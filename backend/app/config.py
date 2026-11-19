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
    # Empty means "not set": resolved_model_defaults() chooses from the keys.
    model_strong_default: str = ""
    model_fast_default: str = ""
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
        if self.langfuse_public_key:
            os.environ["LANGFUSE_PUBLIC_KEY"] = self.langfuse_public_key
        if self.langfuse_secret_key:
            os.environ["LANGFUSE_SECRET_KEY"] = self.langfuse_secret_key
        if self.langfuse_host:
            os.environ["LANGFUSE_HOST"] = self.langfuse_host


settings = Settings()
settings.export_provider_env()
