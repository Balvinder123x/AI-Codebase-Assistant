"""
RAG Chain
=========
The heart of the project. Retrieval-Augmented Generation:

    Question
       |
       v
    Embed the question
       |
       v
    Vector search  ->  top-K most relevant code chunks
       |
       v
    Stuff those chunks into a prompt as CONTEXT
       |
       v
    Send [system prompt + context + question] to the LLM
       |
       v
    Answer  (+ the sources we used, returned to the UI)

WHY RAG INSTEAD OF JUST ASKING THE LLM?
---------------------------------------
The LLM has never seen your repository. Its weights were frozen before your
code existed. Ask it "what does UserService.authenticate() do in my repo?"
and it will either say "I don't know" or - worse - HALLUCINATE a plausible
answer.

RAG fixes this by turning a knowledge problem into a reading-comprehension
problem. We do not ask the model to REMEMBER your code. We paste the
relevant code into the prompt and ask it to READ.

WHY NOT FINE-TUNE ON THE REPO INSTEAD?
--------------------------------------
Three reasons, and this is a classic interview question:
  1. Cost - fine-tuning is expensive; RAG is a vector search.
  2. Freshness - a new commit means retraining. With RAG you re-index in
     seconds.
  3. Attribution - RAG can show you WHICH file the answer came from.
     A fine-tuned model cannot cite its sources.

THIS IS THE "STUFF" STRATEGY
----------------------------
We stuff all retrieved chunks into one prompt and make ONE LLM call.
Simple, fast, cheap. Alternatives (map-reduce, refine) make one call per
chunk and are only needed when the context does not fit - not our case.
"""

from dataclasses import dataclass

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from services.vector_store import RetrievedChunk, search

# Cache of model-name -> client, so we build each client only once.
_llm_cache: dict[str, ChatGoogleGenerativeAI] = {}


def _build_llm(model_name: str) -> ChatGoogleGenerativeAI:
    """Build (and cache) a client for one specific model."""
    if model_name not in _llm_cache:
        if not config.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Copy .env.example to .env and "
                "paste your key from https://aistudio.google.com/apikey"
            )

        _llm_cache[model_name] = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=config.LLM_TEMPERATURE,
            google_api_key=config.GOOGLE_API_KEY,
        )

    return _llm_cache[model_name]


def get_llm() -> ChatGoogleGenerativeAI:
    """Return a client for the primary model."""
    return _build_llm(config.LLM_MODEL)


def _is_model_unavailable(exc: Exception) -> bool:
    """
    True if this error means "try a different model", as opposed to a bug we
    should surface.

    Covers:
      - 404: the model was retired (e.g. gemini-2.0-flash after 3 Mar 2026)
      - 429: rate limited, OR quota_value: 0 which ALSO means retired
      - 503: model temporarily overloaded
    """
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("429", "404", "503", "quota", "not found", "overloaded")
    )


# ---------------------------------------------------------------------------
# THE PROMPT
# ---------------------------------------------------------------------------
# This is the single highest-leverage piece of text in the project. Note the
# explicit instructions:
#
#   - "ONLY the code context below"    -> reduces hallucination
#   - "say so honestly"                -> gives the model permission to fail,
#                                         which is what stops it inventing
#   - "cite the file path"             -> makes answers verifiable
#
# Without the honesty clause, an LLM will confidently invent a function that
# does not exist, because its training objective rewards plausible text, not
# truthful text.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert software engineer helping a developer \
understand an unfamiliar codebase.

Answer the developer's question using ONLY the code context provided below.

Rules:
- If the context does not contain enough information to answer, say so \
honestly. Do NOT invent functions, files, or behaviour that is not shown.
- Cite the file path when you refer to specific code.
- Be concise and concrete. Prefer short explanations over long ones.
- Use markdown. Put code in fenced code blocks.

--- CODE CONTEXT ---
{context}
--- END CONTEXT ---"""

USER_PROMPT = "{question}"

prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]
)


def format_context(chunks: list[RetrievedChunk]) -> str:
    """
    Turn retrieved chunks into a single string for the prompt.

    We label each chunk with its file path so the LLM can cite sources.
    Without the labels the model sees one undifferentiated blob of code and
    cannot tell you where anything lives.
    """
    if not chunks:
        return "(No relevant code was found in this repository.)"

    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[Source {i}] File: {chunk.file_path}\n"
            f"```{chunk.language}\n{chunk.text}\n```"
        )

    return "\n\n".join(blocks)


@dataclass
class RagAnswer:
    """What the /ask route returns: the answer plus the sources behind it."""

    answer: str
    sources: list[RetrievedChunk]
    model_used: str  # which model actually produced this (may be a fallback)


def ask(repo_name: str, question: str, top_k: int | None = None) -> RagAnswer:
    """
    Run the full RAG pipeline for one question.

    This is the function the POST /ask route calls.
    """
    # 1. RETRIEVE - semantic search over the indexed chunks
    chunks = search(repo_name, question, top_k=top_k)

    # 2. AUGMENT - build the prompt with the retrieved code as context
    context = format_context(chunks)

    # 3. GENERATE - try the primary model, then each fallback in turn.
    #
    # WHY A FALLBACK CHAIN?
    # Google retires models. gemini-2.0-flash was killed on 3 Mar 2026 and
    # started returning "429 ... limit: 0" - a confusing error that looks like
    # a quota problem but actually means the model is gone. With a single
    # hardcoded model, that one deprecation takes the entire app down.
    #
    # Walking a list means the app degrades to the next model instead of
    # dying. This is the same reasoning behind retrying embeddings on 429:
    # depend on a remote service, plan for it being unavailable.
    models_to_try = [config.LLM_MODEL, *config.LLM_FALLBACK_MODELS]
    last_error: Exception | None = None

    for model_name in models_to_try:
        try:
            # LCEL: the '|' operator pipes each step into the next.
            #     dict -> formatted prompt -> LLM -> plain string
            chain = prompt_template | _build_llm(model_name) | StrOutputParser()
            answer = chain.invoke({"context": context, "question": question})

            if model_name != config.LLM_MODEL:
                print(f"[llm] primary unavailable; answered with {model_name}")

            return RagAnswer(
                answer=answer, sources=chunks, model_used=model_name
            )

        except Exception as exc:
            last_error = exc

            # A missing API key will fail on EVERY model - surface it now
            # rather than making the user wait through the whole chain.
            if isinstance(exc, ValueError):
                raise

            if not _is_model_unavailable(exc):
                raise  # a real bug, not a dead/limited model

            print(f"[llm] {model_name} unavailable, trying next fallback...")

    raise RuntimeError(
        "All Gemini models are currently unavailable or rate limited "
        f"(tried: {', '.join(models_to_try)}). Free-tier daily quotas reset "
        "at midnight Pacific time. Please try again later."
    ) from last_error
