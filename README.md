# 🤖 AI Codebase Assistant

Index any public GitHub repository and ask questions about it in plain English.
A mini "Copilot Chat for understanding repos", built with **Retrieval-Augmented
Generation (RAG)**.

Every answer shows the exact code chunks it was based on — so you can verify it
instead of trusting it.

**Stack:** Python · FastAPI · LangChain · ChromaDB · Sentence-Transformers ·
Google Gemini · React · TailwindCSS

---

## What it does

| Feature | How |
|---|---|
| Clone any public GitHub repo | GitPython, shallow clone (`depth=1`) |
| Split code into chunks | LangChain `RecursiveCharacterTextSplitter`, language-aware |
| Semantic search | `all-MiniLM-L6-v2` embeddings (local, free) + ChromaDB |
| Answer questions | RAG: retrieve top-5 chunks → stuff into prompt → Gemini |
| Show the evidence | Every answer lists the source files + similarity scores |
| Browse files | File tree sidebar, click to view |
| Exact-match search | Literal keyword search (grep), complements semantic search |

---

## How RAG works here

```
   Question: "How does retry logic work?"
        │
        ▼
   Embed the question           →  [0.02, -0.41, 0.88, ...]  (384 numbers)
        │
        ▼
   Vector search in ChromaDB    →  top-5 most similar code chunks
        │
        ▼
   Stuff those chunks into the prompt as CONTEXT
        │
        ▼
   Gemini reads the context and answers
        │
        ▼
   Answer  +  the 5 sources it used
```

**Why RAG instead of just asking the LLM?** The model has never seen your
repository — its weights were frozen before your code existed. Ask it about your
code and it will hallucinate a plausible-sounding answer. RAG turns a *memory*
problem into a *reading-comprehension* problem: we don't ask the model to
remember your code, we paste the relevant parts into the prompt and ask it to
read.

**Why not fine-tune on the repo instead?** Three reasons:
1. **Cost** — fine-tuning is expensive; a vector search is nearly free.
2. **Freshness** — a new commit means retraining. With RAG you re-index in seconds.
3. **Attribution** — RAG can cite which file an answer came from. A fine-tuned model cannot.

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Git

### 1. Get a free API key
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) → **Create API key**.
Free tier, no credit card.

### 2. Backend

```bash
cd backend

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt   # ~2GB, mostly PyTorch. One time.

cp .env.example .env              # Windows: copy .env.example .env
# open .env and paste your key

uvicorn main:app --reload
```

Backend runs at **http://127.0.0.1:8000**
Interactive API docs at **http://127.0.0.1:8000/docs**

### 3. Frontend

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

### 4. Use it

1. Paste a repo URL (e.g. `https://github.com/psf/requests`)
2. Click **Index Repo** — takes 1–2 min on first run (the embedding model downloads once, then it's cached)
3. Ask questions

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + whether the API key is set |
| `POST` | `/index` | Clone, chunk, embed a repo |
| `POST` | `/ask` | RAG question answering |
| `GET` | `/files` | List indexed files |
| `GET` | `/file` | Read one file |
| `GET` | `/search` | Literal keyword search |

<details>
<summary>Example requests</summary>

```bash
# Index
curl -X POST http://127.0.0.1:8000/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/psf/requests"}'

# Ask
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"repo_name": "requests", "question": "How does retry logic work?"}'
```
</details>

---

## Project structure

```
ai-codebase-assistant/
├── backend/
│   ├── main.py                  # FastAPI routes (thin — no logic here)
│   ├── config.py                # every tunable value, one place
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response contracts
│   └── services/
│       ├── repo_loader.py       # clone + walk + filter files
│       ├── chunker.py           # language-aware splitting + metadata
│       ├── vector_store.py      # embeddings + ChromaDB
│       ├── rag_chain.py         # retrieve → prompt → LLM   ← the core
│       └── repo_utils.py        # read_file / list_files / search_keyword
└── frontend/
    └── src/
        ├── App.jsx              # owns all shared state
        ├── api.js               # every network call
        └── components/
            ├── RepoInput.jsx
            ├── ChatBox.jsx
            ├── Sidebar.jsx      # file tree + keyword search
            ├── SourcePanel.jsx  # retrieved chunks + file viewer
            └── Loader.jsx
```

**Layering:** routes call services; services never call routes. Every service is
importable and testable without starting a web server.

---

## Design decisions

**Chunk size 1000 chars, 200 overlap.** Too big and the embedding becomes a
blurry average that matches everything weakly. Too small and a function gets cut
in half. The 200-char overlap means a function sitting on a chunk boundary still
appears whole in at least one chunk.

**Language-aware splitting.** `RecursiveCharacterTextSplitter.from_language()`
prefers to break on `\nclass ` and `\ndef ` before falling back to blank lines,
then newlines, then spaces. A cheap approximation of AST-aware chunking with
none of the complexity.

**Local embeddings, cloud LLM.** Embedding runs thousands of times during
indexing — doing that over an API would be slow and rate-limited. Generation
runs once per question, and quality matters more there. So: embeddings local
(free, fast), generation via Gemini.

**One Chroma collection per repo.** Searching repo A can never return chunks
from repo B, and re-indexing only wipes that repo's data.

**Temperature 0.2.** We want the same answer every time for "what does this
function do", not creative variation.

**No autonomous agent.** A tool-calling agent needs a reasoning loop, an
iteration cap, and error recovery when a tool fails. That complexity buys
nothing here — the user already knows they want to open a file, so they just
click it. Simple, predictable, debuggable.

---

## Security note

`repo_utils._resolve_safe_path()` blocks **path traversal**. Without it, a
request for `?path=../../../../etc/passwd` would happily read files outside the
repo. The fix: `resolve()` the path (collapsing all the `..`), then verify the
result is still inside the repo root.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `GOOGLE_API_KEY is not set` | `cp .env.example .env`, paste your key, restart uvicorn |
| Frontend: "Cannot reach the backend" | Is uvicorn running on port 8000? |
| First index is very slow | Normal — the 90MB embedding model downloads once, then caches |
| `Could not clone` | Repo must be **public**; check the URL |
| CORS error | Frontend must run on `:5173` or `:3000` (see `config.ALLOWED_ORIGINS`) |

---

## License

MIT
