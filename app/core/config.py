"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CaseFlow", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    database_url: str = Field(
        default="postgresql+psycopg://caseflow:caseflow@localhost:5432/caseflow",
        alias="DATABASE_URL",
    )
    test_database_url: str = Field(default="sqlite+pysqlite:///:memory:", alias="TEST_DATABASE_URL")

    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_ttl_minutes: int = Field(default=15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(default=30, alias="REFRESH_TOKEN_TTL_DAYS")
    password_reset_ttl_minutes: int = Field(default=30, alias="PASSWORD_RESET_TTL_MINUTES")
    auth_session_activity_update_interval_seconds: int = Field(
        default=60,
        alias="AUTH_SESSION_ACTIVITY_UPDATE_INTERVAL_SECONDS",
    )
    document_processing_mode: Literal["inline", "worker"] = Field(
        default="inline",
        alias="DOCUMENT_PROCESSING_MODE",
    )
    webhook_delivery_mode: Literal["sync", "worker"] = Field(
        default="sync",
        alias="WEBHOOK_DELIVERY_MODE",
    )
    email_delivery_mode: Literal["sync", "worker"] = Field(
        default="sync",
        alias="EMAIL_DELIVERY_MODE",
    )
    email_delivery_backend: Literal["local", "smtp"] = Field(
        default="local",
        alias="EMAIL_DELIVERY_BACKEND",
    )
    job_retry_base_delay_seconds: int = Field(default=30, alias="JOB_RETRY_BASE_DELAY_SECONDS")
    webhook_retry_base_delay_seconds: int = Field(
        default=30,
        alias="WEBHOOK_RETRY_BASE_DELAY_SECONDS",
    )
    email_retry_base_delay_seconds: int = Field(default=30, alias="EMAIL_RETRY_BASE_DELAY_SECONDS")
    worker_poll_interval_seconds: int = Field(default=30, alias="WORKER_POLL_INTERVAL_SECONDS")
    invitation_ttl_hours: int = Field(default=168, alias="INVITATION_TTL_HOURS")
    local_storage_path: Path = Field(default=Path("./storage"), alias="LOCAL_STORAGE_PATH")
    local_email_sink_path: Path = Field(
        default=Path("./.tmp/emails"),
        alias="LOCAL_EMAIL_SINK_PATH",
    )
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="no-reply@caseflow.local", alias="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="CaseFlow", alias="SMTP_FROM_NAME")
    smtp_use_starttls: bool = Field(default=True, alias="SMTP_USE_STARTTLS")
    smtp_use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    smtp_timeout_seconds: int = Field(default=10, alias="SMTP_TIMEOUT_SECONDS")
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
