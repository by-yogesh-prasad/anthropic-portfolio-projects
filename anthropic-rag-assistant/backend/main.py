"""FastAPI application for the Anthropic RAG assistant."""

import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests as http_requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ingest import run_ingestion
from rag import stream_answer
from vector_store import get_collection_stats, init_collection

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAG_API_KEY = os.getenv("RAG_API_KEY", "")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Anthropic RAG Assistant",
    description="Enterprise knowledge base over Anthropic documentation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def verify_api_key(x_api_key: str = Header(default="")) -> str:
    """Validate X-API-Key header.

    Auth is skipped entirely when RAG_API_KEY is not configured (local dev).
    """
    if RAG_API_KEY and x_api_key != RAG_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")
    return x_api_key

# ---------------------------------------------------------------------------
# Rate limiting (sliding window, in-process)
# ---------------------------------------------------------------------------

class _SlidingWindowLimiter:
    """Thread-safe sliding window rate limiter.

    NOTE: in-process only — does not coordinate across multiple server instances.
    Replace with a Redis-backed implementation for multi-replica deployments.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            bucket = [t for t in self._buckets[key] if now - t < self.window]
            self._buckets[key] = bucket
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True


_chat_limiter = _SlidingWindowLimiter(max_requests=10, window_seconds=60)

# ---------------------------------------------------------------------------
# Background job registry
# ---------------------------------------------------------------------------

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _run_ingest_job(
    job_id: str,
    urls: Optional[List[str]],
    use_sitemap: bool,
    include_api: bool,
    reset: bool,
) -> None:
    """Worker function executed in a daemon thread for background ingestion."""
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        summary = run_ingestion(
            urls=urls,
            use_sitemap=use_sitemap,
            include_api=include_api,
            reset=reset,
        )
        with _jobs_lock:
            _jobs[job_id].update(
                {
                    "status": "completed",
                    "pages_processed": summary["pages_processed"],
                    "pages_failed": summary["pages_failed"],
                    "total_chunks_added": summary["total_chunks_added"],
                }
            )
    except Exception:
        logger.exception("Ingest job %s failed", job_id)
        import traceback
        with _jobs_lock:
            _jobs[job_id].update(
                {"status": "failed", "error": traceback.format_exc()}
            )
    finally:
        with _jobs_lock:
            _jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    """A single turn in the conversation history."""

    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""

    question: str = Field(..., min_length=1, max_length=2000)
    history: List[HistoryMessage] = Field(default_factory=list)


class Citation(BaseModel):
    url: str
    title: str


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    urls: Optional[List[str]] = Field(
        default=None,
        description="Explicit URL list. Overrides use_sitemap when provided.",
    )
    use_sitemap: bool = Field(
        default=True,
        description="Fetch all English doc URLs from the Anthropic sitemap (~87 pages). "
                    "Ignored when urls is provided.",
    )
    include_api: bool = Field(
        default=False,
        description="Also ingest /api/* reference pages (~1,188 extra URLs). "
                    "Only applies when use_sitemap=True.",
    )
    reset: bool = Field(
        default=False,
        description="Drop and recreate the collection before ingesting.",
    )


class IngestJobQueued(BaseModel):
    """Immediate response when an ingest job is accepted."""

    job_id: str
    status: str = "queued"
    message: str


class IngestJobStatus(BaseModel):
    """Full status of an ingest job — returned by GET /ingest/status/{job_id}."""

    job_id: str
    status: str
    queued_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    pages_processed: Optional[int] = None
    pages_failed: Optional[int] = None
    total_chunks_added: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: Dict[str, str]


class StatsResponse(BaseModel):
    collection_name: str
    total_documents: int
    storage_path: str


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    """Initialize ChromaDB collection on server start."""
    init_collection()
    logger.info("ChromaDB collection initialised")
    if not RAG_API_KEY:
        logger.warning("RAG_API_KEY is not set — API auth is disabled")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Health check — verifies ChromaDB is accessible and API keys are configured.

    Defined as sync so FastAPI runs it in a thread-pool executor. Calling
    synchronous ChromaDB/SQLite operations from an async handler would block
    the event loop and cause all health checks to fail during ingest.
    """
    checks: Dict[str, str] = {}

    try:
        stats = get_collection_stats()
        checks["chromadb"] = f"ok ({stats['total_documents']} docs)"
    except Exception as e:
        checks["chromadb"] = f"error: {e}"

    checks["anthropic_key"] = "set" if os.getenv("ANTHROPIC_API_KEY") else "missing"
    checks["openai_key"] = "set" if os.getenv("OPENAI_API_KEY") else "missing"

    overall = "ok" if all(not v.startswith("error") and v != "missing" for v in checks.values()) else "degraded"

    return HealthResponse(status=overall, version="1.0.0", checks=checks)


@app.get("/stats", response_model=StatsResponse, tags=["system"])
def stats() -> StatsResponse:
    """Return ChromaDB collection statistics.

    Sync so the blocking ChromaDB call runs in a thread pool, not the event loop.
    """
    try:
        data = get_collection_stats()
        return StatsResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest", response_model=IngestJobQueued, tags=["admin"])
def ingest(
    request: IngestRequest,
    _key: str = Depends(verify_api_key),
) -> IngestJobQueued:
    """Queue a background ingestion job and return immediately.

    Poll GET /ingest/status/{job_id} for progress.
    Defined as sync so FastAPI runs it in a thread-pool executor — this avoids
    asyncio event-loop conflicts with Playwright's sync API.
    """
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }

    thread = threading.Thread(
        target=_run_ingest_job,
        args=(job_id, request.urls, request.use_sitemap, request.include_api, request.reset),
        daemon=True,
    )
    thread.start()

    source = "explicit URLs" if request.urls else ("sitemap" if request.use_sitemap else "fallback list")
    logger.info("Ingest job %s queued (source=%s, reset=%s)", job_id, source, request.reset)

    return IngestJobQueued(
        job_id=job_id,
        message=f"Ingestion queued (source: {source}). Poll /ingest/status/{job_id} for progress.",
    )


@app.get("/ingest/status/{job_id}", response_model=IngestJobStatus, tags=["admin"])
async def ingest_status(
    job_id: str,
    _key: str = Depends(verify_api_key),
) -> IngestJobStatus:
    """Return the current status of an ingest job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return IngestJobStatus(job_id=job_id, **job)


@app.post("/chat", tags=["chat"])
async def chat(
    request: ChatRequest,
    req: Request,
    _key: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Stream a RAG answer for the given question (SSE).

    Rate limited to 10 requests per minute per API key (or IP when key auth is off).
    """
    rate_key = _key or req.client.host or "anonymous"
    if not _chat_limiter.check(rate_key):
        logger.warning("Rate limit exceeded for key/ip %r", rate_key)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded: 10 requests per minute.",
        )

    history = [{"role": m.role, "content": m.content} for m in request.history]

    def event_generator():
        for event in stream_answer(request.question, history=history):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
