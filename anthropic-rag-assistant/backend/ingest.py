"""Data ingestion pipeline: scrape → chunk → embed → store."""

import json
import logging
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import requests
import tiktoken
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from embeddings import get_embeddings_batch
from vector_store import add_documents, get_collection_stats, init_collection, reset_collection

load_dotenv()

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
ENCODING_NAME = "cl100k_base"

SITEMAP_URL = "https://platform.claude.com/docs/sitemap.xml"

# Fallback used only when sitemap is unreachable
TARGET_URLS: List[str] = [
    "https://platform.claude.com/docs/en/intro",
    "https://platform.claude.com/docs/en/get-started",
    "https://platform.claude.com/docs/en/build-with-claude/overview",
    "https://platform.claude.com/docs/en/build-with-claude/prompt-caching",
    "https://platform.claude.com/docs/en/build-with-claude/streaming",
    "https://platform.claude.com/docs/en/build-with-claude/extended-thinking",
    "https://platform.claude.com/docs/en/build-with-claude/vision",
    "https://platform.claude.com/docs/en/build-with-claude/files",
    "https://platform.claude.com/docs/en/build-with-claude/context-windows",
    "https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview",
    "https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works",
    "https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools",
    "https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls",
    "https://platform.claude.com/docs/en/agents-and-tools/remote-mcp-servers",
    "https://platform.claude.com/docs/en/managed-agents/overview",
]

_encoder = tiktoken.get_encoding(ENCODING_NAME)


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def get_sitemap_urls(include_api: bool = False) -> List[str]:
    """Fetch all English documentation URLs from the Anthropic sitemap.

    Args:
        include_api: If True, also include /api/* reference pages (~1,188 URLs).
                     Default False — those pages have repetitive endpoint schemas
                     that dilute retrieval quality for narrative questions.

    Returns:
        Sorted list of unique documentation URLs.

    Raises:
        RuntimeError: If the sitemap cannot be fetched or parsed.
    """
    try:
        resp = requests.get(SITEMAP_URL, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch sitemap: {e}") from e

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise RuntimeError(f"Failed to parse sitemap XML: {e}") from e

    # Sitemap uses the sitemaps.org namespace
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text.strip() for el in root.findall(".//sm:loc", ns) if el.text]

    urls = []
    for url in locs:
        if "/docs/en/" not in url:
            continue
        if not include_api and "/docs/en/api/" in url:
            continue
        urls.append(url)

    logger.info("Sitemap: found %d English doc URLs (include_api=%s)", len(urls), include_api)
    return sorted(set(urls))


# ---------------------------------------------------------------------------
# Scraping — each page runs Chromium in an isolated subprocess
# ---------------------------------------------------------------------------

_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper_worker.py")


def scrape_page(url: str) -> Tuple[str, str]:
    """Render a docs page in a subprocess and return (title, clean_text).

    Playwright/Chromium runs in a child process so an OOM kill only terminates
    that child — the uvicorn server process stays alive and healthy.

    Args:
        url: The URL to scrape.

    Returns:
        Tuple of (page_title, extracted_plain_text).

    Raises:
        RuntimeError: If the subprocess fails or times out.
    """
    try:
        proc = subprocess.run(
            [sys.executable, _WORKER, url],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Scraper subprocess timed out for {url}")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Scraper subprocess exited {proc.returncode} for {url}: "
            f"{proc.stderr[-400:].strip()}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from scraper for {url}: {exc}") from exc

    return data["title"], data["text"]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """Split text into token-bounded chunks with overlap.

    Args:
        text: Plain text to split.
        chunk_size: Maximum tokens per chunk.
        overlap: Number of tokens to repeat at the start of the next chunk.

    Returns:
        List of text chunk strings.
    """
    tokens = _encoder.encode(text)
    chunks: List[str] = []
    start = 0

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(_encoder.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def ingest_url(url: str) -> Dict[str, Any]:
    """Scrape, chunk, embed, and store a single documentation page.

    Args:
        url: The documentation page URL to ingest.

    Returns:
        Dict with url, title, num_chunks.
    """
    logger.info("Scraping: %s", url)
    title, text = scrape_page(url)
    logger.info("  Title: %r  |  chars: %d", title, len(text))

    chunks = chunk_text(text)
    logger.info("  Chunks: %d", len(chunks))

    embeddings = get_embeddings_batch(chunks)

    metadata = [
        {"source": url, "title": title, "chunk_index": i, "total_chunks": len(chunks)}
        for i in range(len(chunks))
    ]

    add_documents(chunks=chunks, embeddings=embeddings, metadata=metadata)
    logger.info("  Stored %d documents", len(chunks))

    return {"url": url, "title": title, "num_chunks": len(chunks)}


def run_ingestion(
    urls: Optional[List[str]] = None,
    use_sitemap: bool = True,
    include_api: bool = False,
    reset: bool = False,
) -> Dict[str, Any]:
    """Run the full ingestion pipeline.

    URL resolution order:
      1. Explicit ``urls`` list (if provided)
      2. Sitemap fetch (if ``use_sitemap=True``)
      3. ``TARGET_URLS`` fallback (if sitemap is unreachable)

    Args:
        urls: Explicit list of URLs to ingest (overrides sitemap).
        use_sitemap: Fetch the full URL list from the Anthropic sitemap.
        include_api: Include /api/* reference pages (~1,188 extra URLs).
                     Only applies when use_sitemap=True.
        reset: Drop and recreate the ChromaDB collection before ingesting.

    Returns:
        Summary dict with per-page results and totals.
    """
    if reset:
        logger.info("Resetting ChromaDB collection")
        reset_collection()
    else:
        init_collection()

    # Resolve the URL list
    if urls:
        target = urls
        logger.info("Using %d explicitly provided URLs", len(target))
    elif use_sitemap:
        try:
            target = get_sitemap_urls(include_api=include_api)
            logger.info("Sitemap resolved %d URLs", len(target))
        except RuntimeError as e:
            logger.warning("Sitemap unavailable (%s) — falling back to TARGET_URLS", e)
            target = TARGET_URLS
    else:
        target = TARGET_URLS
        logger.info("Using %d fallback TARGET_URLS", len(target))

    results = []
    total_chunks = 0
    errors = []

    for i, url in enumerate(target, start=1):
        logger.info("[%d/%d] %s", i, len(target), url)
        try:
            result = ingest_url(url)
            results.append(result)
            total_chunks += result["num_chunks"]
            time.sleep(0.5)  # polite delay between pages
        except Exception:
            logger.exception("Failed to ingest %s", url)
            errors.append({"url": url, "error": "see server logs"})

    stats = get_collection_stats()
    summary = {
        "pages_processed": len(results),
        "pages_failed": len(errors),
        "total_chunks_added": total_chunks,
        "collection_stats": stats,
        "results": results,
        "errors": errors,
    }
    logger.info("Ingestion complete: %d/%d pages, %d chunks", len(results), len(target), total_chunks)
    return summary


if __name__ == "__main__":
    summary = run_ingestion()
    print(json.dumps(summary, indent=2))
