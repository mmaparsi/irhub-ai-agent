from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings
from app.observability import configure_observability

logger = logging.getLogger(__name__)

_READY = False


class LLMCallError(Exception):
    """The model chain failed. `user_message` is safe to show in the panel."""

    def __init__(self, reason: str, model: str, user_message: str) -> None:
        self.reason = reason
        self.model = model
        self.user_message = user_message
        super().__init__(user_message)


def configure_litellm() -> None:
    """Drop unsupported params (Gemini rejects temperature on some flash models)."""
    global _READY
    import litellm

    litellm.drop_params = True
    if not _READY:
        configure_observability()
        _READY = True


def build_model_chain(primary: str, fast: str | None, fallbacks: list[str]) -> list[str]:
    """Primary, then the fast tier, then MODEL_FALLBACKS, without duplicates."""
    chain: list[str] = []
    for name in (primary, fast or "", *fallbacks):
        cleaned = (name or "").strip()
        if cleaned and cleaned not in chain:
            chain.append(cleaned)
    return chain


def classify_llm_error(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    text = f"{type(exc).__name__} {exc}".lower()
    if status == 429 or any(
        token in text
        for token in ("resource_exhausted", "quota", "rate limit", "too many requests")
    ):
        return "quota"
    if status == 503 or any(
        token in text for token in ("unavailable", "high demand", "overloaded", "503")
    ):
        return "overloaded"
    if status == 404 or any(
        token in text for token in ("no longer available", "not_found", "not found", "404")
    ):
        return "unavailable"
    if any(
        token in text
        for token in ("user location", "location is not supported", "failed_precondition")
    ) or ("region" in text and "not supported" in text):
        return "region"
    if any(
        token in text
        for token in (
            "connecterror",
            "connection",
            "proxy",
            "timeout",
            "timed out",
            "network",
            "name or service not known",
            "temporary failure",
        )
    ):
        return "network"
    return "unknown"


def persian_llm_error(reason: str, model: str) -> str:
    name = model or "مدل"
    messages = {
        "quota": (
            f"سهمیهٔ رایگان مدل «{name}» تمام شده است (خطای ۴۲۹). "
            "مدل‌های جایگزین هم پاسخ ندادند. کمی بعد دوباره تلاش کنید یا در گفتگو لایهٔ «سریع» را انتخاب کنید."
        ),
        "overloaded": (
            f"مدل «{name}» الان شلوغ است و پاسخ نداد (خطای ۵۰۳، تقاضای زیاد). "
            "چند لحظه بعد دوباره تلاش کنید."
        ),
        "region": (
            "دسترسی به مدل از این موقعیت جغرافیایی مسدود شده است. "
            "اگر در ایران هستید، HTTPS_PROXY را روی پروکسی محلی بگذارید "
            "(برای v2rayN معمولاً http://host.docker.internal:10809)."
        ),
        "network": (
            "اتصال به سرویس مدل برقرار نشد. پروکسی (HTTP_PROXY و HTTPS_PROXY) و اینترنت را بررسی کنید."
        ),
        "unavailable": (
            f"مدل «{name}» دیگر برای این کلید در دسترس نیست. "
            "پیش‌فرض‌ها را خالی بگذارید تا عامل‌ها به مدل فعلی مهاجرت کنند، یا نام مدل را در ویرایش عامل عوض کنید."
        ),
    }
    return messages.get(
        reason,
        "فراخوانی مدل ناموفق بود. کلید، نام مدل و پروکسی را بررسی کنید.",
    )


def to_provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite assistant tool calls into the OpenAI function-call wire format.

    Graph history stores ``{id, name, arguments}`` with ``arguments`` as a dict.
    Strict providers reject that shape when a tool result follows. Calls that
    already include ``function`` are left unchanged. An empty list is dropped.
    """
    prepared: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "assistant" or "tool_calls" not in message:
            prepared.append(message)
            continue
        calls = [
            _provider_tool_call(call)
            for call in message.get("tool_calls") or []
            if isinstance(call, dict)
        ]
        rewritten = {key: value for key, value in message.items() if key != "tool_calls"}
        if calls:
            rewritten["tool_calls"] = calls
        prepared.append(rewritten)
    return prepared


def _provider_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    if "function" in call:
        return call
    arguments = call.get("arguments", {})
    if not isinstance(arguments, str):
        payload = arguments if isinstance(arguments, dict) else {}
        arguments = json.dumps(payload, ensure_ascii=False)
    return {
        "id": call.get("id") or "",
        "type": "function",
        "function": {"name": call.get("name") or "", "arguments": arguments},
    }


def api_base_for(model: str) -> str:
    # LiteLLM already targets OpenRouter. Forcing LLM_API_BASE (for example GapGPT)
    # onto these calls would send them to the wrong host.
    if model.startswith("openrouter/"):
        return ""
    if model.startswith("gemini/") and settings.gemini_api_base.strip():
        return settings.gemini_api_base.strip()
    return settings.llm_api_base.strip()


def _retryable(reason: str) -> bool:
    return reason in {"quota", "overloaded", "network"}


async def stream_model(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    tools: list[dict[str, Any]] | None = None,
    fast_model: str | None = None,
    fallback_models: list[str] | None = None,
    notify: Any = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yield ('token', str) pieces, then ('tools', list) if the model called tools.

    Retry 429, 503, and connection errors with backoff. Then try the fast tier
    and `MODEL_FALLBACKS`. A 404 skips straight to the next model.
    """
    configure_litellm()
    chain = build_model_chain(
        model,
        fast_model,
        settings.model_fallback_list() if fallback_models is None else fallback_models,
    )
    if not chain:
        raise LLMCallError("unknown", model, persian_llm_error("unknown", model))

    last_reason = "unknown"
    last_model = chain[-1]
    for candidate in chain:
        attempts = max(1, settings.llm_retry_attempts)
        for attempt in range(attempts):
            emitted = False
            try:
                async for event in _stream_once(
                    model=candidate,
                    messages=messages,
                    temperature=temperature,
                    tools=tools,
                ):
                    emitted = True
                    yield event
                if candidate != model:
                    logger.info("llm fallback succeeded model=%s", candidate)
                    if notify:
                        notify(
                            "model_switch",
                            {"from": model, "to": candidate, "reason": last_reason},
                        )
                return
            except Exception as exc:
                reason = classify_llm_error(exc)
                last_reason = reason
                last_model = candidate
                logger.warning(
                    "llm call failed model=%s attempt=%s reason=%s error=%s",
                    candidate,
                    attempt + 1,
                    reason,
                    exc,
                )
                if emitted:
                    raise LLMCallError(
                        reason, candidate, persian_llm_error(reason, candidate)
                    ) from exc
                if reason == "unavailable" or reason == "region":
                    break
                if _retryable(reason) and attempt + 1 < attempts:
                    if notify:
                        notify(
                            "retry",
                            {"model": candidate, "attempt": attempt + 1, "reason": reason},
                        )
                    await asyncio.sleep(settings.llm_retry_base_seconds * (2**attempt))
                    continue
                break
    raise LLMCallError(last_reason, last_model, persian_llm_error(last_reason, last_model))


async def _stream_once(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    tools: list[dict[str, Any]] | None,
) -> AsyncIterator[tuple[str, Any]]:
    import litellm

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": to_provider_messages(messages),
        "temperature": temperature,
        "stream": True,
    }
    base = api_base_for(model)
    if base:
        kwargs["api_base"] = base
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


async def complete_model(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    tools: list[dict[str, Any]] | None = None,
    fast_model: str | None = None,
    fallback_models: list[str] | None = None,
) -> dict[str, Any]:
    """Non-streaming completion with the same retry and fallback policy as streaming."""
    configure_litellm()
    chain = build_model_chain(
        model,
        fast_model,
        settings.model_fallback_list() if fallback_models is None else fallback_models,
    )
    if not chain:
        raise LLMCallError("unknown", model, persian_llm_error("unknown", model))
    last_reason = "unknown"
    last_model = chain[-1]
    for candidate in chain:
        attempts = max(1, settings.llm_retry_attempts)
        for attempt in range(attempts):
            try:
                return await _complete_once(
                    model=candidate,
                    messages=messages,
                    temperature=temperature,
                    tools=tools,
                )
            except Exception as exc:
                reason = classify_llm_error(exc)
                last_reason = reason
                last_model = candidate
                logger.warning(
                    "llm completion failed model=%s attempt=%s reason=%s error=%s",
                    candidate,
                    attempt + 1,
                    reason,
                    exc,
                )
                if reason in {"unavailable", "region"}:
                    break
                if _retryable(reason) and attempt + 1 < attempts:
                    await asyncio.sleep(settings.llm_retry_base_seconds * (2**attempt))
                    continue
                break
    raise LLMCallError(last_reason, last_model, persian_llm_error(last_reason, last_model))


async def _complete_once(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    import litellm

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": to_provider_messages(messages),
        "temperature": temperature,
    }
    base = api_base_for(model)
    if base:
        kwargs["api_base"] = base
    if tools:
        kwargs["tools"] = tools
    response = await litellm.acompletion(**kwargs)
    message = response.choices[0].message
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        raw = call.function.arguments or "{}"
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError:
            arguments = {}
        calls.append(
            {
                "id": call.id,
                "name": call.function.name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        )
    return {"content": message.content or "", "tool_calls": calls}
