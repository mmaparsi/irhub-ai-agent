from __future__ import annotations

import hashlib
import logging
import math

from app.config import settings
from app.constants import EMBEDDING_DIM

logger = logging.getLogger(__name__)


def embed_text(text: str) -> list[float]:
    """Return a vector of EMBEDDING_DIM.

    Uses a provider embedding when a real model key is configured and mock
    mode is off. Otherwise a deterministic local vector keeps pgvector usable
    without an API key. Replace `stub_embed` with a real embedder when ready.
    """
    if not settings.llm_is_mock() and settings.openai_api_key:
        try:
            import litellm

            response = litellm.embedding(
                model="text-embedding-3-small",
                input=(text or "")[:8000],
            )
            vector = list(response.data[0]["embedding"])
            return _fit(vector, EMBEDDING_DIM)
        except Exception:
            logger.exception("embedding provider failed; using stub vector")
    return stub_embed(text)


def stub_embed(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    raw = (text or "").encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    for index, byte in enumerate(digest):
        vector[index % EMBEDDING_DIM] += (byte / 255.0) - 0.5
    for index, char in enumerate(text or ""):
        vector[(index * 31 + ord(char)) % EMBEDDING_DIM] += 0.05
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _fit(vector: list[float], size: int) -> list[float]:
    if len(vector) == size:
        return vector
    if len(vector) > size:
        return vector[:size]
    return vector + [0.0] * (size - len(vector))
