"""
Chunker
=======
Splits source files into smaller pieces ("chunks") that fit comfortably
inside an LLM prompt, and attaches metadata to each one.

WHY CHUNK AT ALL?
-----------------
Two reasons:

1. Context window. We cannot paste an entire 50-file repository into the
   prompt - it would be hundreds of thousands of tokens.

2. Retrieval precision. Even if we could fit a whole file, an embedding of
   a 3000-line file is a blurry average of everything in it. It matches
   every query weakly and no query strongly. Small chunks produce sharp,
   specific embeddings.

WHY RecursiveCharacterTextSplitter?
-----------------------------------
A naive splitter cuts every 1000 characters, which will happily slice a
function in half. Recursive splitting tries a prioritised list of
separators: first split on the biggest structural boundary; only if the
piece is still too big does it fall back to a smaller separator.

For Python, LangChain's built-in separator list is roughly:
    ["\\nclass ", "\\ndef ", "\\n\\tdef ", "\\n\\n", "\\n", " ", ""]

So it prefers to break between classes, then between functions, then
between paragraphs, and only splits mid-word as a last resort. That is a
cheap approximation of AST-aware chunking, with none of the complexity.
"""

from dataclasses import dataclass

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

import config
from services.repo_loader import SourceFile


@dataclass
class Chunk:
    """One chunk of code, plus everything we know about where it came from."""

    text: str                # the code itself - this gets embedded
    file_path: str           # e.g. "src/requests/api.py"
    language: str            # e.g. "python"
    chunk_index: int         # 0, 1, 2 ... position within its own file
    chunk_id: str            # globally unique, e.g. "requests::api.py::2"


# Map our language strings -> LangChain's Language enum.
# Any language NOT in this map falls back to the generic splitter.
LANGCHAIN_LANGUAGES: dict[str, Language] = {
    "python": Language.PYTHON,
    "javascript": Language.JS,
    "typescript": Language.TS,
    "java": Language.JAVA,
    "cpp": Language.CPP,
    "c": Language.CPP,        # close enough; C and C++ share separators
    "go": Language.GO,
    "rust": Language.RUST,
    "ruby": Language.RUBY,
    "php": Language.PHP,
    "csharp": Language.CSHARP,
    "swift": Language.SWIFT,
    "kotlin": Language.KOTLIN,
    "html": Language.HTML,
    "markdown": Language.MARKDOWN,
}


def _get_splitter(language: str) -> RecursiveCharacterTextSplitter:
    """
    Return a splitter tuned for `language`.

    Uses LangChain's language-aware separator lists where available, and a
    plain recursive splitter (paragraph -> line -> word -> char) otherwise.
    """
    if language in LANGCHAIN_LANGUAGES:
        return RecursiveCharacterTextSplitter.from_language(
            language=LANGCHAIN_LANGUAGES[language],
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )


def chunk_file(source_file: SourceFile, repo_name: str) -> list[Chunk]:
    """Split a single source file into chunks."""
    splitter = _get_splitter(source_file.language)
    texts = splitter.split_text(source_file.content)

    chunks: list[Chunk] = []
    for index, text in enumerate(texts):
        # Skip whitespace-only fragments the splitter sometimes produces
        if not text.strip():
            continue

        chunks.append(
            Chunk(
                text=text,
                file_path=source_file.relative_path,
                language=source_file.language,
                chunk_index=index,
                # chunk_id must be unique across the whole collection,
                # otherwise ChromaDB will silently overwrite documents.
                chunk_id=f"{repo_name}::{source_file.relative_path}::{index}",
            )
        )

    return chunks


def chunk_files(
    source_files: list[SourceFile], repo_name: str
) -> list[Chunk]:
    """
    Split every file in the repository.

    Called by the POST /index route, straight after repo_loader.
    """
    all_chunks: list[Chunk] = []
    for source_file in source_files:
        all_chunks.extend(chunk_file(source_file, repo_name))
    return all_chunks
