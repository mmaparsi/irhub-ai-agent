from __future__ import annotations

import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)


async def enqueue(job: str, *args: str) -> bool:
    if os.getenv("SKIP_REDIS") == "1":
        return False
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception:
        logger.warning("redis unavailable; job %s was not queued", job)
        return False
    try:
        await redis.enqueue_job(job, *args)
        return True
    except Exception:
        logger.exception("failed to enqueue %s", job)
        return False
    finally:
        await redis.close()
