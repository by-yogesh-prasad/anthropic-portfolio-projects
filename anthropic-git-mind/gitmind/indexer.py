"""Read a repo's Git history, chunk commits, embed, and store in sqlite-vec."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from git import InvalidGitRepositoryError, Repo
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from gitmind.embedder import embed
from gitmind.schema import Chunk, CommitRecord, IndexMeta
from gitmind.store import init_db, upsert_chunk

console = Console()

# ~500 tokens at ~4 chars/token; hard cap per per-file diff chunk
MAX_DIFF_CHARS = 2000
# Embed this many chunks at once to amortize model overhead
BATCH_SIZE = 32


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------


def _is_binary(blob_stream) -> bool:
    """Return True if the first 8 KB of a blob stream contains a null byte."""
    try:
        sample = blob_stream.read(8192)
        return b"\x00" in sample
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _make_id(*parts: str) -> str:
    """Stable 16-hex-char ID from arbitrary string parts."""
    key = ":".join(parts).encode()
    return hashlib.sha256(key).hexdigest()[:16]


def _chunk_diff(sha: str, diff_text: str) -> list[Chunk]:
    """Split a raw unified diff into per-file chunks capped at MAX_DIFF_CHARS.

    Each file boundary (``diff --git …``) starts a new chunk; oversized
    file diffs are split further by character budget.
    """
    chunks: list[Chunk] = []
    current_file = "unknown"
    current_lines: list[str] = []
    current_size = 0
    part = 0

    def flush() -> None:
        nonlocal part, current_size
        text = "".join(current_lines).strip()
        if text:
            chunks.append(
                Chunk(
                    chunk_id=_make_id(sha, current_file, str(part)),
                    commit_sha=sha,
                    text=f"File: {current_file}\n{text}",
                    chunk_type="diff",
                )
            )
        part += 1
        current_lines.clear()
        current_size = 0

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_lines:
                flush()
                part = 0  # reset part counter per file
            # Extract the b/ path: "diff --git a/foo b/foo" → "foo"
            current_file = line.split(" b/", 1)[-1].strip() if " b/" in line else line.strip()
            current_lines.append(line)
            current_size += len(line)
        else:
            current_lines.append(line)
            current_size += len(line)
            if current_size >= MAX_DIFF_CHARS:
                flush()

    if current_lines:
        flush()

    return chunks


# ---------------------------------------------------------------------------
# Commit extraction
# ---------------------------------------------------------------------------


def _extract_commit(commit) -> CommitRecord:
    """Build a CommitRecord from a gitpython Commit, skipping binary files."""
    files_changed: list[str] = []
    diff_parts: list[str] = []

    try:
        parent = commit.parents[0] if commit.parents else None
        diffs = (
            commit.diff(parent, create_patch=True)
            if parent
            else commit.diff(None, create_patch=True)
        )

        for d in diffs:
            # Skip binary blobs
            if d.a_blob:
                try:
                    if _is_binary(d.a_blob.data_stream):
                        continue
                except Exception:
                    continue
            if d.b_blob:
                try:
                    if _is_binary(d.b_blob.data_stream):
                        continue
                except Exception:
                    continue

            path = d.b_path or d.a_path or ""
            if path:
                files_changed.append(path)

            try:
                patch = d.diff
                if isinstance(patch, bytes):
                    patch = patch.decode("utf-8", errors="replace")
                diff_parts.append(
                    f"diff --git a/{d.a_path} b/{d.b_path}\n{patch}"
                )
            except Exception:
                pass

    except Exception:
        pass

    return CommitRecord(
        sha=commit.hexsha,
        message=commit.message.strip(),
        author=f"{commit.author.name} <{commit.author.email}>",
        date=datetime.fromtimestamp(commit.committed_date, tz=timezone.utc),
        files_changed=files_changed,
        diff_text="\n".join(diff_parts),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def index_repo(repo_path: Path, db_path: Path) -> IndexMeta:
    """Index an entire git repository into the sqlite-vec store at db_path.

    Iterates every commit reachable from HEAD, builds message + diff chunks,
    embeds them in batches, and upserts into the vector store.
    """
    try:
        repo = Repo(str(repo_path), search_parent_directories=True)
    except InvalidGitRepositoryError:
        raise ValueError(f"No git repository found at {repo_path}")

    repo_name = Path(repo.working_dir).name
    conn = init_db(db_path)

    all_commits = list(repo.iter_commits("HEAD"))
    total = len(all_commits)

    console.print(
        f"[bold cyan]GitMind[/] indexing [bold]{repo_name}[/] — "
        f"[bold]{total:,}[/] commits"
    )

    pending_chunks: list[Chunk] = []

    def flush_batch() -> None:
        if not pending_chunks:
            return
        texts = [c.text for c in pending_chunks]
        embeddings = embed(texts)
        for chunk, emb in zip(pending_chunks, embeddings):
            upsert_chunk(conn, chunk, emb)
        conn.commit()
        pending_chunks.clear()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Indexing {total:,} commits…", total=total)

        for commit in all_commits:
            record = _extract_commit(commit)

            # One chunk for the commit message
            pending_chunks.append(
                Chunk(
                    chunk_id=_make_id(record.sha, "message"),
                    commit_sha=record.sha,
                    text=(
                        f"Commit {record.sha[:8]} by {record.author} "
                        f"on {record.date.date()}\n\n{record.message}"
                    ),
                    chunk_type="message",
                )
            )

            # Per-file diff chunks
            if record.diff_text:
                pending_chunks.extend(_chunk_diff(record.sha, record.diff_text))

            if len(pending_chunks) >= BATCH_SIZE:
                flush_batch()

            progress.advance(task)

    flush_batch()
    conn.close()

    return IndexMeta(
        repo_path=str(repo_path.resolve()),
        repo_name=repo_name,
        total_commits=total,
        indexed_at=datetime.now(tz=timezone.utc),
    )
