"""
Repo Utilities
==============
Plain helper functions that operate on an already-cloned repository:

    list_files()      - the file tree, for the sidebar
    read_file()       - one file's contents, for the code viewer
    search_keyword()  - literal text search (grep), for exact lookups

IMPORTANT DESIGN DECISION
-------------------------
These are NOT LangChain tools, and the LLM does not decide when to call
them. They are ordinary functions exposed as REST endpoints that the React
frontend calls directly.

Why? Because an agent that chooses its own tools is a whole extra system:
you need a reasoning loop, an iteration cap, error recovery when a tool
fails, and a story for what happens when the model calls read_file() on a
path that does not exist. That complexity buys us nothing here - the user
already knows they want to open a file, so let them just click it.

Simple, predictable, and easy to defend in an interview.

WHY KEEP KEYWORD SEARCH AT ALL, IF WE HAVE SEMANTIC SEARCH?
-----------------------------------------------------------
They fail in opposite directions, and this is a great interview answer:

  - Semantic search is good at CONCEPTS ("how does auth work?") and bad at
    EXACT STRINGS. Ask it for the variable `MAX_RETRIES_v2` and the
    embedding blurs it into "retry-ish things".

  - Keyword search is perfect at exact strings and useless at concepts. It
    cannot find `verify_token()` when you search for "authentication".

Offering both covers both failure modes.
"""

from dataclasses import dataclass
from pathlib import Path

import config
from services.repo_loader import get_repo_path


@dataclass
class FileInfo:
    """One entry in the file tree."""

    path: str        # e.g. "src/requests/api.py"
    language: str
    size_bytes: int


@dataclass
class SearchHit:
    """One line matching a keyword search."""

    file_path: str
    line_number: int
    line: str        # the matching line, stripped and truncated


def list_files(repo_name: str) -> list[FileInfo]:
    """
    Return every indexable file in the repo, for the sidebar file tree.

    Applies the same filters as the indexer, so the sidebar shows exactly
    the files that were actually indexed. Nothing more, nothing less.
    """
    repo_path = get_repo_path(repo_name)
    files: list[FileInfo] = []

    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue

        parts = path.relative_to(repo_path).parts
        if any(part in config.IGNORED_DIRS for part in parts[:-1]):
            continue

        suffix = path.suffix.lower()
        if suffix not in config.ALLOWED_EXTENSIONS:
            continue

        size = path.stat().st_size
        if size > config.MAX_FILE_SIZE_BYTES:
            continue

        # Skip empty files. The indexer skips them too (an empty chunk is
        # pure noise in the vector store), so if we listed them here the
        # sidebar would show files that were never actually indexed.
        try:
            if not path.read_text(encoding="utf-8", errors="ignore").strip():
                continue
        except OSError:
            continue

        files.append(
            FileInfo(
                path=str(path.relative_to(repo_path)),
                language=config.EXTENSION_TO_LANGUAGE.get(suffix, "text"),
                size_bytes=size,
            )
        )

    return files


def _resolve_safe_path(repo_name: str, relative_path: str) -> Path:
    """
    Turn a user-supplied relative path into an absolute path, and REFUSE if
    it escapes the repository folder.

    THIS IS A SECURITY CHECK. Without it, a request for
        ?path=../../../../etc/passwd
    would happily read a file outside the repo. This is called a path
    traversal attack, and it is one of the oldest bugs in web development.

    The fix: resolve() the path (which collapses all the '..'), then verify
    the result is still inside the repo root.
    """
    repo_path = get_repo_path(repo_name).resolve()
    target = (repo_path / relative_path).resolve()

    if not target.is_relative_to(repo_path):
        raise ValueError("Invalid path: outside the repository.")

    if not target.is_file():
        raise ValueError(f"File not found: {relative_path}")

    return target


def read_file(repo_name: str, relative_path: str) -> tuple[str, str]:
    """
    Read one file from the repo.

    Returns:
        (content, language)
    """
    target = _resolve_safe_path(repo_name, relative_path)

    content = target.read_text(encoding="utf-8", errors="ignore")
    language = config.EXTENSION_TO_LANGUAGE.get(target.suffix.lower(), "text")

    return content, language


def search_keyword(
    repo_name: str, keyword: str, max_results: int = 50
) -> list[SearchHit]:
    """
    Literal, case-insensitive text search across the repo. Basically grep.

    Stops after `max_results` hits so that searching for "e" does not return
    fifty thousand lines and freeze the browser.
    """
    if not keyword.strip():
        return []

    repo_path = get_repo_path(repo_name)
    needle = keyword.lower()
    hits: list[SearchHit] = []

    for file_info in list_files(repo_name):
        if len(hits) >= max_results:
            break

        path = repo_path / file_info.path
        try:
            lines = path.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines()
        except OSError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if needle in line.lower():
                hits.append(
                    SearchHit(
                        file_path=file_info.path,
                        line_number=line_number,
                        line=line.strip()[:200],  # truncate very long lines
                    )
                )
                if len(hits) >= max_results:
                    break

    return hits
