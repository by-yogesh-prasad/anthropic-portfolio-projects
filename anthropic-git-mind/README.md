# GitMind

Ask natural language questions about any Git repository's history and get cited answers backed by commit SHAs.

```
$ gitmind ask "why does the retry logic use 3 attempts?"

  The retry limit of 3 was introduced in commit a3f8c1d2 to match AWS SDK
  defaults, replacing the original 5-attempt limit that was causing timeout
  cascades under load (see commit 7b2e09f4 which first reported the issue).
```

## What it does

GitMind indexes every commit in a Git repo — message + diff — into a local [sqlite-vec](https://github.com/asg017/sqlite-vec) vector store using a local embedding model. When you ask a question, it retrieves the most relevant commits and sends them as context to Claude Sonnet 4.6, which synthesizes a cited answer.

No data leaves your machine except the question and retrieved commit excerpts sent to the Anthropic API.

## Stack

| Layer | Technology |
|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`, runs locally) |
| Vector store | `sqlite-vec` (local SQLite extension) |
| LLM | Claude Sonnet 4.6 via Anthropic API |
| CLI | `click` + `rich` |
| API backend | FastAPI + uvicorn |
| Web UI | Next.js 15, React 19, Tailwind CSS |

## Installation

**Prerequisites:** Python 3.11+, Node.js 18+

```bash
git clone https://github.com/by-yogesh-prasad/anthropic-git-mind
cd anthropic-git-mind

# Install Python package
pip install -e ".[api]"

# Install Node dependencies for the web UI
cd web && npm install && cd ..
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Quick start

### CLI

```bash
# Index a repository (defaults to current directory)
gitmind index --repo /path/to/repo

# Ask a question
gitmind ask "why was the caching layer added?"

# Show index stats
gitmind status

# Clear the index for a repo
gitmind clear
```

### Web UI

Start the API server and the Next.js dev server in two terminals:

```bash
# Terminal 1 — API
gitmind serve

# Terminal 2 — Web UI
cd web && npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

For production:

```bash
gitmind serve --port 8000

cd web
npm run build
npm start
```

## CLI reference

```
gitmind index [--repo PATH]          Index a git repo (default: current dir)
gitmind ask QUESTION [--repo NAME]   Ask a question; --repo selects which index
              [--top-k N]            Number of chunks to retrieve (default: 10)
gitmind status [--repo NAME]         Show index stats
gitmind clear [--repo NAME] [--yes]  Delete the index
gitmind serve [--host HOST]          Start the FastAPI backend
              [--port PORT]          Port (default: 8000)
              [--reload]             Auto-reload on code changes (dev)
```

## API

The FastAPI backend exposes:

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/repos` | List indexed repositories |
| `POST` | `/repos/index` | Index a repository `{repo_path}` |
| `DELETE` | `/repos/{name}` | Clear a repository's index |
| `POST` | `/ask` | Ask a question (SSE stream) `{question, repo, top_k}` |

Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## How it works

1. **Indexing** — `gitmind index` walks every commit reachable from HEAD via `gitpython`. For each commit it creates:
   - A *message chunk*: author, date, full commit message
   - One *diff chunk* per changed file (capped at ~500 tokens each)

   All chunks are embedded with `all-MiniLM-L6-v2` in batches of 32, then stored as `float32` blobs in a sqlite-vec `vec0` virtual table at `~/.gitmind/{repo_name}/index.db`.

2. **Retrieval** — The query is embedded with the same model. A KNN search (`WHERE embedding MATCH ? AND k = ?`) returns the top-K nearest chunks.

3. **Generation** — The retrieved chunks are sent as context to Claude Sonnet 4.6 with a system prompt that requires SHA citations. The answer streams back via SSE.

## Storage

```
~/.gitmind/
  {repo_name}/
    index.db      sqlite-vec database (vectors + chunk text)
    meta.json     index metadata (commit count, timestamp, repo path)
```

## Project structure

```
anthropic-git-mind/
├── gitmind/
│   ├── cli.py        click CLI (index, ask, status, clear, serve)
│   ├── indexer.py    git history → chunks → embeddings → sqlite-vec
│   ├── store.py      sqlite-vec read/write wrapper
│   ├── embedder.py   sentence-transformers wrapper (lazy-loaded)
│   └── schema.py     pydantic models
├── api/
│   └── main.py       FastAPI backend (REST + SSE)
└── web/              Next.js 15 frontend
    ├── app/
    ├── components/
    └── lib/
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins for the API. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API base URL used by the web frontend. |
