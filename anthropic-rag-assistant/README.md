# Anthropic RAG Assistant

An enterprise-grade Retrieval-Augmented Generation (RAG) knowledge base that answers
questions over Anthropic's official documentation in real time, with streaming responses,
multi-turn conversation history, and source citations.

---

## Architecture

```
User Question
      │
      ▼
┌─────────────┐     POST /chat (SSE)      ┌──────────────────────────────────────┐
│  React UI   │ ──────────────────────►  │          FastAPI Backend              │
│  (Vite +    │ ◄── token stream (SSE) ─  │                                      │
│  Tailwind)  │                           │  1. Embed question  (OpenAI)         │
└─────────────┘                           │  2. Retrieve top-5 chunks (ChromaDB) │
                                          │  3. Build prompt with context        │
      │                                   │  4. Stream answer   (Claude)         │
      │  POST /ingest → job_id            │  5. Return citations                 │
      │  GET  /ingest/status/{id} ──────► └──────────────┬───────────────────────┘
      │  (polls until done)                              │
      └──────────────────────────────────────────────────┘
                                                         │
                   ┌─────────────────────────────────────┼──────────────────────┐
                   ▼                                     ▼                      ▼
         ┌──────────────────┐             ┌─────────────────────┐  ┌────────────────────┐
         │   OpenAI API     │             │      ChromaDB       │  │   Anthropic API    │
         │ text-embed-3-sm  │             │  cosine similarity  │  │  claude-sonnet-4-6 │
         │   (1536 dims)    │             │  persistent on disk │  │    SSE streaming   │
         └──────────────────┘             └─────────────────────┘  └────────────────────┘
```

### Ingestion Pipeline

```
platform.claude.com/docs/sitemap.xml
             │
             ▼ get_sitemap_urls()
   ~87 English doc pages
   (or ~1,275 with include_api=true)
             │
             ▼
   scraper_worker.py subprocess
   (isolated Playwright Chromium per page;
    OOM kills only the child, not uvicorn)
             │
             ▼
   tiktoken cl100k_base chunking
   (500 tokens, 50 token overlap)
             │
             ▼
   OpenAI text-embedding-3-small
   (batches of 100, 1536-dim vectors)
             │
             ▼
   ChromaDB upsert
   (cosine similarity, idempotent)
```

---

## Tech Stack

| Layer       | Technology                                                        |
|-------------|-------------------------------------------------------------------|
| Frontend    | React 18, TypeScript, Tailwind CSS, Vite                          |
| Markdown    | react-markdown, remark-gfm, @tailwindcss/typography               |
| Backend     | FastAPI, Python 3.11+, single uvicorn worker                      |
| Embeddings  | OpenAI `text-embedding-3-small` via direct HTTP                   |
| Vector DB   | ChromaDB (local persistent, cosine similarity, threading.RLock)   |
| LLM         | Anthropic `claude-sonnet-4-6` (streaming, multi-turn history)     |
| Scraping    | Playwright headless Chromium in isolated subprocess per page      |
| Chunking    | tiktoken `cl100k_base`                                            |
| Containers  | Docker + Docker Compose                                           |

---

## Features

- **Multi-turn conversation** — each request carries the full conversation history so follow-up questions like "can you elaborate?" work correctly
- **Streaming answers** — tokens stream to the UI via Server-Sent Events as Claude generates them
- **Markdown rendering** — headings, bold, bullet lists, inline code, and code blocks render properly in the assistant bubble
- **Source citations** — deduplicated source URLs and titles appear below each answer
- **Background ingestion** — `POST /ingest` returns immediately; actual scraping runs in a daemon thread with a polling status endpoint
- **Rate limiting** — 10 requests/minute per API key (sliding window, in-process)
- **Auth** — `X-API-Key` header; disabled when `RAG_API_KEY` is unset (local dev)
- **OOM-safe scraping** — each Playwright/Chromium instance runs in its own subprocess; a crash or OOM kill leaves uvicorn alive

---

## Project Structure

```
anthropic-rag-assistant/
├── backend/
│   ├── main.py              # FastAPI — auth, rate limiting, background ingest jobs
│   ├── rag.py               # RAG pipeline + Claude SSE streaming + conversation history
│   ├── ingest.py            # Sitemap → scrape → chunk → embed → store
│   ├── scraper_worker.py    # Standalone Playwright worker — run as subprocess per page
│   ├── vector_store.py      # ChromaDB CRUD + RLock thread safety + reset_collection()
│   ├── embeddings.py        # OpenAI HTTP client (no SDK)
│   ├── requirements.txt
│   ├── Dockerfile           # Based on official Playwright Python image
│   └── .dockerignore
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # SSE streaming, history, ingest polling, X-API-Key header
│   │   ├── types.ts             # Message, IngestJobStatus, SSEEvent, Citation
│   │   ├── vite-env.d.ts        # Vite env type declarations
│   │   └── components/
│   │       ├── ChatWindow.tsx       # Message list + suggested questions
│   │       ├── MessageBubble.tsx    # Markdown-rendered assistant bubbles + typing indicator
│   │       ├── SourceCitation.tsx   # Numbered source links
│   │       └── InputBar.tsx         # Auto-grow textarea, Enter to send
│   ├── index.html
│   ├── nginx.conf           # Reverse proxy + SSE-compatible settings
│   ├── vite.config.ts       # Dev proxy → :8000
│   ├── tailwind.config.js
│   ├── Dockerfile           # Multi-stage: Node build → nginx
│   └── package.json
├── data/
│   └── chroma_db/           # Persisted vectors (gitignored; Docker named volume)
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+  *(local dev only)*
- [Anthropic API key](https://console.anthropic.com)
- [OpenAI API key](https://platform.openai.com/api-keys) *(embeddings only)*

### Option A — Docker (recommended)

```bash
git clone <repo> && cd anthropic-rag-assistant
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, OPENAI_API_KEY, RAG_API_KEY, ALLOWED_ORIGINS
docker compose up --build
```

Backend → `http://localhost:8000` · Frontend → `http://localhost:3000`

Then trigger the first ingest (scrapes ~87 doc pages, takes ~15 min):

```bash
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: <your RAG_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Or click **Sync Docs** in the UI and watch the status banner.

### Option B — Local dev

```bash
# 1. Configure
cp .env.example .env   # fill in keys; leave RAG_API_KEY blank to skip auth

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload --port 8000

# 3. Frontend
cd frontend && npm install && npm run dev   # → http://localhost:3000

# 4. First ingest (auth disabled when RAG_API_KEY is unset)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" -d '{}'
```

---

## API Reference

| Method | Path                      | Auth | Description                                   |
|--------|---------------------------|------|-----------------------------------------------|
| GET    | `/health`                 | —    | Server + ChromaDB + API key status            |
| GET    | `/stats`                  | —    | ChromaDB collection statistics                |
| POST   | `/ingest`                 | ✓    | Queue background ingest job, returns job_id   |
| GET    | `/ingest/status/{job_id}` | ✓    | Poll ingest progress                          |
| POST   | `/chat`                   | ✓    | Stream RAG answer (SSE)                       |

**Auth:** `X-API-Key: <RAG_API_KEY>` header. Disabled when `RAG_API_KEY` is unset.

**Rate limit:** `/chat` — 10 requests/minute per key (or IP).

### POST /ingest — request body

```json
{
  "use_sitemap":  true,   // fetch all ~87 narrative pages from sitemap (default)
  "include_api":  false,  // also ingest ~1,188 /api/* reference pages
  "urls":         null,   // override with explicit URL list
  "reset":        false   // drop & recreate ChromaDB collection first
}
```

### POST /chat — request body

```json
{
  "question": "How does tool use work?",
  "history": [
    { "role": "user",      "content": "What is Claude?" },
    { "role": "assistant", "content": "Claude is..." }
  ]
}
```

`history` defaults to `[]` — omit it for single-turn queries.

### POST /chat — SSE event stream

```
data: {"type": "token",     "content": "Claude"}
data: {"type": "token",     "content": " is a..."}
data: {"type": "citations", "citations": [{"url": "...", "title": "..."}]}
data: [DONE]
```

---

## Example Queries

- *"What is Claude and what can it do?"*
- *"How do I get started with the Anthropic API?"*
- *"What are best practices for prompt engineering?"*
- *"How does tool use work? Show me the request format."*
- *"What is prompt caching and how does it reduce costs?"*
- *"How do I use extended thinking in Claude?"*
- *"What models does Anthropic offer and how do they differ?"*

---

## How It Works

1. **Sitemap discovery** — `get_sitemap_urls()` fetches `platform.claude.com/docs/sitemap.xml`
   and filters to ~87 English narrative pages, excluding `/api/*` reference pages by default.

2. **Scraping** — Each page is scraped in an isolated subprocess (`scraper_worker.py`) that
   launches its own Playwright Chromium instance, waits for `networkidle`, and returns JSON
   to stdout. Running Chromium in a child process means an OOM kill only terminates that
   child — the uvicorn server stays alive. This is required because the docs are a Mintlify
   React SPA — a plain HTTP request only returns a `Loading...` skeleton.

3. **Chunking** — tiktoken splits the extracted text into 500-token chunks with a 50-token
   overlap so context is never lost at chunk boundaries.

4. **Embedding** — Chunks are sent to OpenAI's `text-embedding-3-small` model via direct
   HTTP in batches of 100. Each chunk becomes a 1536-dimensional float vector.

5. **Storage** — ChromaDB upserts the vectors with cosine similarity. IDs are deterministic
   (`{url}__chunk_{index}`) so re-ingesting the same page is safe and idempotent. All
   ChromaDB access is serialised through a `threading.RLock` to prevent race conditions
   between the ingest thread and the health-check thread pool.

6. **Background jobs** — `POST /ingest` returns a `job_id` immediately. The actual scraping
   and embedding runs in a daemon thread. The frontend polls `GET /ingest/status/{job_id}`
   every 4 seconds until the job completes or fails.

7. **Retrieval** — At query time the user's question is embedded with the same OpenAI model
   and ChromaDB returns the 5 most similar chunks by cosine distance.

8. **Generation** — Retrieved chunks are formatted into a user prompt. The full conversation
   history (previous turns) is prepended as prior messages so Claude has multi-turn context.
   The request is sent to `claude-sonnet-4-6` via the Anthropic streaming API.

9. **Streaming** — Tokens stream to the frontend via Server-Sent Events. The frontend renders
   each token through `react-markdown` so headings, bold text, bullet lists, and code blocks
   display correctly as the response builds up.

10. **Citations** — Source URLs and titles are deduplicated from the retrieved chunks and
    sent as a final SSE event, rendered as numbered links below each answer.

---

## Environment Variables

| Variable            | Required | Description                                          |
|---------------------|----------|------------------------------------------------------|
| `ANTHROPIC_API_KEY` | yes      | Claude API key                                       |
| `OPENAI_API_KEY`    | yes      | OpenAI key for embeddings                            |
| `RAG_API_KEY`       | no       | Protects `/chat` + `/ingest`; blank = auth disabled  |
| `ALLOWED_ORIGINS`   | no       | Comma-separated CORS origins (default: localhost)    |
| `VITE_API_KEY`      | no       | Frontend build-time key sent as `X-API-Key` header   |
