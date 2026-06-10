from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Mandate Finder API"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./mandate_finder.db"
    redis_url: str = "redis://localhost:6379/0"
    api_rate_limit_solo: int = 100
    api_rate_limit_professional: int = 1000
    api_rate_limit_agency: int = 5000
    api_rate_window_seconds: int = 60
    webhook_max_retries: int = 3
    webhook_retry_base_delay: float = 1.0
    webhook_retry_max_delay: float = 60.0
    webhook_delivery_log_days: int = 30
    webhook_default_timeout: int = 10
    api_key_bytes: int = 32
    api_key_prefix: str = "mf_"
    openapi_url: str = "/docs"
    docs_url: str = "/docs"

    model_config = {"env_prefix": "MF_", "env_file": ".env"}


settings = Settings()
