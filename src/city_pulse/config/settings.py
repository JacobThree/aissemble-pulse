"""Application settings from environment (Pydantic Settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed config loaded from env (SCREAMING_SNAKE keys via pydantic-settings)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://city_pulse:city_pulse@localhost:5432/city_pulse",
        description="Timescale/Postgres connection URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis for frame queue",
    )
    yolo_endpoint: str = Field(
        default="http://localhost:8081",
        description="MLServer / OIP base URL for YOLO inference",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (clear cache in tests when env changes)."""
    return Settings()
