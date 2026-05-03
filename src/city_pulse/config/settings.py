"""Application settings from environment (Pydantic Settings)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed config loaded from env (SCREAMING_SNAKE keys via pydantic-settings)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://city_pulse:city_pulse@localhost:5433/city_pulse",
        description="Timescale URL (Compose DB mapped to localhost:5433)",
    )
    database_readonly_url: str = Field(
        default=(
            "postgresql://city_pulse_reader:city_pulse_reader@localhost:5433/city_pulse"
        ),
        description="Read-only role for Streamlit / dashboards",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis for frame queue",
    )
    yolo_endpoint: str = Field(
        default="http://localhost:8080",
        description="MLServer HTTP base (OIP REST; gRPC often 8081 in Compose)",
    )

    ingest_m3u8_url: str | None = Field(
        default=None,
        description="Public HLS playlist URL (.m3u8) for ingest loop",
    )
    ingest_camera_key: str = Field(
        default="cam-default",
        description="Stable label stored with each frame",
    )
    ingest_sample_interval_seconds: float = Field(
        default=7.5,
        gt=0,
        description="Sleep between successful frame samples",
    )
    ingest_queue_key: str = Field(
        default="city_pulse:frames",
        description="Redis list key for frame JSON payloads",
    )
    ingest_heartbeat_key: str | None = Field(
        default="city_pulse:ingest:last_success_at",
        description=(
            "Redis string key set to ISO timestamp after each successful enqueue; "
            "empty/null disables"
        ),
    )
    ingest_max_queue_length: int = Field(
        default=64,
        ge=1,
        description="Max queued frames (oldest evicted on overflow)",
    )
    ingest_jpeg_quality: int = Field(
        default=85,
        ge=1,
        le=100,
        description="JPEG quality for frame_b64 payload",
    )
    ingest_backoff_initial_seconds: float = Field(
        default=1.0,
        gt=0,
        description="First backoff sleep after stream/read failure",
    )
    ingest_backoff_max_seconds: float = Field(
        default=60.0,
        gt=0,
        description="Backoff ceiling",
    )
    ingest_backoff_multiplier: float = Field(
        default=2.0,
        gt=1.0,
        description="Backoff multiplier after each consecutive failure",
    )

    vision_model_name: str = Field(
        default="yolov8",
        description="MLServer model folder name (path segment /v2/models/{name}/infer)",
    )
    vision_vehicle_labels: str = Field(
        default="car,truck,bus,motorcycle",
        description="Comma-separated COCO-style labels counted as vehicles",
    )
    vision_min_confidence: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum detector score to count a vehicle label",
    )
    vision_http_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description="HTTP client timeout for MLServer infer",
    )
    vision_brpop_timeout_seconds: int = Field(
        default=5,
        ge=1,
        description="Redis BRPOP block timeout seconds",
    )
    vision_db_pool_max: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Max psycopg pool connections for vision worker",
    )

    sumy_endpoint: str = Field(
        default="http://localhost:8090",
        description=(
            "MLServer HTTP base for Sumy (Compose maps container 8080 → host 8090)"
        ),
    )
    sumy_model_name: str = Field(
        default="sumy",
        description="MLServer model name for /v2/models/{name}/infer",
    )
    sumy_http_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        description="HTTP timeout for Sumy infer",
    )
    daily_brief_db_pool_max: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Max psycopg pool connections for daily brief job",
    )

    @field_validator("ingest_heartbeat_key", mode="before")
    @classmethod
    def _none_if_blank(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return str(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (clear cache in tests when env changes)."""
    return Settings()
