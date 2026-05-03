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

---

## Author

**Yogesh Prasad** — [github.com/by-yogesh-prasad](https://github.com/by-yogesh-prasad)
