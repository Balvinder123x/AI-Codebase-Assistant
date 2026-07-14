"""
FastAPI Application
===================
The HTTP layer. This file is deliberately THIN.

Each route does exactly three things:
    1. Accept a validated request (Pydantic did the checking).
    2. Call ONE service function.
    3. Shape the result into a response model.

All the real work lives in services/. This is the "thin controller" pattern,
and it is why you can unit-test the whole pipeline without ever starting a
web server.

Run with:
    uvicorn main:app --reload
Then open http://127.0.0.1:8000/docs for interactive API documentation.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import config
from models.schemas import (
    AskRequest,
    AskResponse,
    FileContentResponse,
    FileInfoResponse,
    FilesResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    SearchHitResponse,
    SearchResponse,
    SourceChunk,
)
from services import chunker, rag_chain, repo_loader, repo_utils, vector_store

app = FastAPI(
    title="AI Codebase Assistant",
    description=(
        "Index any public GitHub repository and ask questions about it "
        "in natural language, using Retrieval-Augmented Generation."
    ),
    version="1.0.0",
)

@app.get("/")
def root():
    return {
        "project": "AI Codebase Assistant",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

# CORS: the browser blocks cross-origin requests by default. The React dev
# server runs on :5173 and the API on :8000 - different ports means different
# origins, so we must explicitly allow it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    # Matches any *.vercel.app origin, so Vercel preview deploys (which get a
    # fresh URL every push) work without redeploying this backend.
    allow_origin_regex=config.ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check. Also tells the UI whether the API key is configured."""
    return HealthResponse(
        status="ok",
        llm_model=config.LLM_MODEL,
        embedding_model=config.EMBEDDING_MODEL,
        api_key_configured=bool(config.GOOGLE_API_KEY),
    )


@app.post("/index", response_model=IndexResponse)
def index_repository(request: IndexRequest) -> IndexResponse:
    """
    Clone a GitHub repo, chunk it, embed it, and store it in ChromaDB.

    Pipeline:
        repo_loader.load_repository()  -> list[SourceFile]
        chunker.chunk_files()          -> list[Chunk]
        vector_store.add_chunks()      -> stored in ChromaDB

    This is slow (30s - 2min for a medium repo) because embedding runs on
    the CPU. In production you would push this to a background worker queue
    and poll for status - but that is exactly the kind of complexity we are
    deliberately avoiding here.
    """
    try:
        repo_name, source_files = repo_loader.load_repository(request.repo_url)
        chunks = chunker.chunk_files(source_files, repo_name)
        stored = vector_store.add_chunks(repo_name, chunks)
    except ValueError as exc:
        # Expected failures: bad URL, private repo, empty repo.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Unexpected failures: disk full, model download failed, etc.
        raise HTTPException(
            status_code=500, detail=f"Indexing failed: {exc}"
        ) from exc

    return IndexResponse(
        repo_name=repo_name,
        files_indexed=len(source_files),
        chunks_created=stored,
        message=f"Indexed {len(source_files)} files into {stored} chunks.",
    )


@app.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest) -> AskResponse:
    """
    Answer a natural-language question about an indexed repository.

    This is the RAG endpoint. See services/rag_chain.py for the pipeline.
    We return the retrieved sources alongside the answer so the user can
    verify it - an answer with no citations is just a rumour.
    """
    if not vector_store.collection_exists(request.repo_name):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Repository '{request.repo_name}' is not indexed. "
                f"Index it first via POST /index."
            ),
        )

    try:
        result = rag_chain.ask(
            repo_name=request.repo_name,
            question=request.question,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Every model in the fallback chain was unavailable/rate limited.
        # 429 (not 500) - this is a quota problem, not a server bug.
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate answer: {exc}"
        ) from exc

    return AskResponse(
        answer=result.answer,
        model_used=result.model_used,
        sources=[
            SourceChunk(
                file_path=chunk.file_path,
                language=chunk.language,
                text=chunk.text,
                score=chunk.score,
            )
            for chunk in result.sources
        ],
    )


@app.get("/files", response_model=FilesResponse)
def get_files(repo_name: str = Query(..., examples=["requests"])) -> FilesResponse:
    """List every indexed file in the repo. Powers the sidebar file tree."""
    try:
        files = repo_utils.list_files(repo_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FilesResponse(
        repo_name=repo_name,
        total=len(files),
        files=[
            FileInfoResponse(
                path=f.path, language=f.language, size_bytes=f.size_bytes
            )
            for f in files
        ],
    )


@app.get("/file", response_model=FileContentResponse)
def get_file(
    repo_name: str = Query(...),
    path: str = Query(..., description="Path relative to the repo root"),
) -> FileContentResponse:
    """Read a single file's contents. Powers the code viewer."""
    try:
        content, language = repo_utils.read_file(repo_name, path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileContentResponse(path=path, language=language, content=content)


@app.get("/search", response_model=SearchResponse)
def keyword_search(
    repo_name: str = Query(...),
    q: str = Query(..., min_length=1, description="Literal text to search for"),
) -> SearchResponse:
    """
    Literal keyword search (grep). Complements the semantic search in /ask.

    Semantic search is good at concepts and bad at exact strings.
    Keyword search is the reverse. Offering both covers both failure modes.
    """
    try:
        hits = repo_utils.search_keyword(repo_name, q)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return SearchResponse(
        query=q,
        total=len(hits),
        hits=[
            SearchHitResponse(
                file_path=h.file_path, line_number=h.line_number, line=h.line
            )
            for h in hits
        ],
    )
