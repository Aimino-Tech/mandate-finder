from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mandate_finder"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/mandate_finder"
    enable_scheduler: bool = True
    scheduler_interval_seconds: int = 300

    slack_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    default_notify_from: str = "noreply@mandatefinder.com"

    model_config = {"env_prefix": "MF_"}


settings = Settings()
