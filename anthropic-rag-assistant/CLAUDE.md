# Anthropic RAG Assistant

## Project Overview
Enterprise knowledge base RAG application that answers questions over Anthropic's
documentation using retrieval-augmented generation with streaming responses,
multi-turn conversation history, and markdown-rendered output.

## Tech Stack
- Backend: FastAPI (Python 3.11+)
- Frontend: React 18 + TypeScript + Tailwind CSS + Vite
- Markdown: react-markdown + remark-gfm + @tailwindcss/typography
- Vector DB: ChromaDB (local, persistent, threading.RLock for thread safety)
- Embeddings: OpenAI `text-embedding-3-small` via direct HTTP (no SDK)
- LLM: Claude `claude-sonnet-4-6` via Anthropic API (streaming, multi-turn history)
- Scraping: Playwright headless Chromium in isolated subprocess per page
- Data source: platform.claude.com/docs (~87 narrative pages via sitemap)

## Project Structure
```
anthropic-rag-assistant/
├── backend/
│   ├── main.py              # FastAPI — auth, rate limiting, background jobs
│   ├── ingest.py            # Sitemap → scrape → chunk → embed → store
│   ├── rag.py               # RAG pipeline + Claude streaming + conversation history
│   ├── vector_store.py      # ChromaDB CRUD + RLock + reset_collection()
│   ├── embeddings.py        # OpenAI embeddings via HTTP
│   ├── scraper_worker.py    # Standalone Playwright worker invoked as subprocess per page
│   ├── requirements.txt
│   ├── Dockerfile           # Based on mcr.microsoft.com/playwright/python
│   └── .dockerignore
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # SSE streaming, conversation history, ingest polling, auth headers
│   │   ├── types.ts         # Shared TS types (Message, IngestJobStatus, SSEEvent)
│   │   ├── vite-env.d.ts    # Vite ImportMeta env declarations
│   │   └── components/
│   │       ├── ChatWindow.tsx
│   │       ├── MessageBubble.tsx    # Renders assistant content via react-markdown
│   │       ├── SourceCitation.tsx
│   │       └── InputBar.tsx
│   ├── index.html
│   ├── nginx.conf           # Proxies /chat /ingest /health /stats → backend
│   ├── vite.config.ts       # Dev proxy → :8000
│   ├── tailwind.config.js   # Includes @tailwindcss/typography plugin
│   ├── Dockerfile           # Multi-stage: node build → nginx serve
│   ├── .dockerignore
│   └── package.json
├── data/
│   ├── docs/                # Optional raw content cache
│   └── chroma_db/           # ChromaDB vectors — gitignored, Docker named volume
├── docker-compose.yml
├── .env.example
├── .gitignore
├── CLAUDE.md
└── README.md
```

## Environment Variables
```
ANTHROPIC_API_KEY=     # console.anthropic.com
OPENAI_API_KEY=        # platform.openai.com/api-keys  (embeddings only)
RAG_API_KEY=           # protects /chat + /ingest; leave blank to disable auth
ALLOWED_ORIGINS=       # comma-separated CORS origins (default: localhost)
```
Frontend build-time variable (Vite):
```
VITE_API_KEY=          # same value as RAG_API_KEY — sent as X-API-Key header
```

## API Endpoints
| Method | Path                    | Auth | Type  | Description                           |
|--------|-------------------------|------|-------|---------------------------------------|
| GET    | /health                 | no   | sync  | Liveness + ChromaDB + key checks      |
| GET    | /stats                  | no   | sync  | ChromaDB collection stats             |
| POST   | /ingest                 | yes  | sync  | Queue background ingest job           |
| GET    | /ingest/status/{job_id} | yes  | async | Poll job: queued→running→completed    |
| POST   | /chat                   | yes  | async | SSE stream: token/citations/error     |

**Auth:** `X-API-Key: <RAG_API_KEY>` header. Skipped when `RAG_API_KEY` unset.

**Rate limiting:** `/chat` — 10 req/min per key (or IP). In-process sliding window.
Replace with Redis-backed limiter for multi-replica deployments.

**IMPORTANT:** `/health` and `/stats` are `def` (sync), not `async def`. They call
synchronous ChromaDB/SQLite functions. If they were async, they would block the
asyncio event loop while the ingest thread holds the SQLite write lock, causing health
check timeouts even when the server is healthy.

## Ingest Background Jobs
`POST /ingest` returns immediately: `{"job_id": "...", "status": "queued"}`.
Work runs in a daemon thread. Poll `GET /ingest/status/{job_id}` for progress.
States: `queued` → `running` → `completed` | `failed`.

### IngestRequest flags
| Flag          | Default | Effect                                               |
|---------------|---------|------------------------------------------------------|
| `use_sitemap` | `true`  | Pull URLs from sitemap (~87 narrative pages)         |
| `include_api` | `false` | Also ingest /api/* reference pages (~1,188 extra)    |
| `urls`        | `null`  | Override with explicit URL list                      |
| `reset`       | `false` | Drop and recreate ChromaDB collection first          |

## RAG Pipeline
1. `get_sitemap_urls()` fetches `platform.claude.com/docs/sitemap.xml`, filters to
   `/docs/en/*`, excludes `/api/*` by default (~87 pages)
2. Each page is scraped by spawning `scraper_worker.py` as a subprocess. Chromium runs
   inside the child process — an OOM kill terminates only the child, not uvicorn.
   Plain HTTP returns a `Loading...` skeleton because the docs are a Mintlify React SPA.
3. `inner_text` extracted from `<main>` selector
4. tiktoken `cl100k_base` splits into 500-token chunks with 50-token overlap
5. Batch-embed with OpenAI `text-embedding-3-small` (1536 dims, batches of 100)
6. Upsert into ChromaDB (cosine similarity, idempotent — IDs are deterministic)
7. At query time: embed question → retrieve top 5 chunks by cosine distance
8. Prompt = system instructions + context blocks + question. Prior conversation turns
   are prepended as messages so Claude has multi-turn context.
9. Stream tokens as SSE `token` events → final `citations` event → `[DONE]`
10. Frontend renders assistant content through `react-markdown` (GFM enabled) so
    headings, bold, lists, and code blocks display correctly during streaming.

## Key Design Decisions
- **Subprocess-isolated Playwright**: each page scrape runs `scraper_worker.py` via
  `subprocess.run()`. If Chromium OOMs, only the child process dies — uvicorn stays
  alive and the ingest loop catches the exception and continues to the next URL.
- **Sync `/health` and `/stats` endpoints**: blocking ChromaDB/SQLite calls must not
  run on the asyncio event loop. `def` (not `async def`) makes FastAPI run them in a
  thread-pool executor. Previously `async def` caused event loop blocking when the
  ingest thread held the SQLite write lock, making the container appear unhealthy.
- **`threading.RLock` on ChromaDB**: the ingest daemon thread and health/stats thread
  pool threads both access `_collection`. A plain `Lock` would deadlock because
  `_ensure_collection()` calls `init_collection()`, which also acquires the lock.
  An RLock (reentrant) lets the same thread re-enter without deadlocking.
- **Conversation history**: `POST /chat` accepts a `history` field
  (`[{role, content}, ...]`). The frontend snapshots completed messages before each
  submit and sends them. Claude receives history + current user prompt (with retrieved
  context) so follow-up questions work correctly.
- **Markdown rendering**: assistant content is rendered through `react-markdown` with
  `remark-gfm`. Raw `**bold**` and `## headings` in Claude's output display as
  formatted text rather than literal punctuation.
- **OpenAI embeddings over Voyage AI**: Voyage hit 429 rate limits at low volume.
  OpenAI has much higher limits and near-identical HTTP response shape.
- **Single uvicorn worker**: daemon threads and the `_jobs` dict are in-process
  state. Multiple workers = separate processes = broken job tracking. If you need
  horizontal scale, replace with Celery + Redis.
- **`reset_collection()`**: ChromaDB binds embedding dimensions on first write.
  Switching models requires a reset. Use `POST /ingest {"reset": true}`.
- **Upsert not insert**: re-ingesting the same URL is safe and idempotent.
- **Sitemap-driven URL discovery**: avoids maintaining a hardcoded URL list.
  Falls back to `TARGET_URLS` if sitemap is unreachable.

## ChromaDB Notes
- Local path: `data/chroma_db/` (gitignored)
- Docker: named volume `chroma_data` mounted at `/data/chroma_db`
- Collection: `anthropic_docs`, cosine similarity, 1536 dims
- Dimension mismatch: delete `data/chroma_db/` or `POST /ingest {"reset": true}`
- All reads/writes wrapped in `threading.RLock` — safe for concurrent ingest + health threads

## Running Locally (dev)
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp ../.env.example ../.env   # fill in ANTHROPIC_API_KEY, OPENAI_API_KEY
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend && npm install && npm run dev   # → http://localhost:3000

# Trigger first ingest (auth disabled when RAG_API_KEY is unset)
curl -X POST http://localhost:8000/ingest -H "Content-Type: application/json" -d '{}'
```

## Running with Docker
```bash
cp .env.example .env          # fill in all keys including RAG_API_KEY
docker compose up --build     # backend: :8000 · frontend: :3000

# First-time ingest
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: <RAG_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{}'

# Full ingest including API reference pages (~1,275 total)
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: <RAG_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"include_api": true, "reset": true}'
```

## Coding Standards
- Python: type hints on all functions, docstrings on all public functions/classes
- Use `logging.getLogger(__name__)` — no `print()` statements
- Always handle errors with try/except; re-raise as RuntimeError with context
- FastAPI endpoints must have Pydantic response models
- React components must be fully typed with TypeScript
- All API calls must handle loading and error states in the UI
