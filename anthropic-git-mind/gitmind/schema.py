"""Pydantic v2 data models for GitMind."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CommitRecord(BaseModel):
    """A single Git commit with its metadata and diff."""

    sha: str
    message: str
    author: str
    date: datetime
    files_changed: list[str]
    diff_text: str


class Chunk(BaseModel):
    """A text chunk derived from a commit, ready for embedding."""

    chunk_id: str
    commit_sha: str
    text: str
    chunk_type: Literal["message", "diff", "summary"]


class SearchResult(BaseModel):
    """A ranked result from vector similarity search."""

    chunk: Chunk
    score: float  # cosine distance — lower is more similar
    commit: CommitRecord


class IndexMeta(BaseModel):
    """Metadata about an indexed repository."""

    repo_path: str
    repo_name: str
    total_commits: int
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
