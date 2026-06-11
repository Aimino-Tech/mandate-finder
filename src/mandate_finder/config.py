from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    PRODUCTION = "production"
    STAGING = "staging"

    @property
    def is_deployed(self) -> bool:
        return self in (self.PRODUCTION, self.STAGING)

    @property
    def is_debug(self) -> bool:
        return self == self.LOCAL


class Settings(BaseSettings):
    app_name: str = "Mandate Finder API"
    environment: Environment = Environment.LOCAL
    debug: bool = True
    secret_key: str = "change-me-in-production"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://mandate:mandate@127.0.0.1:5432/mandate_finder"
    database_url_sync: str = "postgresql+psycopg://mandate:mandate@127.0.0.1:5432/mandate_finder"

    propelauth_api_key: str = ""
    propelauth_auth_url: str = "https://4881448908.propelauthtest.com"

    dev_auth_token: str = "mandate-local-dev-token"
    dev_auth_enabled: bool = False

    # ── Scoring Engine Settings ──────────────────────────────────────
    scoring_default_min_score: float = 0.0
    scoring_contact_threshold: float = 0.7
    scoring_watchlist_threshold: float = 0.4
    scoring_enable_agi_pass: bool = True
    scoring_synonym_map_enabled: bool = True

    cors_origins: ClassVar[list[str]] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MANDATE_",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def _auth_safety_for_environment(self) -> Settings:
        if self.environment != Environment.LOCAL:
            object.__setattr__(self, "dev_auth_enabled", False)
        elif not self.propelauth_api_key.strip():
            object.__setattr__(self, "dev_auth_enabled", True)
        return self

    @property
    def propelauth_configured(self) -> bool:
        return bool(self.propelauth_api_key.strip())

    @property
    def demo_login_available(self) -> bool:
        return self.environment == Environment.LOCAL and not self.propelauth_configured


settings = Settings()
