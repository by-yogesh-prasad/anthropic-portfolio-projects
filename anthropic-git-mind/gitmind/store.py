"""sqlite-vec vector store: init, upsert, search, and helpers."""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

from gitmind.schema import Chunk

EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize(vector: list[float]) -> bytes:
    """Pack a float list into a raw IEEE-754 blob for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def _open_conn(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with sqlite-vec loaded."""
    import sqlite_vec

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create tables and return an open connection.

    Creates ~/.gitmind/<repo>/index.db if it doesn't exist.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _open_conn(db_path)

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS chunks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id   TEXT    UNIQUE NOT NULL,
            commit_sha TEXT    NOT NULL,
            text       TEXT    NOT NULL,
            chunk_type TEXT    NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
            embedding float[{EMBEDDING_DIM}]
        );
    """)
    conn.commit()
    return conn


def upsert_chunk(conn: sqlite3.Connection, chunk: Chunk, embedding: list[float]) -> None:
    """Insert or update a chunk and its embedding vector."""
    conn.execute(
        """
        INSERT INTO chunks (chunk_id, commit_sha, text, chunk_type)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            commit_sha = excluded.commit_sha,
            text       = excluded.text,
            chunk_type = excluded.chunk_type
        """,
        (chunk.chunk_id, chunk.commit_sha, chunk.text, chunk.chunk_type),
    )

    row = conn.execute(
        "SELECT id FROM chunks WHERE chunk_id = ?", (chunk.chunk_id,)
    ).fetchone()
    rowid: int = row["id"]

    # vec0 doesn't support ON CONFLICT, so delete-then-insert
    conn.execute("DELETE FROM vec_chunks WHERE rowid = ?", (rowid,))
    conn.execute(
        "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
        (rowid, _serialize(embedding)),
    )


def search(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[dict]:
    """Return top_k most similar chunks as plain dicts (includes distance)."""
    rows = conn.execute(
        """
        SELECT c.chunk_id, c.commit_sha, c.text, c.chunk_type, v.distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ?
          AND k = ?
        ORDER BY v.distance
        """,
        (_serialize(query_embedding), top_k),
    ).fetchall()

    return [
        {
            "chunk_id":   r["chunk_id"],
            "commit_sha": r["commit_sha"],
            "text":       r["text"],
            "chunk_type": r["chunk_type"],
            "distance":   r["distance"],
        }
        for r in rows
    ]


def get_chunk_by_id(conn: sqlite3.Connection, chunk_id: str) -> Chunk | None:
    """Fetch a single chunk by its chunk_id. Returns None if not found."""
    row = conn.execute(
        "SELECT chunk_id, commit_sha, text, chunk_type FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if row is None:
        return None
    return Chunk(
        chunk_id=row["chunk_id"],
        commit_sha=row["commit_sha"],
        text=row["text"],
        chunk_type=row["chunk_type"],
    )


def count(conn: sqlite3.Connection) -> int:
    """Total number of indexed chunks."""
    return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]


def clear_all(conn: sqlite3.Connection) -> None:
    """Delete all chunks and vectors from the store."""
    conn.executescript("""
        DELETE FROM vec_chunks;
        DELETE FROM chunks;
    """)
    conn.commit()
