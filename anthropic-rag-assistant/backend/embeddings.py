"""OpenAI embeddings via direct HTTP requests (no openai package)."""

import logging
import os
import requests
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/embeddings"
OPENAI_MODEL = "text-embedding-3-small"


def get_embedding(text: str) -> List[float]:
    """Embed a single text string using OpenAI text-embedding-3-small.

    Args:
        text: The text to embed.

    Returns:
        A list of floats representing the embedding vector (1536 dims).

    Raises:
        RuntimeError: If the API call fails.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables.")

    logger.debug("Embedding single text (%d chars)", len(text))
    try:
        response = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "input": text,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except requests.exceptions.RequestException as e:
        logger.error("OpenAI embedding request failed: %s", e)
        raise RuntimeError(f"OpenAI API request failed: {e}") from e
    except (KeyError, IndexError) as e:
        logger.error("Unexpected OpenAI embedding response format: %s", e)
        raise RuntimeError(f"Unexpected OpenAI API response format: {e}") from e


def get_embeddings_batch(texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """Embed a list of texts in batches using OpenAI text-embedding-3-small.

    OpenAI accepts up to 2048 inputs per request; we use 100 as a safe default.

    Args:
        texts: List of text strings to embed.
        batch_size: Number of texts to send per API request.

    Returns:
        A list of embedding vectors, one per input text, in the same order.

    Raises:
        RuntimeError: If any API call fails.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in environment variables.")

    all_embeddings: List[List[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size
    logger.info("Embedding %d texts in %d batch(es)", len(texts), total_batches)

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.debug("Embedding batch %d/%d (%d texts)", batch_num, total_batches, len(batch))
        try:
            response = requests.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "input": batch,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            # OpenAI returns results sorted by index; re-sort to be safe
            batch_results = sorted(data["data"], key=lambda x: x["index"])
            all_embeddings.extend([item["embedding"] for item in batch_results])

        except requests.exceptions.RequestException as e:
            logger.error("OpenAI batch %d/%d failed: %s", batch_num, total_batches, e)
            raise RuntimeError(
                f"OpenAI batch embedding failed on batch {i // batch_size}: {e}"
            ) from e
        except (KeyError, IndexError) as e:
            logger.error("Unexpected OpenAI response format in batch %d/%d: %s", batch_num, total_batches, e)
            raise RuntimeError(
                f"Unexpected OpenAI API response format in batch {i // batch_size}: {e}"
            ) from e

    logger.info("Batch embedding complete — %d vectors returned", len(all_embeddings))
    return all_embeddings
