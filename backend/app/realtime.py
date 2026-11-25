"""In-process fan-out, with Redis pub/sub when the API and worker are separate."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "irhub:events"


class Hub:
    def __init__(self) -> None:
        self._listeners: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        inbox: queue.Queue = queue.Queue()
        with self._lock:
            self._listeners.append(inbox)
        return inbox

    def unsubscribe(self, inbox: queue.Queue) -> None:
        with self._lock:
            if inbox in self._listeners:
                self._listeners.remove(inbox)

    def publish(self, event: dict[str, Any]) -> None:
        if _redis_publish(event):
            return
        self.fanout(event)

    def fanout(self, event: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for inbox in listeners:
            try:
                inbox.put_nowait(event)
            except Exception:
                logger.debug("dropped live event", exc_info=True)


hub = Hub()
_listener_started = False
_listener_lock = threading.Lock()


def _redis_publish(event: dict[str, Any]) -> bool:
    if os.getenv("SKIP_REDIS") == "1":
        return False
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=0.3, socket_timeout=0.3
        )
        client.publish(CHANNEL, json.dumps(event, ensure_ascii=False, default=str))
        return True
    except Exception:
        logger.debug("redis publish unavailable")
        return False


def start_redis_listener() -> None:
    """API process: events published by the worker arrive on this thread."""
    global _listener_started
    if os.getenv("SKIP_REDIS") == "1":
        return
    with _listener_lock:
        if _listener_started:
            return
        _listener_started = True

    def _loop() -> None:
        import time

        while True:
            try:
                import redis

                client = redis.Redis.from_url(settings.redis_url, socket_timeout=None)
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(CHANNEL)
                for item in pubsub.listen():
                    if item.get("type") != "message":
                        continue
                    raw = item.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    hub.fanout(json.loads(raw))
            except Exception:
                logger.info("redis listener retrying")
                time.sleep(2)

    threading.Thread(target=_loop, name="irhub-live", daemon=True).start()
