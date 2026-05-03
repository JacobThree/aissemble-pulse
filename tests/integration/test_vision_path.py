"""Vision worker path with mocked MLServer + DB insert."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast

import fakeredis
import httpx
import pytest
from psycopg_pool import ConnectionPool
from pytest_httpserver import HTTPServer

from city_pulse.config.settings import Settings
from city_pulse.ingest.models import FramePayload
from city_pulse.workers import vision_worker


class _DummyPool:
    """Minimal pool stub (insert_vehicle_count patched in tests)."""

    @contextmanager
    def connection(self) -> Iterator[None]:
        yield None


@contextmanager
def _patch_insert(
    monkeypatch: pytest.MonkeyPatch, captured: list[dict[str, Any]]
) -> Iterator[None]:
    def _recorder(conn: object, **kwargs: object) -> None:
        captured.append(dict(kwargs))

    monkeypatch.setattr(
        vision_worker,
        "insert_vehicle_count",
        _recorder,
    )
    yield


def test_process_next_happy_path(
    httpserver: HTTPServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infer_path = "/v2/models/yolov8/infer"
    httpserver.expect_request(infer_path, method="POST").respond_with_json(
        {
            "model_name": "yolov8",
            "outputs": [
                {
                    "name": "labels",
                    "datatype": "BYTES",
                    "shape": [2],
                    "data": ["car", "person"],
                },
                {
                    "name": "scores",
                    "datatype": "FP32",
                    "shape": [2],
                    "data": [0.95, 0.4],
                },
            ],
        }
    )

    base_url = httpserver.url_for("/").rstrip("/")
    settings = Settings(
        yolo_endpoint=base_url,
        redis_url="redis://unused",
        database_url="postgresql://unused",
        vision_model_name="yolov8",
        vision_brpop_timeout_seconds=1,
    )

    r = fakeredis.FakeRedis(decode_responses=True)
    payload = FramePayload(
        camera_key="cam-x",
        captured_at=datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC),
        frame_b64="Zm9v",
    )
    r.lpush(settings.ingest_queue_key, payload.model_dump_json())

    captured: list[dict[str, Any]] = []
    with _patch_insert(monkeypatch, captured):
        client = httpx.Client(timeout=30.0)
        pool = cast(ConnectionPool, _DummyPool())
        assert vision_worker.process_next(
            settings=settings,
            redis_client=r,
            http_client=client,
            pool=pool,
        )
        client.close()

    assert len(captured) == 1
    row = captured[0]
    assert row["camera_location"] == "cam-x"
    assert row["vehicle_count"] == 1
