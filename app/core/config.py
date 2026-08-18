"""Application configuration loaded from the environment.

All runtime configuration is centralized here via ``pydantic-settings`` so the
rest of the codebase never reads ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class RateLimitRule:
    """A parsed ``count/window`` rate-limit rule (e.g. ``10/60``)."""

    __slots__ = ("limit", "window")

    def __init__(self, raw: str) -> None:
        count, _, window = raw.partition("/")
        self.limit = int(count)
        self.window = int(window or 60)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Aahaar API"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://aahaar:aahaar@localhost:5433/aahaar"

    # Security / JWT
    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    jwt_algorithm: str = "HS256"

    # CORS — NoDecode lets us accept a plain comma-separated env string
    # (pydantic-settings would otherwise try to JSON-decode a list field).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:3000",
        ]
    )

    # Realtime
    redis_url: str = ""

    # Customer app base URL (used when building QR target links)
    customer_app_base_url: str = "http://localhost:5174"

    # Clerk (Google SSO). Leave blank to disable Google login.
    clerk_secret_key: str = ""
    clerk_authorized_parties: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
        ]
    )

    # Super admins skip the waitlist and can approve kitchens.
    super_admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Join notifications (Gmail SMTP + optional Twilio WhatsApp).
    admin_notify_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    admin_whatsapp_to: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""

    # Web Push (optional PEM). Empty = derive a stable key from SECRET_KEY.
    vapid_private_key: str = ""
    vapid_contact: str = "mailto:hello@aahaar.app"

    # Rate limiting rules (raw "count/window" strings from env)
    rate_limit_login: str = "10/60"
    rate_limit_order: str = "30/60"
    rate_limit_public: str = "120/60"

    @field_validator(
        "cors_origins", "clerk_authorized_parties", "super_admin_emails", mode="before"
    )
    @classmethod
    def _split_cors(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def browser_origins(self) -> list[str]:
        """Origins allowed for credentialed browser traffic. Never ``*``."""
        if self.cors_origins:
            return self.cors_origins
        return [] if self.is_production else ["http://localhost:5174"]

    @property
    def clerk_enabled(self) -> bool:
        return bool(self.clerk_secret_key.strip())

    def is_super_admin_email(self, email: str) -> bool:
        wanted = {item.strip().lower() for item in self.super_admin_emails if item.strip()}
        return email.strip().lower() in wanted

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL (psycopg/psycopg2 or plain) for tooling that needs it."""
        return self.database_url.replace("+asyncpg", "")

    def rate_rule(self, name: str) -> RateLimitRule:
        return RateLimitRule(getattr(self, f"rate_limit_{name}"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
