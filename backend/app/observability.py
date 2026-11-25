from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def configure_observability() -> None:
    """Attach Langfuse to LiteLLM when explicitly enabled.

    Off by default. Keys stay in the environment; nothing is sent until
    LANGFUSE_ENABLED=true and both keys are present.
    """
    if not settings.langfuse_enabled:
        logger.info("langfuse hook disabled")
        return
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("langfuse enabled but keys are missing; hook left inactive")
        return
    try:
        import litellm

        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
    except Exception:
        logger.exception("failed to enable langfuse callback")
        return
    logger.info("langfuse callback enabled")
