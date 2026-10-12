"""Application settings loaded from environment variables.

One Settings instance per process. Access via `from alpago.core.config import settings`.
Never read os.environ directly from domain code — it should be reachable from tests
by swapping settings.

Local dev defaults to SQLite + eager Celery. No external services needed.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Database — SQLite file for local dev; Postgres URL on Render
    database_url: str = Field(default="sqlite+aiosqlite:///./alpago_dev.db")

    # Celery / Redis — empty in local dev means Celery runs tasks eagerly in-process
    redis_url: str = ""

    # Auth
    auth_secret: str = Field(min_length=16, default="change-me-change-me-change-me-xxxx")
    allowed_email_domains: str = "alpagomanufacturing.com"

    # Rate limiting — leave unset to auto-disable in local/test and enable elsewhere
    rate_limit_enabled: bool | None = None

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # AI (Claude)
    anthropic_api_key: str = ""
    ai_model_standard: str = "claude-sonnet-5-5"
    ai_model_fast: str = "claude-haiku-5-5"

    # Email
    resend_api_key: str = ""
    email_from: str = "Alpago HR <hr@alpagomanufacturing.com>"

    # WhatsApp
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Storage (R2)
    r2_account_id: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "alpago-hr-local"
    r2_endpoint: str = ""

    # Observability
    sentry_dsn: str = ""

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def celery_eager(self) -> bool:
        """True = Celery runs tasks synchronously in-process (no broker required)."""
        return not self.redis_url or self.env in ("local", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
