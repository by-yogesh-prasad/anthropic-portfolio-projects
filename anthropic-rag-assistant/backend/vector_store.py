"""ChromaDB vector store operations for the RAG knowledge base."""

import logging
import os
import threading
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
COLLECTION_NAME = "anthropic_docs"

_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None
_lock = threading.RLock()  # reentrant — same thread can re-acquire during nested calls


def _get_client() -> chromadb.PersistentClient:
    """Return (or lazily create) the persistent ChromaDB client. Caller holds _lock."""
    global _client
    if _client is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def init_collection() -> chromadb.Collection:
    """Initialize (or load) the Anthropic docs collection.

    Returns:
        The ChromaDB Collection object.
    """
    global _collection
    with _lock:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Collection %r ready — %d documents stored",
            COLLECTION_NAME, _collection.count(),
        )
        return _collection


def _ensure_collection() -> chromadb.Collection:
    """Return the collection, initializing it if needed. Caller holds _lock."""
    global _collection
    if _collection is None:
        return init_collection()
    return _collection


def reset_collection() -> chromadb.Collection:
    """Delete the existing collection and recreate it (clears all stored vectors).

    Use this when switching embedding models — dimension changes are incompatible
    with an existing collection and require a full re-ingest. Also fixes a
    readonly/corrupt SQLite state by forcing the client to reconnect.

    Returns:
        The freshly created empty Collection object.
    """
    global _client, _collection
    logger.warning("Resetting collection %r — all vectors will be deleted", COLLECTION_NAME)
    with _lock:
        if _client is not None:
            try:
                _client.delete_collection(name=COLLECTION_NAME)
                logger.info("Deleted existing collection %r", COLLECTION_NAME)
            except Exception:
                pass
        _client = None
        _collection = None
    return init_collection()


def add_documents(
    chunks: List[str],
    embeddings: List[List[float]],
    metadata: List[Dict[str, Any]],
    ids: Optional[List[str]] = None,
) -> None:
    """Upsert text chunks with their embeddings and metadata into ChromaDB.

    Args:
        chunks: Raw text strings for each chunk.
        embeddings: Pre-computed embedding vectors, one per chunk.
        metadata: Dicts of metadata (e.g. source URL, title, chunk_index).
        ids: Optional explicit IDs; auto-generated from metadata if omitted.

    Raises:
        ValueError: If the lengths of chunks, embeddings, and metadata differ.
        RuntimeError: If the ChromaDB upsert fails.
    """
    if not (len(chunks) == len(embeddings) == len(metadata)):
        raise ValueError(
            f"Mismatched lengths: chunks={len(chunks)}, "
            f"embeddings={len(embeddings)}, metadata={len(metadata)}"
        )

    if ids is None:
        ids = [
            f"{m.get('source', 'unknown')}__chunk_{m.get('chunk_index', i)}"
            for i, m in enumerate(metadata)
        ]

    with _lock:
        collection = _ensure_collection()
        try:
            collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadata,
            )
            logger.info("Upserted %d documents into %r", len(chunks), COLLECTION_NAME)
        except Exception as e:
            if "readonly database" in str(e).lower():
                logger.error("ChromaDB upsert failed: readonly database")
                raise RuntimeError(
                    "ChromaDB upsert failed: readonly database. "
                    "Delete data/chroma_db/ and re-ingest, or call POST /ingest with {\"reset\": true}."
                ) from e
            logger.error("ChromaDB upsert failed: %s", e)
            raise RuntimeError(f"ChromaDB upsert failed: {e}") from e


def search(
    query_embedding: List[float],
    top_k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Retrieve the top-k most similar chunks for a query embedding.

    Args:
        query_embedding: The embedding vector of the user's question.
        top_k: Number of results to return.
        where: Optional ChromaDB metadata filter dict.

    Returns:
        List of dicts with keys: id, document, metadata, distance.
    """
    with _lock:
        collection = _ensure_collection()
        try:
            n_results = min(top_k, collection.count() or top_k)
            kwargs: Dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
                logger.debug("Search with metadata filter: %s", where)

            results = collection.query(**kwargs)

            hits: List[Dict[str, Any]] = []
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    }
                )
            logger.debug("Search returned %d hits (requested top_%d)", len(hits), top_k)
            return hits
        except Exception as e:
            logger.error("ChromaDB query failed: %s", e)
            raise RuntimeError(f"ChromaDB query failed: {e}") from e


def get_collection_stats() -> Dict[str, Any]:
    """Return summary statistics about the current collection.

    Returns:
        Dict with total_documents count and collection name.
    """
    with _lock:
        try:
            collection = _ensure_collection()
            count = collection.count()
            return {
                "collection_name": COLLECTION_NAME,
                "total_documents": count,
                "storage_path": os.path.abspath(CHROMA_PATH),
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get collection stats: {e}") from e
