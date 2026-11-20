from __future__ import annotations

import hashlib
import logging
import math

from app.agents.llm import api_base_for, configure_litellm
from app.config import settings
from app.constants import EMBEDDING_DIM
from app.llm_defaults import GEMINI_EMBEDDING_DIM, GEMINI_EMBEDDING_MODEL, OPENAI_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def embed_text(text: str) -> list[float]:
    """Return a vector of EMBEDDING_DIM (1536), matching the pgvector column.

    OpenAI `text-embedding-3-small` is already 1536. Gemini
    `gemini/gemini-embedding-001` is requested at 768 dimensions and zero-padded
    to 1536. Cosine distance is unchanged by a shared zero tail, so the column
    stays `vector(1536)`. Mock mode, or a missing key, uses the local stub.
    """
    model = _provider_embedding_model()
    if model is None:
        return stub_embed(text)
    try:
        import litellm

        configure_litellm()
        kwargs: dict = {"model": model, "input": (text or "")[:8000]}
        if model == GEMINI_EMBEDDING_MODEL:
            kwargs["dimensions"] = GEMINI_EMBEDDING_DIM
        base = api_base_for(model)
        if base:
            kwargs["api_base"] = base
        response = litellm.embedding(**kwargs)
        vector = _extract_embedding(response)
        if len(vector) != EMBEDDING_DIM:
            logger.info(
                "fitting embedding from %s dims to %s for %s",
                len(vector),
                EMBEDDING_DIM,
                model,
            )
        return _fit(vector, EMBEDDING_DIM)
    except Exception:
        logger.exception("embedding provider failed; using stub vector")
        return stub_embed(text)


def _provider_embedding_model() -> str | None:
    if settings.llm_is_mock():
        return None
    if settings.openai_api_key.strip():
        return OPENAI_EMBEDDING_MODEL
    if settings.gemini_api_key.strip():
        return GEMINI_EMBEDDING_MODEL
    return None


def _extract_embedding(response: object) -> list[float]:
    data = response["data"] if isinstance(response, dict) else response.data  # type: ignore[attr-defined]
    item = data[0]
    if isinstance(item, dict):
        return list(item["embedding"])
    return list(item.embedding)


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
