from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import (
    DEFAULT_FAST_MODEL,
    DEFAULT_STRONG_MODEL,
    MAX_DISCOUNT_PERCENT_DEFAULT,
)

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
    model_strong_default: str = DEFAULT_STRONG_MODEL
    model_fast_default: str = DEFAULT_FAST_MODEL
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    max_discount_percent: float = MAX_DISCOUNT_PERCENT_DEFAULT

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def llm_is_mock(self) -> bool:
        mode = self.mock_llm.strip().lower()
        has_key = bool(self.anthropic_api_key or self.openai_api_key)
        if mode in {"1", "true", "yes", "on"}:
            return True
        if mode in {"0", "false", "no", "off"}:
            return False
        return not has_key

    def export_provider_env(self) -> None:
        """LiteLLM reads provider keys from the process environment."""
        if self.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.langfuse_public_key:
            os.environ["LANGFUSE_PUBLIC_KEY"] = self.langfuse_public_key
        if self.langfuse_secret_key:
            os.environ["LANGFUSE_SECRET_KEY"] = self.langfuse_secret_key
        if self.langfuse_host:
            os.environ["LANGFUSE_HOST"] = self.langfuse_host


settings = Settings()
settings.export_provider_env()
