"""Ingest loop with faked OpenCV."""

from types import SimpleNamespace

import fakeredis
import pytest

from city_pulse.config.settings import Settings
from city_pulse.ingest.capture import run_ingest_loop
from city_pulse.ingest.metrics import IngestMetrics


@pytest.fixture
def fake_cv2_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    from city_pulse.ingest import capture as capture_mod

    class FakeCap:
        def __init__(self, url: str) -> None:
            self._url = url

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, object]:
            return True, object()

        def release(self) -> None:
            return None

    fake_mod = SimpleNamespace(
        VideoCapture=FakeCap,
    )
    monkeypatch.setattr(capture_mod, "_import_cv2", lambda: fake_mod)
    monkeypatch.setattr(capture_mod, "frame_to_b64_jpeg", lambda *a, **k: "YmFo")


def test_run_ingest_loop_enqueues_n(fake_cv2_capture: None) -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = Settings(ingest_m3u8_url="https://example/stream.m3u8")
    metrics = IngestMetrics()
    sleeps: list[float] = []

    run_ingest_loop(
        settings=settings,
        redis_client=r,
        metrics=metrics,
        sleep_fn=sleeps.append,
        stop_after_iterations=3,
    )

    assert r.llen(settings.ingest_queue_key) == 3
    assert metrics.frames_enqueued == 3
    assert metrics.frames_read_ok == 3
    # Loop breaks before the trailing sleep on the last successful enqueue.
    assert len(sleeps) == 2


def test_run_ingest_requires_url() -> None:
    with pytest.raises(ValueError, match="INGEST_M3U8_URL"):
        run_ingest_loop(
            settings=Settings(ingest_m3u8_url=None),
            redis_client=fakeredis.FakeRedis(decode_responses=True),
            metrics=IngestMetrics(),
            sleep_fn=lambda _: None,
            stop_after_iterations=1,
        )


def test_run_ingest_loop_uses_runtime_interval_override(fake_cv2_capture: None) -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = Settings(
        ingest_m3u8_url="https://example/stream.m3u8",
        ingest_sample_interval_seconds=7.5,
    )
    if settings.ingest_sample_interval_override_key:
        r.set(settings.ingest_sample_interval_override_key, "1.25")
    metrics = IngestMetrics()
    sleeps: list[float] = []

    run_ingest_loop(
        settings=settings,
        redis_client=r,
        metrics=metrics,
        sleep_fn=sleeps.append,
        stop_after_iterations=3,
    )

    assert sleeps == [1.25, 1.25]


def test_run_ingest_uses_override_on_jpeg_encode_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from city_pulse.ingest import capture as capture_mod

    class FakeCap:
        def __init__(self, url: str) -> None:
            self._url = url

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, object]:
            return True, object()

        def release(self) -> None:
            return None

    fake_mod = SimpleNamespace(VideoCapture=FakeCap)
    monkeypatch.setattr(capture_mod, "_import_cv2", lambda: fake_mod)
    monkeypatch.setattr(capture_mod, "frame_to_b64_jpeg", lambda *a, **k: None)

    r = fakeredis.FakeRedis(decode_responses=True)
    settings = Settings(
        ingest_m3u8_url="https://example/stream.m3u8",
        ingest_sample_interval_seconds=7.5,
    )
    if settings.ingest_sample_interval_override_key:
        r.set(settings.ingest_sample_interval_override_key, "2.0")
    metrics = IngestMetrics()
    sleeps: list[float] = []

    def _sleep_recorder(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise RuntimeError("stop")

    with pytest.raises(RuntimeError, match="stop"):
        run_ingest_loop(
            settings=settings,
            redis_client=r,
            metrics=metrics,
            sleep_fn=_sleep_recorder,
            stop_after_iterations=None,
        )

    assert sleeps == [2.0, 2.0]
