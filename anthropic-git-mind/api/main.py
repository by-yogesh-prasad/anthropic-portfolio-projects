"""FastAPI backend for GitMind — serves the Next.js web UI."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Ensure the package root is importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from gitmind.embedder import embed_one
from gitmind.indexer import index_repo
from gitmind.schema import IndexMeta
from gitmind.store import clear_all, count, init_db, search

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITMIND_DIR = Path.home() / ".gitmind"
MODEL = "claude-sonnet-4-6"
SYSTEM_PROMPT = (
    "You are GitMind, an expert at explaining Git repository history. "
    "You answer questions about why code exists, when decisions were made, "
    "and the reasoning behind changes — all based on commit messages and diffs. "
    "Always cite the commit SHA (the 8-character prefix shown in brackets) when "
    "referencing a specific change. Format your answer in Markdown."
)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_dir(name: str) -> Path:
    return GITMIND_DIR / name

def _db_path(name: str) -> Path:
    return _repo_dir(name) / "index.db"

def _meta_path(name: str) -> Path:
    return _repo_dir(name) / "meta.json"

def _save_meta(meta: IndexMeta) -> None:
    p = _meta_path(meta.repo_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(meta.model_dump_json(indent=2))

def _load_meta(name: str) -> IndexMeta | None:
    p = _meta_path(name)
    return IndexMeta.model_validate_json(p.read_text()) if p.exists() else None

def _list_repos() -> list[str]:
    if not GITMIND_DIR.exists():
        return []
    return [d.name for d in GITMIND_DIR.iterdir() if d.is_dir() and _meta_path(d.name).exists()]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="GitMind API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class IndexRequest(BaseModel):
    repo_path: str

class AskRequest(BaseModel):
    question: str
    repo: str
    top_k: int = 10

class RepoInfo(BaseModel):
    name: str
    repo_path: str
    total_commits: int
    chunk_count: int
    indexed_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/repos", response_model=list[RepoInfo])
async def list_repos() -> list[dict[str, Any]]:
    repos = []
    for name in _list_repos():
        meta = _load_meta(name)
        if meta is None:
            continue
        db = _db_path(name)
        chunks = 0
        if db.exists():
            try:
                conn = init_db(db)
                chunks = count(conn)
                conn.close()
            except Exception:
                pass
        repos.append(
            RepoInfo(
                name=meta.repo_name,
                repo_path=meta.repo_path,
                total_commits=meta.total_commits,
                chunk_count=chunks,
                indexed_at=meta.indexed_at.isoformat(),
            ).model_dump()
        )
    return repos


@app.post("/repos/index", response_model=RepoInfo)
async def index_repository(req: IndexRequest) -> dict[str, Any]:
    repo_path = Path(req.repo_path).resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {repo_path}")

    try:
        from git import Repo as GitRepo
        git_repo = GitRepo(str(repo_path), search_parent_directories=True)
        repo_name = Path(git_repo.working_dir).name
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Not a git repository: {exc}")

    db = _db_path(repo_name)
    db.parent.mkdir(parents=True, exist_ok=True)

    try:
        loop = asyncio.get_event_loop()
        meta = await loop.run_in_executor(None, index_repo, repo_path, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _save_meta(meta)

    conn = init_db(db)
    chunks = count(conn)
    conn.close()

    return RepoInfo(
        name=meta.repo_name,
        repo_path=meta.repo_path,
        total_commits=meta.total_commits,
        chunk_count=chunks,
        indexed_at=meta.indexed_at.isoformat(),
    ).model_dump()


@app.delete("/repos/{repo_name}")
async def clear_repo(repo_name: str) -> dict[str, bool]:
    if _load_meta(repo_name) is None:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")

    db = _db_path(repo_name)
    if db.exists():
        conn = init_db(db)
        clear_all(conn)
        conn.close()
        db.unlink()

    mp = _meta_path(repo_name)
    if mp.exists():
        mp.unlink()

    try:
        _repo_dir(repo_name).rmdir()
    except OSError:
        pass

    return {"success": True}


@app.post("/ask")
async def ask(req: AskRequest) -> StreamingResponse:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured.")

    meta = _load_meta(req.repo)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Repository '{req.repo}' not indexed.")

    db = _db_path(req.repo)
    if not db.exists():
        raise HTTPException(status_code=404, detail="Index database not found.")

    # Run the blocking embedding + search in a thread
    loop = asyncio.get_event_loop()

    def _search() -> list[dict]:
        embedding = embed_one(req.question)
        conn = init_db(db)
        results = search(conn, embedding, top_k=req.top_k)
        conn.close()
        return results

    results = await loop.run_in_executor(None, _search)

    if not results:
        async def _empty():
            yield f"data: {json.dumps({'type': 'done', 'sources': [], 'usage': {}})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    context = "\n\n---\n\n".join(
        f"[Commit {r['commit_sha'][:8]}]\n{r['text']}" for r in results
    )
    user_message = (
        f"Repository: {req.repo}\n\n"
        f"Question: {req.question}\n\n"
        f"Relevant commits from the repository history:\n\n{context}"
    )

    sources = [
        {
            "sha": r["commit_sha"][:8],
            "full_sha": r["commit_sha"],
            "chunk_type": r["chunk_type"],
            "distance": r["distance"],
            "text": r["text"][:600],
        }
        for r in results
    ]

    async def _stream():
        import anthropic

        client = anthropic.Anthropic()
        input_tokens = 0
        output_tokens = 0

        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'chunk', 'text': text})}\n\n"

                final = stream.get_final_message()
                input_tokens = final.usage.input_tokens
                output_tokens = final.usage.output_tokens

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'usage': {'input': input_tokens, 'output': output_tokens}})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
