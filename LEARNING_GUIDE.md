# Learning Guide

Every concept in this project, explained from scratch. Read this before an
interview.

**Rule: if you cannot explain a file, delete it.** Nothing in this project exists
just to look impressive.

---

## 1. Large Language Models

**What.** A neural network trained to predict the next token. That's it. Every
capability — writing code, answering questions — emerges from that one objective
at scale.

**Analogy.** Autocomplete that read the internet.

**Why this matters here.** The model's weights were frozen at training time. It
has **never seen your repository**. This single fact is the reason RAG exists.

**Interview questions**
- *Q: Why do LLMs hallucinate?*
  Their objective is *plausible* text, not *true* text. Nothing in the training
  loss penalizes confident fiction. A model asked about code it has never seen
  will produce something that *looks* like a correct answer, because that's what
  it was optimized to do.
- *Q: What is a context window?*
  The maximum tokens (prompt + answer) the model can process at once. Exceed it
  and the request fails or gets truncated. This is the hard constraint that
  forces chunking.

**Common mistake.** Assuming a bigger context window makes RAG unnecessary. Even
with a 1M-token window, stuffing an entire repo in is slow, expensive, and
*worse* — models lose accuracy on facts buried in the middle of a long context
("lost in the middle").

---

## 2. Tokens

**What.** Models don't see characters or words. They see integers. Tokenization
maps text → integer IDs using a learned vocabulary (~50–100k entries). Common
sequences (`" the"`, `"def "`) get one ID; rare ones get split into pieces.

**Why not character-level?** Sequences become ~5× longer, and attention is O(n²).
You just made the model 25× more expensive.

**Why not word-level?** Out-of-vocabulary words become `<UNK>` and you lose
information. Also `run`/`running`/`ran` become three unrelated embeddings.

**Why you care.** Code tokenizes *badly* — indentation eats tokens. Rough rule:
1 token ≈ 0.75 English words, ≈ 0.5 for code.

**Interview question**
- *Q: Why can't LLMs count the r's in "strawberry"?*
  They never see characters. "strawberry" might be 3 tokens. It's like asking you
  how many brushstrokes are in a Chinese character you've only ever heard spoken.

---

## 3. Embeddings

**What.** A function turning text into a fixed-length vector (here: 384 floats),
such that texts with **similar meaning** land close together in that space.

```
"function that reads a file"   →  [ 0.02, -0.41,  0.88, ...]
"def load_file(path):"         →  [ 0.03, -0.39,  0.85, ...]   ← close!
"CSS grid layout"              →  [ 0.71,  0.12, -0.44, ...]   ← far
```

**Analogy.** A library where books are shelved by *topic*, not alphabetically.
Walk to the "cooking" shelf and every cookbook is right there — even the ones
with "cooking" nowhere in the title.

**Why it exists.** Keyword search (Ctrl+F) fails on synonyms. Ask "how does
authentication work?" and grep finds nothing, because the code says
`verify_token()`. Embeddings capture *meaning*, so `verify_token()` and
"authentication" land near each other.

**In this project.** `all-MiniLM-L6-v2`, running locally. Free, offline,
384 dimensions.

**Interview questions**
- *Q: Why must you use the SAME model for indexing and querying?*
  Different models produce different vector spaces. Comparing them is like
  comparing metres to feet — the numbers are meaningless across systems. **This
  is the #1 RAG bug.**
- *Q: Why 384 dimensions and not 10?*
  Too few and unrelated concepts get squashed together. Too many and you pay
  storage/compute for diminishing returns.

---

## 4. Cosine Similarity

**What.** Measures the **angle** between two vectors, ignoring their length.

```
cos(θ) = (A · B) / (|A| × |B|)

 1.0 = identical meaning
 0.0 = unrelated
-1.0 = opposite
```

**Why angle, not distance?** A long document and a short one about the same topic
have very different *magnitudes* but point the same *direction*. Euclidean
distance would call them dissimilar. Cosine correctly says: same topic.

**Optimization in this project.** We normalize embeddings to unit length
(`normalize_embeddings: True` in `vector_store.py`). Once every vector has
length 1, the denominator becomes 1 — so cosine similarity reduces to a plain
dot product. Faster, same answer.

---

## 5. Chunking

**What.** Splitting files into pieces small enough to fit in a prompt.

**Why — two separate reasons (interviewers probe this):**
1. **Context window.** You cannot paste a 50-file repo into a prompt.
2. **Retrieval precision.** *Even if you could*, the embedding of a 3000-line
   file is a blurry average of everything in it. It matches every query weakly
   and no query strongly. Small chunks → sharp, specific embeddings.

**Why `RecursiveCharacterTextSplitter`?** A naive splitter cuts every 1000 chars
and will happily slice a function in half. Recursive splitting tries a
*prioritized list of separators*:

```python
# Python separators, in priority order:
["\nclass ", "\ndef ", "\n\tdef ", "\n\n", "\n", " ", ""]
```

It splits on the biggest structural boundary first, and only falls back to
smaller ones if the piece is still too large. Splitting mid-word is a last
resort.

**Why overlap (200 chars)?** A function might straddle a chunk boundary. Overlap
means the tail of chunk N is repeated at the head of chunk N+1 — so a concept on
the seam still appears *whole* in at least one chunk. Cost: ~20% more storage.
Worth it.

**Interview questions**
- *Q: How would you pick chunk size?*
  Empirically. Build an eval set of questions with known correct files, then
  measure recall@k at 500 / 1000 / 2000. There is no universal right answer — it
  depends on your content.
- *Q: What's better than this?*
  AST-aware chunking (tree-sitter): parse the code and split on real function
  boundaries. Strictly better retrieval, significantly more complexity. This
  project deliberately chose the simpler approach — **know the tradeoff and say
  so.**

---

## 6. Vector Databases & ChromaDB

**What.** A database that stores vectors and answers "find the k most similar to
this one" fast.

**Why not just a Python list?** You *could* store vectors in a list and compute
cosine similarity against all of them per query. That's O(n) — fine at 1,000
chunks, slow at 1,000,000. A vector DB adds:
1. **An index** (approximate nearest-neighbour) → sub-linear search
2. **Persistence** → survives restarts
3. **Metadata filtering** → "only search `.py` files"

**Why Chroma over Pinecone/FAISS?** Chroma runs embedded (no server), persists to
disk, and handles metadata. Pinecone is a paid cloud service. FAISS is faster but
has no metadata or persistence out of the box. For a local project, Chroma is the
right call — **and being able to justify that is the point.**

**Design decision here:** one collection per repo. Searching repo A can never
return chunks from repo B, and re-indexing only wipes that repo.

---

## 7. RAG (Retrieval-Augmented Generation)

**The core idea.** Don't ask the model to *remember* your code. Paste the
relevant code into the prompt and ask it to *read*.

```
Question → Embed → Vector search → Top-K chunks
                                        ↓
                        Stuff into prompt as context
                                        ↓
                                      LLM
                                        ↓
                              Answer + sources
```

RAG converts a **memory problem** into a **reading-comprehension problem**.

**Interview questions**
- *Q: RAG vs fine-tuning?* (Asked constantly.)
  | | RAG | Fine-tuning |
  |---|---|---|
  | Cost | Cheap (vector search) | Expensive (GPU training) |
  | Freshness | Re-index in seconds | Retrain per change |
  | Attribution | Can cite sources | Cannot |
  | Best for | *Knowledge* the model lacks | *Behavior/style/format* |

  Rule of thumb: **RAG for facts, fine-tuning for form.**

- *Q: Your RAG gives a wrong answer. How do you debug it?*
  **This is the question.** Split it in two:
  - **Retrieval failure** — were the right chunks even fetched? Look at the
    Sources panel. If the relevant file isn't there, the bug is in chunking,
    embedding, or `top_k`. The LLM never had a chance.
  - **Generation failure** — right chunks fetched, but the model misread them.
    That's a prompt problem.

  *The Sources panel in this project exists specifically to make that
  distinction visible.* Without it you cannot debug RAG at all.

- *Q: What is the "stuff" strategy?*
  Put all retrieved chunks in one prompt, make one LLM call. Simple, fast,
  cheap. Alternatives (map-reduce, refine) make one call *per chunk* and are only
  needed when context doesn't fit — not our case.

**Common mistakes**
- Using different embedding models for indexing vs querying → garbage results
- `top_k` too low → misses the answer. Too high → noise drowns the signal.
- No "say I don't know" instruction in the prompt → confident hallucination

---

## 8. Prompt Engineering

The system prompt in `rag_chain.py` is the highest-leverage text in the project.
Three deliberate instructions:

| Instruction | Why |
|---|---|
| "Use ONLY the code context below" | Stops the model answering from training data |
| "If the context is insufficient, **say so honestly**" | **Gives the model permission to fail** — without this it invents |
| "Cite the file path" | Makes answers verifiable |

**The honesty clause is the important one.** An LLM's training rewards *plausible*
text. Absent explicit permission to say "I don't know", it will fabricate. You
have to tell it that failing is an acceptable output.

**Temperature 0.2.** Temperature scales the probability distribution before
sampling. High (0.8+) = creative, varied. Low (0.0–0.3) = focused, deterministic.
For "what does this function do?" we want the same answer every time.

---

## 9. FastAPI

**Why FastAPI over Flask?** Automatic request validation via Pydantic, automatic
interactive docs at `/docs`, native async, and type hints that are actually
enforced.

**The thin-controller pattern.** Every route in `main.py` does exactly three
things:
1. Accept a validated request (Pydantic already checked it)
2. Call **one** service function
3. Shape the result into a response model

All real logic lives in `services/`. **This is why you can test the entire
pipeline without starting a web server.**

**Pydantic = "parse, don't validate".** Convert untrusted input into a trusted,
typed object *once*, at the boundary. Then trust it everywhere downstream. You
never write `if not isinstance(...)` again.

**CORS.** Browsers block cross-origin requests by default. Frontend on `:5173`,
backend on `:8000` = different origins. `CORSMiddleware` explicitly allows it.

---

## 10. React

**Controlled components.** React state is the single source of truth for every
input's value. The DOM never holds state React doesn't know about.

**Lifting state up.** `App.jsx` owns all shared state. Why? When you ask a
question:
- `ChatBox` needs the **answer**
- `SourcePanel` needs the **sources**

They're siblings — they can't see each other's state. So state moves to their
nearest common parent. **This is the standard React answer to "two components
need the same data", and it's why this app needs neither Redux nor Context.**

**`useEffect`.** Runs code after render. Used here to (a) ping `/health` once on
mount, (b) auto-scroll to the newest message.

**Optimistic updates.** In `handleAsk`, the user's message appears *immediately*,
before the network call finishes. Waiting for the server to echo it back makes
the UI feel sluggish.

---

## 11. Security: Path Traversal

`repo_utils._resolve_safe_path()` is the one genuinely dangerous function in the
project.

The endpoint `GET /file?path=...` takes a **user-supplied path**. Without a
guard, this request:

```
GET /file?repo_name=requests&path=../../../../etc/passwd
```

...would read a file outside the repository. This is **path traversal**, one of
the oldest bugs in web development.

**The fix:**
```python
target = (repo_path / relative_path).resolve()   # collapses all the ".."
if not target.is_relative_to(repo_path):         # still inside the repo?
    raise ValueError("Invalid path")
```

Resolve first, *then* check. Checking for the literal string `".."` before
resolving is a classic broken fix — it misses URL-encoded and symlink variants.

**Interview gold.** Bringing this up unprompted signals you think about security,
not just features.

---

## 12. Honest Resume Bullets

Every claim below is true of the code as written. **No invented metrics.**

> **AI Codebase Assistant** — *Python, FastAPI, LangChain, ChromaDB, React*
>
> - Built an AI assistant that indexes GitHub repositories using
>   **Retrieval-Augmented Generation (RAG)**, enabling natural-language question
>   answering over unfamiliar codebases.
> - Implemented semantic search with **sentence-transformer embeddings** and
>   **ChromaDB**, using language-aware chunking to retrieve relevant code and
>   generate grounded, source-cited explanations.
> - Exposed the system via a **FastAPI** REST backend and a **React** frontend
>   that surfaces retrieved chunks and similarity scores, making retrieval
>   quality auditable.

**If you want real numbers**, measure them yourself — don't invent them:
- `files_indexed` and `chunks_created` are returned by `/index`. Run it on a repo and record the real values.
- Time an `/ask` call with `curl -w "%{time_total}"`.
- For retrieval accuracy: write 20 questions where you *know* the correct file, then check how often it appears in the top-5 sources. That's **recall@5**, and it's a real, defensible metric.

---

## Final Checklist

Before you claim this project in an interview, be able to answer:

- [ ] Why does RAG exist? (Model never saw your code.)
- [ ] Why chunk? (Two reasons: context window *and* retrieval precision.)
- [ ] Why overlap? (Functions straddle boundaries.)
- [ ] Why cosine and not Euclidean? (Angle, not magnitude.)
- [ ] Why the same embedding model for index and query? (Same vector space.)
- [ ] RAG vs fine-tuning? (Facts vs form.)
- [ ] Your answer is wrong — retrieval failure or generation failure? (Check the Sources panel.)
- [ ] Why no agent? (Complexity buys nothing; user already knows what to click.)
- [ ] What's the security hole in `GET /file`? (Path traversal — and you fixed it.)
- [ ] What would you improve next? (AST chunking, re-ranking, an eval set.)

That last one matters. **Knowing the limitations of your own project is the
strongest signal you can give.**
