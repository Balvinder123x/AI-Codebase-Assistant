"""
Vector Store
============
Wraps ChromaDB. Two jobs:

  1. add_chunks()  - embed chunks and store them
  2. search()      - embed a question and find the most similar chunks

WHAT IS AN EMBEDDING?
---------------------
A function that turns text into a fixed-length list of numbers (here: 768
floats) such that texts with similar MEANING end up close together in that
768-dimensional space.

"function that reads a file"  ->  [0.02, -0.41, 0.88, ...]
"def load_file(path):"        ->  [0.03, -0.39, 0.85, ...]   <- close!
"CSS grid layout"             ->  [0.71,  0.12, -0.44, ...]  <- far away

This is why semantic search beats keyword search (Ctrl+F): the user can ask
"how does authentication work?" and we find `verify_token()` even though
the word "authentication" appears nowhere in it.

WHERE DO THE EMBEDDINGS COME FROM?
----------------------------------
Gemini's embedding API (models/text-embedding-004), NOT a local model.

Originally this used sentence-transformers running on CPU. That pulls in
PyTorch, which costs ~250-400MB of RAM just to import - before embedding a
single chunk. On a 512MB host that OOMs the process on startup.

Calling the API instead keeps zero model weights in memory. The tradeoff:
indexing now needs network access and an API key, and is bound by API
latency rather than CPU. On a small box, that is the right trade.

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
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import config
from services.chunker import Chunk

# Global cache. Building the embeddings client is cheap (it holds no model
# weights - it is just an API wrapper), but we still reuse one instance
# rather than constructing a new client per request.
_embedding_model: GoogleGenerativeAIEmbeddings | None = None


def get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """
    Return the shared embedding client, creating it on first use.

    NOTE: this holds NO model weights in memory. It sends text to Gemini's
    embedding endpoint and receives vectors back. That is the entire reason
    we can run on a 512MB host - a local sentence-transformers model would
    drag in PyTorch and OOM the process before embedding anything.
    """
    global _embedding_model

    if _embedding_model is None:
        if not config.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Embeddings now run through the "
                "Gemini API, so a key is required to index a repository. "
                "Get one free at https://aistudio.google.com/apikey"
            )

        _embedding_model = GoogleGenerativeAIEmbeddings(
            model=config.EMBEDDING_MODEL,
            google_api_key=config.GOOGLE_API_KEY,
            # NOTE: we deliberately do NOT set `task_type`.
            #
            # Left unset, the library uses RETRIEVAL_DOCUMENT when embedding
            # stored chunks and RETRIEVAL_QUERY when embedding a user's
            # question. That asymmetry is a real quality win for RAG: a
            # question ("how does auth work?") and the code that answers it
            # ("def verify_token(...)") do not look alike as text, so the
            # model embeds each side with the appropriate intent.
            #
            # Pinning task_type here would force ONE type for both sides and
            # quietly degrade retrieval.
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

    # Embed in batches. Each batch is one API call to Gemini, so this also
    # controls how many network round-trips indexing costs. Gemini caps batch
    # size at 100; we stay under it and keep peak memory flat.
    batch_size = config.EMBEDDING_BATCH_SIZE
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
