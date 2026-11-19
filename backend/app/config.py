from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import MAX_DISCOUNT_PERCENT_DEFAULT
from app.llm_defaults import auto_models

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        extra="ignore",
    )

    app_name: str = "IRHub"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://irhub:irhub@localhost:5432/irhub"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"
    admin_name: str = "مدیر سیستم"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # auto: mock when no provider key is set. true/false force the mode.
    mock_llm: str = "auto"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    gemini_api_base: str = ""
    llm_api_base: str = ""
    # Empty means "not set": resolved_model_defaults() chooses from the keys.
    model_strong_default: str = ""
    model_fast_default: str = ""
    # Tried after the selected tier (and after the fast model, when the tier is strong).
    model_fallbacks: str = ""
    llm_retry_attempts: int = 2
    llm_retry_base_seconds: float = 0.5
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = ""
    searxng_url: str = "http://searxng:8080"
    tavily_api_key: str = ""
    brave_api_key: str = ""
    artifact_dir: str = "data/artifacts"
    task_max_steps: int = 12
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    max_discount_percent: float = MAX_DISCOUNT_PERCENT_DEFAULT

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def has_provider_key(self) -> bool:
        return bool(
            self.anthropic_api_key.strip()
            or self.openai_api_key.strip()
            or self.gemini_api_key.strip()
        )

    def resolved_model_defaults(self) -> tuple[str, str]:
        """Explicit MODEL_*_DEFAULT wins. Otherwise follow the configured key."""
        auto_strong, auto_fast = auto_models(
            anthropic=bool(self.anthropic_api_key.strip()),
            openai=bool(self.openai_api_key.strip()),
            gemini=bool(self.gemini_api_key.strip()),
        )
        strong = self.model_strong_default.strip() or auto_strong
        fast = self.model_fast_default.strip() or auto_fast
        return strong, fast

    def model_fallback_list(self) -> list[str]:
        return [item.strip() for item in self.model_fallbacks.split(",") if item.strip()]

    def llm_is_mock(self) -> bool:
        mode = self.mock_llm.strip().lower()
        if mode in {"1", "true", "yes", "on"}:
            return True
        if mode in {"0", "false", "no", "off"}:
            return False
        return not self.has_provider_key()

    def export_provider_env(self) -> None:
        """LiteLLM reads provider keys from the process environment."""
        if self.anthropic_api_key.strip():
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key.strip()
        if self.openai_api_key.strip():
            os.environ["OPENAI_API_KEY"] = self.openai_api_key.strip()
        if self.gemini_api_key.strip():
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key.strip()
        if self.gemini_api_base.strip():
            os.environ["GEMINI_API_BASE"] = self.gemini_api_base.strip()
        self._export_proxy()
        if self.langfuse_public_key:
            os.environ["LANGFUSE_PUBLIC_KEY"] = self.langfuse_public_key
        if self.langfuse_secret_key:
            os.environ["LANGFUSE_SECRET_KEY"] = self.langfuse_secret_key
        if self.langfuse_host:
            os.environ["LANGFUSE_HOST"] = self.langfuse_host

    def _export_proxy(self) -> None:
        """httpx and LiteLLM read the process environment, including from .env."""
        pairs = (
            ("HTTP_PROXY", "http_proxy", self.http_proxy),
            ("HTTPS_PROXY", "https_proxy", self.https_proxy),
            ("NO_PROXY", "no_proxy", self.no_proxy),
        )
        for upper, lower, value in pairs:
            text = value.strip()
            if not text:
                continue
            os.environ[upper] = text
            os.environ[lower] = text


settings = Settings()
settings.export_provider_env()
