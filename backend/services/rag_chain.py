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

# Global cache - build the LLM client once, not per request.
_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    """Return the shared LLM client, creating it on first use."""
    global _llm

    if _llm is None:
        if not config.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Copy .env.example to .env and "
                "paste your key from https://aistudio.google.com/apikey"
            )

        _llm = ChatGoogleGenerativeAI(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            google_api_key=config.GOOGLE_API_KEY,
        )

    return _llm


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


def ask(repo_name: str, question: str, top_k: int | None = None) -> RagAnswer:
    """
    Run the full RAG pipeline for one question.

    This is the function the POST /ask route calls.
    """
    # 1. RETRIEVE - semantic search over the indexed chunks
    chunks = search(repo_name, question, top_k=top_k)

    # 2. AUGMENT - build the prompt with the retrieved code as context
    context = format_context(chunks)

    # 3. GENERATE - one LLM call
    # The '|' operator is LCEL (LangChain Expression Language). It pipes the
    # output of each step into the next:
    #     dict -> formatted prompt -> LLM -> plain string
    chain = prompt_template | get_llm() | StrOutputParser()

    answer = chain.invoke({"context": context, "question": question})

    return RagAnswer(answer=answer, sources=chunks)
