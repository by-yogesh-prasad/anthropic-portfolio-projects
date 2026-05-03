"""RAG pipeline: embed question → retrieve context → stream Claude answer."""

import logging
import os
from typing import Any, Dict, Generator, List, Optional

import anthropic
from dotenv import load_dotenv

from embeddings import get_embedding
from vector_store import search

load_dotenv()

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_CONTEXT_CHUNKS = 5
MAX_TOKENS = 1024

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Return (or lazily create) the Anthropic client."""
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in environment variables.")
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _build_system_prompt() -> str:
    """Return the system prompt for the RAG assistant."""
    return (
        "You are an expert assistant for Anthropic's documentation. "
        "You have access to a pre-indexed knowledge base of ~87 Anthropic documentation pages "
        "from platform.claude.com/docs, covering topics such as models, APIs, tool use, "
        "prompt engineering, agents, vision, files, streaming, and more. "
        "When a user asks a question, the most relevant excerpts from that knowledge base "
        "are retrieved and provided to you as context below. "
        "Answer questions accurately using only the provided context excerpts. "
        "If the context does not contain enough information to fully answer the question, "
        "say so clearly and suggest the user visit platform.claude.com/docs for the full reference. "
        "Do not claim you cannot access documentation — the documentation has already been "
        "retrieved and is provided in the context. "
        "Always be concise and factual."
    )


def _build_user_prompt(question: str, context_chunks: List[Dict[str, Any]]) -> str:
    """Assemble the user turn containing retrieved context + question.

    Args:
        question: The user's original question.
        context_chunks: Retrieved chunks from ChromaDB search results.

    Returns:
        Formatted prompt string.
    """
    context_blocks = []
    for i, chunk in enumerate(context_chunks, start=1):
        source = chunk["metadata"].get("source", "unknown")
        title = chunk["metadata"].get("title", "Untitled")
        context_blocks.append(
            f"[Source {i}] {title}\nURL: {source}\n\n{chunk['document']}"
        )

    context_text = "\n\n---\n\n".join(context_blocks)

    return (
        f"Use the following documentation excerpts to answer the question.\n\n"
        f"{context_text}\n\n"
        f"---\n\n"
        f"Question: {question}"
    )


def retrieve_chunks(question: str, top_k: int = MAX_CONTEXT_CHUNKS) -> List[Dict[str, Any]]:
    """Embed the question and retrieve the most relevant chunks.

    Args:
        question: The user's question string.
        top_k: Number of chunks to retrieve.

    Returns:
        List of chunk dicts from ChromaDB (id, document, metadata, distance).

    Raises:
        RuntimeError: If embedding or retrieval fails.
    """
    query_embedding = get_embedding(question)
    return search(query_embedding, top_k=top_k)


def extract_citations(chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Build a deduplicated list of source citations from retrieved chunks.

    Args:
        chunks: ChromaDB search result dicts.

    Returns:
        List of citation dicts with url and title, deduplicated by URL.
    """
    seen_urls: set[str] = set()
    citations: List[Dict[str, str]] = []
    for chunk in chunks:
        url = chunk["metadata"].get("source", "")
        title = chunk["metadata"].get("title", "Untitled")
        if url and url not in seen_urls:
            seen_urls.add(url)
            citations.append({"url": url, "title": title})
    return citations


def stream_answer(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Full RAG pipeline yielding streaming tokens then a final citations event.

    Yields dicts of shape:
      - {"type": "token",     "content": "<text>"}      — one per streamed token
      - {"type": "citations", "citations": [...]}        — final event
      - {"type": "error",     "message": "<msg>"}        — on failure

    Args:
        question: The user's natural-language question.
        history: Previous conversation turns as [{role, content}, ...].
    """
    history_len = len(history) if history else 0
    logger.info("Question: %r  (history_turns=%d)", question, history_len)

    try:
        chunks = retrieve_chunks(question)
    except Exception as e:
        logger.error("Retrieval failed for question %r: %s", question, e)
        yield {"type": "error", "message": f"Retrieval failed: {e}"}
        return

    logger.info("Retrieved %d chunks:", len(chunks))
    for i, chunk in enumerate(chunks, start=1):
        source = chunk["metadata"].get("source", "unknown")
        title = chunk["metadata"].get("title", "Untitled")
        distance = chunk.get("distance", -1)
        logger.info(
            "  [%d] dist=%.4f  title=%r  source=%s",
            i, distance, title, source,
        )

    citations = extract_citations(chunks)
    user_prompt = _build_user_prompt(question, chunks)
    client = _get_client()

    messages: List[Dict[str, str]] = list(history or [])
    messages.append({"role": "user", "content": user_prompt})

    logger.info("Streaming answer from %s (max_tokens=%d)", MODEL, MAX_TOKENS)
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(),
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield {"type": "token", "content": text}
    except anthropic.APIError as e:
        logger.error("Claude API error for question %r: %s", question, e)
        yield {"type": "error", "message": f"Claude API error: {e}"}
        return

    logger.info("Stream complete — %d citation(s) returned", len(citations))
    yield {"type": "citations", "citations": citations}


def answer(question: str) -> Dict[str, Any]:
    """Non-streaming RAG query — returns full answer + citations at once.

    Args:
        question: The user's question.

    Returns:
        Dict with keys: answer (str), citations (list), chunks_used (int).
    """
    chunks = retrieve_chunks(question)
    citations = extract_citations(chunks)
    user_prompt = _build_user_prompt(question, chunks)
    client = _get_client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_build_system_prompt(),
        messages=[{"role": "user", "content": user_prompt}],
    )

    answer_text = response.content[0].text if response.content else ""
    return {
        "answer": answer_text,
        "citations": citations,
        "chunks_used": len(chunks),
    }
