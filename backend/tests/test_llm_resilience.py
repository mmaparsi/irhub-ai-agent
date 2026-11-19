from __future__ import annotations

import asyncio

import pytest

from app.agents.llm import (
    LLMCallError,
    build_model_chain,
    classify_llm_error,
    configure_litellm,
    persian_llm_error,
    stream_model,
)
from app.config import Settings, settings


class _StatusError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_chain_is_primary_then_fast_then_fallbacks() -> None:
    chain = build_model_chain(
        "gemini/gemini-pro-latest",
        "gemini/gemini-flash-latest",
        ["gemini/gemini-3.8-flash", "gemini/gemini-flash-latest", "gemini/gemini-3.5-flash"],
    )
    assert chain == [
        "gemini/gemini-pro-latest",
        "gemini/gemini-flash-latest",
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash",
    ]


def test_error_reasons_and_persian_text() -> None:
    assert classify_llm_error(_StatusError(429, "quota exceeded")) == "quota"
    assert classify_llm_error(_StatusError(503, "high demand")) == "overloaded"
    assert (
        classify_llm_error(_StatusError(404, "no longer available to new users")) == "unavailable"
    )
    assert classify_llm_error(RuntimeError("User location is not supported")) == "region"
    assert classify_llm_error(ConnectionError("proxy connection failed")) == "network"
    assert "سهمیه" in persian_llm_error("quota", "gemini/gemini-pro-latest")
    assert "شلوغ" in persian_llm_error("overloaded", "gemini/gemini-flash-latest")
    assert "موقعیت" in persian_llm_error("region", "gemini/gemini-pro-latest")
    assert "اتصال" in persian_llm_error("network", "gemini/gemini-flash-latest")
    assert "در دسترس نیست" in persian_llm_error("unavailable", "gemini/gemini-2.5-pro")


def test_drop_params_is_enabled() -> None:
    configure_litellm()
    import litellm

    assert litellm.drop_params is True


def test_quota_falls_back_without_retrying_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] != "gemini/gemini-flash-latest":
            raise _StatusError(429, "quota exceeded")

        async def chunks():
            yield _token_chunk("سلام از فلش")

        return chunks()

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(settings, "llm_retry_attempts", 1)
    monkeypatch.setattr("app.agents.llm.asyncio.sleep", no_sleep)
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    events = asyncio.run(
        _collect(
            model="gemini/gemini-pro-latest",
            fast_model="gemini/gemini-flash-latest",
            fallback_models=["gemini/gemini-3.8-flash"],
        )
    )
    assert calls == ["gemini/gemini-pro-latest", "gemini/gemini-flash-latest"]
    assert events == [("token", "سلام از فلش")]


def test_overloaded_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    slept: list[float] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        if len(calls) == 1:
            raise _StatusError(503, "The model is overloaded")

        async def chunks():
            yield _token_chunk("بازگشت")

        return chunks()

    async def record_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(settings, "llm_retry_attempts", 2)
    monkeypatch.setattr(settings, "llm_retry_base_seconds", 0.25)
    monkeypatch.setattr("app.agents.llm.asyncio.sleep", record_sleep)
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    events = asyncio.run(
        _collect(model="gemini/gemini-flash-latest", fast_model=None, fallback_models=[])
    )
    assert calls == ["gemini/gemini-flash-latest", "gemini/gemini-flash-latest"]
    assert slept == [0.25]
    assert events == [("token", "بازگشت")]


def test_all_models_fail_with_quota_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_acompletion(**_kwargs):
        raise _StatusError(429, "quota exceeded")

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(settings, "llm_retry_attempts", 1)
    monkeypatch.setattr("app.agents.llm.asyncio.sleep", no_sleep)
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    with pytest.raises(LLMCallError) as caught:
        asyncio.run(
            _collect(
                model="gemini/gemini-pro-latest",
                fast_model="gemini/gemini-flash-latest",
                fallback_models=[],
            )
        )
    assert caught.value.reason == "quota"
    assert "سهمیه" in caught.value.user_message


def test_proxy_and_api_base_export(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("GEMINI_API_BASE", raising=False)
    configured = Settings(
        https_proxy="http://host.docker.internal:10809",
        gemini_api_base="https://generativelanguage.googleapis.com",
        llm_api_base="",
        gemini_api_key="",
        anthropic_api_key="",
        openai_api_key="",
    )
    configured.export_provider_env()
    assert configured.model_fallback_list() == []
    explicit = Settings(model_fallbacks="gemini/gemini-3.8-flash, gemini/gemini-3.5-flash")
    assert explicit.model_fallback_list() == [
        "gemini/gemini-3.8-flash",
        "gemini/gemini-3.5-flash",
    ]
    assert __import__("os").environ["HTTPS_PROXY"] == "http://host.docker.internal:10809"
    assert __import__("os").environ["https_proxy"] == "http://host.docker.internal:10809"
    assert (
        __import__("os").environ["GEMINI_API_BASE"] == "https://generativelanguage.googleapis.com"
    )


async def _collect(**kwargs: object) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    async for kind, payload in stream_model(
        model=str(kwargs["model"]),
        messages=[{"role": "user", "content": "سلام"}],
        temperature=0.2,
        fast_model=kwargs.get("fast_model") if isinstance(kwargs.get("fast_model"), str) else None,
        fallback_models=list(kwargs.get("fallback_models") or []),
    ):
        events.append((kind, payload))
    return events


def _token_chunk(text: str):
    delta = type("Delta", (), {"content": text, "tool_calls": None})()
    choice = type("Choice", (), {"delta": delta})()
    return type("Chunk", (), {"choices": [choice]})()
