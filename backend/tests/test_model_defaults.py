from __future__ import annotations

import os

from app.config import Settings
from app.knowledge.embeddings import embed_text
from app.llm_defaults import (
    ANTHROPIC_FAST,
    ANTHROPIC_STRONG,
    GEMINI_FAST,
    GEMINI_STRONG,
    LEGACY_FAST,
    LEGACY_STRONG,
    OPENAI_FAST,
    OPENAI_STRONG,
    apply_default_models,
    auto_models,
)
from app.models import Agent
from tests.conftest import auth_header


def _settings(**kwargs: str) -> Settings:
    base = {
        "mock_llm": "auto",
        "anthropic_api_key": "",
        "openai_api_key": "",
        "gemini_api_key": "",
        "model_strong_default": "",
        "model_fast_default": "",
    }
    base.update(kwargs)
    return Settings(**base)


def test_single_provider_defaults() -> None:
    assert auto_models(anthropic=False, openai=False, gemini=True) == (GEMINI_STRONG, GEMINI_FAST)
    assert auto_models(anthropic=True, openai=False, gemini=False) == (
        ANTHROPIC_STRONG,
        ANTHROPIC_FAST,
    )
    assert auto_models(anthropic=False, openai=True, gemini=False) == (OPENAI_STRONG, OPENAI_FAST)
    assert auto_models(anthropic=True, openai=True, gemini=False) == (LEGACY_STRONG, LEGACY_FAST)
    assert auto_models(anthropic=False, openai=False, gemini=False) == (LEGACY_STRONG, LEGACY_FAST)


def test_gemini_key_disables_mock_and_is_exported(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = _settings(gemini_api_key="gem-test")
    assert settings.llm_is_mock() is False
    assert settings.resolved_model_defaults() == (GEMINI_STRONG, GEMINI_FAST)
    settings.export_provider_env()
    assert os.environ["GEMINI_API_KEY"] == "gem-test"


def test_explicit_model_overrides_gemini_default() -> None:
    settings = _settings(
        gemini_api_key="gem-test",
        model_strong_default="custom/strong",
    )
    assert settings.resolved_model_defaults() == ("custom/strong", GEMINI_FAST)


def test_legacy_defaults_without_keys_follow_gemini() -> None:
    agent = _agent(LEGACY_STRONG, LEGACY_FAST, None, None)
    apply_default_models(
        agent,
        strong=GEMINI_STRONG,
        fast=GEMINI_FAST,
        anthropic=False,
        openai=False,
        gemini=True,
    )
    assert agent.model_strong == GEMINI_STRONG
    assert agent.model_fast == GEMINI_FAST
    assert agent.model_strong_is_default is True
    assert agent.model_fast_is_default is True


def test_custom_models_are_not_overwritten() -> None:
    agent = _agent("my/negotiator", "my/fast", False, False)
    apply_default_models(
        agent,
        strong=GEMINI_STRONG,
        fast=GEMINI_FAST,
        anthropic=False,
        openai=False,
        gemini=True,
    )
    assert agent.model_strong == "my/negotiator"
    assert agent.model_fast == "my/fast"
    assert agent.model_strong_is_default is False


def test_legacy_model_with_a_key_stays() -> None:
    agent = _agent(LEGACY_STRONG, LEGACY_FAST, None, None)
    apply_default_models(
        agent,
        strong=GEMINI_STRONG,
        fast=GEMINI_FAST,
        anthropic=True,
        openai=False,
        gemini=True,
    )
    assert agent.model_strong == LEGACY_STRONG
    assert agent.model_strong_is_default is None
    assert agent.model_fast == GEMINI_FAST
    assert agent.model_fast_is_default is True


def test_retired_gemini_25_migrates_while_the_key_is_present() -> None:
    agent = _agent("gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash", None, None)
    apply_default_models(
        agent,
        strong=GEMINI_STRONG,
        fast=GEMINI_FAST,
        anthropic=False,
        openai=False,
        gemini=True,
    )
    assert agent.model_strong == GEMINI_STRONG
    assert agent.model_fast == GEMINI_FAST
    assert agent.model_strong_is_default is True
    assert agent.model_fast_is_default is True


def test_flagged_default_follows_new_resolution() -> None:
    agent = _agent(LEGACY_STRONG, LEGACY_FAST, True, True)
    apply_default_models(
        agent,
        strong=GEMINI_STRONG,
        fast=GEMINI_FAST,
        anthropic=True,
        openai=True,
        gemini=True,
    )
    assert agent.model_strong == GEMINI_STRONG
    assert agent.model_fast == GEMINI_FAST


def test_seeded_agents_use_resolved_defaults(client) -> None:
    health = client.get("/api/health").json()
    headers = auth_header(client)
    agents = client.get("/api/agents", headers=headers).json()
    builtins = [item for item in agents if item["source"] == "builtin"]
    assert {
        "research",
        "lead_generation",
        "sales_negotiation",
        "consulting",
        "supervisor",
    } <= {item["slug"] for item in builtins}
    for item in builtins:
        assert item["model_strong"] == health["model_strong_default"]
        assert item["model_fast"] == health["model_fast_default"]
        assert item["model_strong_is_default"] is True
        assert item["model_fast_is_default"] is True


def test_reseed_updates_legacy_rows_and_keeps_custom(client, monkeypatch) -> None:
    from sqlalchemy import select

    from app.config import settings
    from app.database import open_session
    from app.seed import seed_core

    monkeypatch.setattr(settings, "gemini_api_key", "gem-test")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "model_strong_default", "")
    monkeypatch.setattr(settings, "model_fast_default", "")

    session = open_session()
    try:
        research = session.scalar(select(Agent).where(Agent.slug == "research"))
        assert research is not None
        research.model_strong = LEGACY_STRONG
        research.model_fast = LEGACY_FAST
        research.model_strong_is_default = None
        research.model_fast_is_default = None
        sales = session.scalar(select(Agent).where(Agent.slug == "sales_negotiation"))
        assert sales is not None
        sales.model_strong = "my/negotiator"
        sales.model_fast = "my/fast"
        sales.model_strong_is_default = False
        sales.model_fast_is_default = False
        session.commit()
        seed_core(session)
        session.commit()
        session.refresh(research)
        session.refresh(sales)
        assert research.model_strong == GEMINI_STRONG
        assert research.model_fast == GEMINI_FAST
        assert sales.model_strong == "my/negotiator"
        assert sales.model_fast == "my/fast"
    finally:
        session.close()


def test_gemini_embedding_is_padded_to_column_width(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "mock_llm", "false")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "gem-test")
    import litellm

    def fake_embedding(**kwargs):
        assert kwargs["model"] == "gemini/gemini-embedding-001"
        assert kwargs["dimensions"] == 768
        return {"data": [{"embedding": [0.5, 0.25]}]}

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    vector = embed_text("سلام")
    assert len(vector) == 1536
    assert vector[0] == 0.5
    assert vector[1] == 0.25
    assert vector[2] == 0.0


def test_openai_embedding_wins_when_both_keys_exist(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "mock_llm", "false")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "gemini_api_key", "gem-test")
    import litellm

    def fake_embedding(**kwargs):
        assert kwargs["model"] == "text-embedding-3-small"
        return {"data": [{"embedding": [0.1] * 1536}]}

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    vector = embed_text("سلام")
    assert len(vector) == 1536
    assert vector[0] == 0.1


def test_mock_mode_does_not_call_the_embedding_provider(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "mock_llm", "true")
    monkeypatch.setattr(settings, "gemini_api_key", "gem-test")
    import litellm

    def fail_embedding(**_kwargs):
        raise AssertionError("provider embedding should not run in mock mode")

    monkeypatch.setattr(litellm, "embedding", fail_embedding)
    vector = embed_text("سلام")
    assert len(vector) == 1536


def _agent(
    strong: str,
    fast: str,
    strong_default: bool | None,
    fast_default: bool | None,
) -> Agent:
    return Agent(
        slug="sample",
        name="Sample",
        name_fa="نمونه",
        system_prompt="تو یک عامل آزمایشی هستی.",
        model_strong=strong,
        model_fast=fast,
        model_strong_is_default=strong_default,
        model_fast_is_default=fast_default,
    )
