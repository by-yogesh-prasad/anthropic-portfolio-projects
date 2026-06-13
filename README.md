# Anthropic Portfolio Projects

A collection of production-grade AI applications built with Anthropic's Claude API,
demonstrating real-world patterns for retrieval-augmented generation, streaming,
tool use, and multi-turn conversation.

---

## Projects

### [anthropic-rag-assistant](./anthropic-rag-assistant)

An enterprise RAG knowledge base that answers questions over Anthropic's official
documentation in real time.

**Stack:** FastAPI · React 18 · ChromaDB · OpenAI Embeddings · Claude claude-sonnet-4-6 · Docker

**Key features:**
- Scrapes ~87 Anthropic doc pages via subprocess-isolated Playwright (OOM-safe)
- Semantic search with OpenAI `text-embedding-3-small` (1536-dim, cosine similarity)
- Streaming answers via Server-Sent Events with multi-turn conversation history
- Markdown-rendered responses with deduplicated source citations
- Background ingestion jobs with polling status endpoint
- Rate limiting, API key auth, and Docker Compose deployment

### [anthropic-git-mind](./anthropic-git-mind)

A local-first tool that indexes a Git repository's entire commit history into a
sqlite-vec vector store and answers natural language questions about why code
exists, when decisions were made, and what changed — with commit SHA citations.

**Stack:** Python CLI · FastAPI · Next.js 15 · sqlite-vec · sentence-transformers · Claude claude-sonnet-4-6

**Key features:**
- Indexes full Git history (commit messages + per-file diffs) into a local sqlite-vec store
- Local embeddings via `sentence-transformers` (all-MiniLM-L6-v2, no external API)
- Streaming answers via Server-Sent Events with commit SHA source citations
- Responsive Next.js UI with light/dark theme and auto-resizing input
- Python CLI (`gitmind index / ask / status / clear / serve`)
- Storage at `~/.gitmind/{repo}/` — one index per repo, no cloud required

---

## Author

**Yogesh Prasad** — [github.com/by-yogesh-prasad](https://github.com/by-yogesh-prasad)
