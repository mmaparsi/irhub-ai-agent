from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.observability import configure_observability

_OBSERVABILITY_READY = False


def _ensure_observability() -> None:
    global _OBSERVABILITY_READY
    if not _OBSERVABILITY_READY:
        configure_observability()
        _OBSERVABILITY_READY = True


async def stream_model(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yield ('token', str) pieces, then ('tools', list) if the model called tools.

    Tool-call chunks are buffered and emitted once at the end of the stream.
    """
    _ensure_observability()
    import litellm

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
    response = await litellm.acompletion(**kwargs)
    buckets: dict[int, dict[str, str]] = {}
    async for chunk in response:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield ("token", text)
        for call in getattr(delta, "tool_calls", None) or []:
            index = int(getattr(call, "index", 0) or 0)
            slot = buckets.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if getattr(call, "id", None):
                slot["id"] = call.id
            function = getattr(call, "function", None)
            if function is None:
                continue
            if getattr(function, "name", None):
                slot["name"] = function.name
            if getattr(function, "arguments", None):
                slot["arguments"] += function.arguments
    if buckets:
        calls = []
        for index in sorted(buckets):
            slot = buckets[index]
            try:
                arguments = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                {
                    "id": slot["id"] or f"call_{index}",
                    "name": slot["name"],
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
        yield ("tools", calls)
