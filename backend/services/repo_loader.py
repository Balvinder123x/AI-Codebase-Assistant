"""
Repository Loader
=================
Turns a GitHub URL into a list of readable source files.

Responsibilities:
  1. Clone a public GitHub repo into a local folder.
  2. Walk the directory tree.
  3. Skip junk (.git, node_modules, binaries, huge files).
  4. Return a clean list of SourceFile objects, ready for chunking.

This module knows NOTHING about embeddings, ChromaDB, or LLMs.
It only deals with the filesystem. That separation is what makes it
testable on its own.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from git import GitCommandError, Repo

import config


@dataclass
class SourceFile:
    """
    One source file from the repository.

    We use a dataclass instead of a plain dict so that a typo like
    `file.pathh` fails immediately with an AttributeError, instead of
    silently returning None at 2am.
    """

    relative_path: str  # e.g. "src/requests/api.py" - what the user sees
    content: str        # the actual text of the file
    language: str       # e.g. "python" - stored as chunk metadata later


def get_repo_name(repo_url: str) -> str:
    """
    Extract a folder-safe repo name from a GitHub URL.

    "https://github.com/psf/requests.git" -> "requests"
    "https://github.com/psf/requests"     -> "requests"
    """
    name = repo_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def clone_repository(repo_url: str) -> Path:
    """
    Clone `repo_url` into config.REPOS_DIR and return the local path.

    If the folder already exists we delete it first. Re-cloning is cheap and
    guarantees we never index a half-downloaded repo left over from a
    failed run. This makes the operation idempotent: same input, same
    output, every time.

    Raises:
        ValueError: if the clone fails (bad URL, private repo, no network).
    """
    repo_name = get_repo_name(repo_url)
    target_dir = config.REPOS_DIR / repo_name

    if target_dir.exists():
        shutil.rmtree(target_dir)

    try:
        # depth=1 -> shallow clone. We only need the current snapshot of the
        # code, not the entire commit history. Much faster on large repos.
        Repo.clone_from(repo_url, target_dir, depth=1)
    except GitCommandError as exc:
        raise ValueError(
            f"Could not clone '{repo_url}'. "
            f"Check that the URL is correct and the repository is public."
        ) from exc

    return target_dir


def _is_in_ignored_dir(file_path: Path, repo_root: Path) -> bool:
    """Return True if any folder in this file's path is on the ignore list."""
    relative_parts = file_path.relative_to(repo_root).parts
    # parts[:-1] drops the filename itself, leaving only the folders
    return any(part in config.IGNORED_DIRS for part in relative_parts[:-1])


def _should_index_file(file_path: Path) -> bool:
    """
    Decide whether a single file is worth indexing.

    We check the cheap things first (extension, then size via stat()) so we
    never read a 50MB minified bundle into memory just to throw it away.
    """
    if file_path.suffix.lower() not in config.ALLOWED_EXTENSIONS:
        return False

    if file_path.stat().st_size > config.MAX_FILE_SIZE_BYTES:
        return False

    return True


def load_source_files(repo_path: Path) -> list[SourceFile]:
    """
    Walk `repo_path` recursively and return every file worth indexing.
    """
    source_files: list[SourceFile] = []

    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue

        if _is_in_ignored_dir(path, repo_path):
            continue

        if not _should_index_file(path):
            continue

        try:
            # errors="ignore" -> a few odd bytes won't crash the whole index
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue  # unreadable file: permissions, broken symlink, etc.

        # Empty files add pure noise to the vector store.
        if not content.strip():
            continue

        source_files.append(
            SourceFile(
                relative_path=str(path.relative_to(repo_path)),
                content=content,
                language=config.EXTENSION_TO_LANGUAGE.get(
                    path.suffix.lower(), "text"
                ),
            )
        )

    return source_files


def load_repository(repo_url: str) -> tuple[str, list[SourceFile]]:
    """
    Main entry point, used by the POST /index route.

    Returns:
        (repo_name, list_of_source_files)

    Raises:
        ValueError: if the clone fails or the repo has no indexable files.
    """
    repo_name = get_repo_name(repo_url)
    repo_path = clone_repository(repo_url)
    files = load_source_files(repo_path)

    if not files:
        raise ValueError(
            f"No indexable source files found in '{repo_name}'. "
            f"The repository may be empty or contain only unsupported "
            f"file types."
        )

    return repo_name, files


def get_repo_path(repo_name: str) -> Path:
    """
    Return the local path of an already-cloned repo.

    Used by repo_utils.py to read files and run keyword searches.

    Raises:
        ValueError: if the repo has not been cloned/indexed yet.
    """
    path = config.REPOS_DIR / repo_name
    if not path.exists():
        raise ValueError(
            f"Repository '{repo_name}' is not indexed. Index it first."
        )
    return path
