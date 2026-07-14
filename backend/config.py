"""
Central configuration for the AI Codebase Assistant.

Every tunable value lives here - API keys, model names, chunk sizes,
folder paths. No other file should hardcode these values.

Interview note: this is the "single source of truth" pattern. When asked
"how would you swap the embedding model?", the answer is "change one line
in config.py" - nothing else in the codebase needs to know.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from the .env file into os.environ
load_dotenv()

# ---------------------------------------------------------------- Paths ----
# BASE_DIR = the 'backend' folder (the parent of this file)
BASE_DIR: Path = Path(__file__).resolve().parent

# Where cloned repositories are stored
REPOS_DIR: Path = BASE_DIR / "cloned_repos"

# Where ChromaDB persists its data (so the index survives server restarts)
CHROMA_DIR: Path = BASE_DIR / "chroma_db"

REPOS_DIR.mkdir(exist_ok=True)
CHROMA_DIR.mkdir(exist_ok=True)

# ------------------------------------------------------------------ LLM ----
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

LLM_MODEL: str = "gemini-2.0-flash"

# Low temperature = factual, deterministic. We want the same answer every
# time for "what does this function do", not creative variation.
LLM_TEMPERATURE: float = 0.2

# ----------------------------------------------------------- Embeddings ----
# Runs locally via sentence-transformers. Free, offline, 384 dimensions.
# Downloads ~90MB on first use, then cached forever.
EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

# ------------------------------------------------------------- Chunking ----
CHUNK_SIZE: int = 1000       # characters per chunk
CHUNK_OVERLAP: int = 200     # characters repeated between neighbouring chunks

# ------------------------------------------------------------ Retrieval ----
TOP_K: int = 5               # how many chunks to retrieve per question

# ------------------------------------------------------- File filtering ----
# Folders we never walk into
IGNORED_DIRS: set[str] = {
    ".git", "node_modules", "venv", ".venv", "env",
    "dist", "build", "__pycache__", ".next", "target",
    ".idea", ".vscode", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "site-packages",
}

# Only these extensions get indexed. Everything else (images, binaries,
# lockfiles, fonts) is skipped.
ALLOWED_EXTENSIONS: set[str] = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".kt",
    ".html", ".css", ".scss",
    ".md", ".txt", ".yml", ".yaml", ".json", ".toml",
}

# Skip files bigger than this - usually minified bundles or generated code,
# which pollute the vector store with noise.
MAX_FILE_SIZE_BYTES: int = 200_000

# Map file extension -> language name. Stored as chunk metadata, and used
# to pick a language-aware splitter in chunker.py
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".md": "markdown",
    ".txt": "text",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
}

# ------------------------------------------------------------------ API ----
# Allow the React dev server to call the backend (CORS)
ALLOWED_ORIGINS: list[str] = [
    "http://localhost:5173",   # Vite default
    "http://localhost:3000",   # Create React App default
]
