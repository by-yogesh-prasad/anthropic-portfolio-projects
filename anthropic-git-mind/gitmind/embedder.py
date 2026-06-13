"""Sentence-transformer embedding wrapper with lazy model loading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_model: "SentenceTransformer | None" = None
_console = Console(stderr=True)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _get_model() -> "SentenceTransformer":
    """Load the embedding model on first call, then cache it."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        with _console.status(
            f"[bold green]Loading embedding model ({MODEL_NAME})…", spinner="dots"
        ):
            _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns one 384-dim float vector per text."""
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return vectors.tolist()


def embed_one(text: str) -> list[float]:
    """Convenience wrapper for a single text."""
    return embed([text])[0]
