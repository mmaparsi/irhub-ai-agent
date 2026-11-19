"""Provider-aware model defaults.

Empty `MODEL_STRONG_DEFAULT` / `MODEL_FAST_DEFAULT` means "pick from the keys
that are actually configured". A single provider is used for both tiers.
Mixed keys, or no keys, keep the original cross-provider pair so existing
deployments do not move unless that pair's provider is missing.
"""

from __future__ import annotations

ANTHROPIC_STRONG = "anthropic/claude-sonnet-4-5"
ANTHROPIC_FAST = "anthropic/claude-haiku-4-5"
OPENAI_STRONG = "openai/gpt-4o"
OPENAI_FAST = "openai/gpt-4o-mini"
GEMINI_STRONG = "gemini/gemini-2.5-pro"
GEMINI_FAST = "gemini/gemini-2.5-flash"

# Pair written by the first seed, before defaults followed the configured key.
LEGACY_STRONG = ANTHROPIC_STRONG
LEGACY_FAST = OPENAI_FAST

# Models this app itself may write. Anything else is treated as an admin choice
# when `model_*_is_default` was never recorded.
KNOWN_DEFAULT_MODELS = frozenset(
    {
        ANTHROPIC_STRONG,
        ANTHROPIC_FAST,
        OPENAI_STRONG,
        OPENAI_FAST,
        GEMINI_STRONG,
        GEMINI_FAST,
    }
)

GEMINI_EMBEDDING_MODEL = "gemini/text-embedding-004"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


def auto_models(*, anthropic: bool, openai: bool, gemini: bool) -> tuple[str, str]:
    if gemini and not anthropic and not openai:
        return GEMINI_STRONG, GEMINI_FAST
    if anthropic and not openai and not gemini:
        return ANTHROPIC_STRONG, ANTHROPIC_FAST
    if openai and not anthropic and not gemini:
        return OPENAI_STRONG, OPENAI_FAST
    return LEGACY_STRONG, LEGACY_FAST


def provider_configured(
    model: str,
    *,
    anthropic: bool,
    openai: bool,
    gemini: bool,
) -> bool:
    provider = (model or "").split("/", 1)[0].lower()
    if provider == "anthropic":
        return anthropic
    if provider == "openai":
        return openai
    if provider in {"gemini", "google"}:
        return gemini
    return False


def should_follow_default(
    model: str,
    is_default: bool | None,
    *,
    anthropic: bool,
    openai: bool,
    gemini: bool,
) -> bool:
    """True when startup may replace this stored model.

    `True` means the row is still on an automatic default. `False` means an
    admin set it and it must be left alone. `None` is a row from before the
    flag existed: replace it only when it still holds a shipped default whose
    provider key is absent.
    """
    if is_default is True:
        return True
    if is_default is False:
        return False
    return model in KNOWN_DEFAULT_MODELS and not provider_configured(
        model,
        anthropic=anthropic,
        openai=openai,
        gemini=gemini,
    )


def apply_default_models(
    agent,
    *,
    strong: str,
    fast: str,
    anthropic: bool,
    openai: bool,
    gemini: bool,
) -> bool:
    """Update one agent in place. Returns whether a stored value changed."""
    changed = False
    if should_follow_default(
        agent.model_strong,
        agent.model_strong_is_default,
        anthropic=anthropic,
        openai=openai,
        gemini=gemini,
    ):
        if agent.model_strong != strong:
            agent.model_strong = strong
            changed = True
        if agent.model_strong_is_default is not True:
            agent.model_strong_is_default = True
            changed = True
    if should_follow_default(
        agent.model_fast,
        agent.model_fast_is_default,
        anthropic=anthropic,
        openai=openai,
        gemini=gemini,
    ):
        if agent.model_fast != fast:
            agent.model_fast = fast
            changed = True
        if agent.model_fast_is_default is not True:
            agent.model_fast_is_default = True
            changed = True
    return changed
