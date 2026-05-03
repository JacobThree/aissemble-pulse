"""Smoke tests for package import and settings."""

import pytest

from city_pulse import __version__
from city_pulse.config import Settings, get_settings


def test_version_is_semverish() -> None:
    parts = __version__.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])


def test_settings_defaults() -> None:
    get_settings.cache_clear()
    s = get_settings()
    assert s.database_url.startswith("postgresql://")
    assert s.redis_url.startswith("redis://")
    assert s.yolo_endpoint.startswith("http")


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://override:secret@db:5432/app")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("YOLO_ENDPOINT", "http://yolo:9999")
    s = get_settings()
    assert s.database_url == "postgresql://override:secret@db:5432/app"
    assert s.redis_url == "redis://redis:6379/1"
    assert s.yolo_endpoint == "http://yolo:9999"
    get_settings.cache_clear()


def test_settings_explicit_construct() -> None:
    s = Settings(
        database_url="postgresql://a/b",
        redis_url="redis://c/0",
        yolo_endpoint="http://d",
    )
    assert isinstance(s, Settings)
