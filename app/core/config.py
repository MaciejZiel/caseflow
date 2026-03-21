"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    invitation_ttl_hours: int = Field(default=168, alias="INVITATION_TTL_HOURS")
    local_storage_path: Path = Field(default=Path("./storage"), alias="LOCAL_STORAGE_PATH")
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, alias="MAX_UPLOAD_SIZE_BYTES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
