"""
Pydantic Schemas
================
The CONTRACT between the FastAPI backend and the React frontend.

WHY PYDANTIC?
-------------
Three things for free:

  1. Validation. If the frontend POSTs {"repo_url": 123}, FastAPI rejects it
     with a 422 before your code ever runs. You never write `if not isinstance(...)`.

  2. Serialisation. FastAPI converts these objects to JSON automatically.

  3. Documentation. FastAPI reads these classes and generates interactive
     API docs at /docs. Free Swagger UI, zero effort.

This is "parse, don't validate": convert untrusted input into a trusted
typed object once, at the boundary, then trust it everywhere downstream.
"""

from pydantic import BaseModel, Field


# --------------------------------------------------------------- Requests --
class IndexRequest(BaseModel):
    """POST /index"""

    repo_url: str = Field(
        ...,
        description="Public GitHub repository URL",
        examples=["https://github.com/psf/requests"],
    )


class AskRequest(BaseModel):
    """POST /ask"""

    repo_name: str = Field(..., examples=["requests"])
    question: str = Field(..., examples=["How does the retry logic work?"])
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="How many chunks to retrieve. Defaults to config.TOP_K.",
    )


# -------------------------------------------------------------- Responses --
class IndexResponse(BaseModel):
    """What POST /index returns."""

    repo_name: str
    files_indexed: int
    chunks_created: int
    message: str


class SourceChunk(BaseModel):
    """One retrieved chunk, shown in the 'Sources' panel of the UI."""

    file_path: str
    language: str
    text: str
    score: float = Field(..., description="Similarity, 0-1. Higher is better.")


class AskResponse(BaseModel):
    """What POST /ask returns: the answer AND the evidence behind it."""

    answer: str
    sources: list[SourceChunk]


class FileInfoResponse(BaseModel):
    """One entry in the file tree."""

    path: str
    language: str
    size_bytes: int


class FilesResponse(BaseModel):
    """GET /files"""

    repo_name: str
    total: int
    files: list[FileInfoResponse]


class FileContentResponse(BaseModel):
    """GET /file?repo_name=...&path=..."""

    path: str
    language: str
    content: str


class SearchHitResponse(BaseModel):
    """One line matching a keyword search."""

    file_path: str
    line_number: int
    line: str


class SearchResponse(BaseModel):
    """GET /search?repo_name=...&q=..."""

    query: str
    total: int
    hits: list[SearchHitResponse]


class HealthResponse(BaseModel):
    """GET /health"""

    status: str
    llm_model: str
    embedding_model: str
    api_key_configured: bool
