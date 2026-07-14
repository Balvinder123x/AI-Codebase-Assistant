"""
Vector Store
============
Wraps ChromaDB. Two jobs:

  1. add_chunks()  - embed chunks and store them
  2. search()      - embed a question and find the most similar chunks

WHAT IS AN EMBEDDING?
---------------------
A function that turns text into a fixed-length list of numbers (here: 384
floats) such that texts with similar MEANING end up close together in that
384-dimensional space.

"function that reads a file"  ->  [0.02, -0.41, 0.88, ...]
"def load_file(path):"        ->  [0.03, -0.39, 0.85, ...]   <- close!
"CSS grid layout"             ->  [0.71,  0.12, -0.44, ...]  <- far away

This is why semantic search beats keyword search (Ctrl+F): the user can ask
"how does authentication work?" and we find `verify_token()` even though
the word "authentication" appears nowhere in it.

WHY A VECTOR DATABASE INSTEAD OF A PYTHON LIST?
-----------------------------------------------
You could store the vectors in a list and compute cosine similarity against
all of them on every query. That is O(n) per query and it works fine at
1,000 chunks. At 100,000 chunks it becomes slow. A vector DB adds an index
(approximate nearest-neighbour search), persistence to disk, and metadata
filtering. Chroma gives us all three in a few lines and needs no server.
"""

from dataclasses import dataclass

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

import config
from services.chunker import Chunk

# Global cache. Loading the sentence-transformers model takes ~3 seconds and
# ~90MB of RAM, so we do it ONCE and reuse it for the whole process lifetime.
# Without this, every single API request would reload the model.
_embedding_model: HuggingFaceEmbeddings | None = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """Return the shared embedding model, loading it on first use."""
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            # Normalising to unit length means cosine similarity reduces to a
            # simple dot product - faster, and it is what Chroma expects.
            encode_kwargs={"normalize_embeddings": True},
        )

    return _embedding_model


def get_vector_store(repo_name: str) -> Chroma:
    """
    Return the Chroma collection for one repository.

    DESIGN NOTE: one collection per repo, not one shared collection.
    This means searching repo A can never accidentally return chunks from
    repo B, and re-indexing a repo only wipes that repo's data.
    """
    return Chroma(
        collection_name=_safe_collection_name(repo_name),
        embedding_function=get_embedding_model(),
        persist_directory=str(config.CHROMA_DIR),
    )


def _safe_collection_name(repo_name: str) -> str:
    """
    Chroma requires collection names to be 3-63 chars, alphanumeric plus
    hyphens/underscores, starting and ending with alphanumeric.
    """
    cleaned = "".join(c if c.isalnum() else "_" for c in repo_name)
    cleaned = cleaned.strip("_")
    if len(cleaned) < 3:
        cleaned = f"repo_{cleaned}"
    return cleaned[:63]


def add_chunks(repo_name: str, chunks: list[Chunk]) -> int:
    """
    Embed every chunk and store it in ChromaDB.

    We wipe any existing collection first so that re-indexing a repo gives a
    clean result instead of duplicating every chunk.

    Returns:
        The number of chunks stored.
    """
    store = get_vector_store(repo_name)

    # Clear old data for this repo (safe if the collection is new/empty)
    try:
        store.delete_collection()
    except Exception:
        pass

    store = get_vector_store(repo_name)

    # LangChain's Document = the text to embed + a metadata dict.
    # The metadata is what powers the "Sources" panel in the UI: it lets us
    # tell the user WHICH file each piece of the answer came from.
    documents = [
        Document(
            page_content=chunk.text,
            metadata={
                "file_path": chunk.file_path,
                "language": chunk.language,
                "chunk_index": chunk.chunk_index,
                "repo_name": repo_name,
            },
        )
        for chunk in chunks
    ]

    ids = [chunk.chunk_id for chunk in chunks]

    # Add in batches. Chroma has an internal limit on batch size, and
    # embedding 5000 chunks in one call can spike memory.
    batch_size = 100
    for start in range(0, len(documents), batch_size):
        store.add_documents(
            documents=documents[start : start + batch_size],
            ids=ids[start : start + batch_size],
        )

    return len(documents)


@dataclass
class RetrievedChunk:
    """A chunk returned by a search, plus its similarity score."""

    text: str
    file_path: str
    language: str
    score: float  # 0.0 - 1.0, higher = more relevant


def search(repo_name: str, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
    """
    Find the `top_k` chunks most semantically similar to `query`.

    Steps under the hood:
      1. Embed the query with the SAME model used for the chunks.
         (Using a different model would be like comparing metres to feet.)
      2. Compare it against every stored vector using cosine similarity.
      3. Return the closest matches.
    """
    if top_k is None:
        top_k = config.TOP_K

    store = get_vector_store(repo_name)

    # Chroma returns DISTANCE (lower = closer). We convert to a similarity
    # score (higher = better) because that is more intuitive in a UI.
    results = store.similarity_search_with_score(query, k=top_k)

    retrieved: list[RetrievedChunk] = []
    for document, distance in results:
        retrieved.append(
            RetrievedChunk(
                text=document.page_content,
                file_path=document.metadata.get("file_path", "unknown"),
                language=document.metadata.get("language", "text"),
                score=round(max(0.0, 1.0 - distance), 3),
            )
        )

    return retrieved


def collection_exists(repo_name: str) -> bool:
    """Return True if this repo has already been indexed."""
    try:
        store = get_vector_store(repo_name)
        return store._collection.count() > 0
    except Exception:
        return False
