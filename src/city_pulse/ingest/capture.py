"""Grab JPEG frames from an HLS URL and enqueue base64 payloads."""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError

from city_pulse.config.settings import Settings
from city_pulse.ingest.backoff import StreamBackoff
from city_pulse.ingest.metrics import IngestMetrics
from city_pulse.ingest.models import FramePayload
from city_pulse.ingest.redis_queue import push_frame

logger = logging.getLogger(__name__)


def _import_cv2() -> Any:
    import cv2

    return cv2


def frame_to_b64_jpeg(frame: Any, *, jpeg_quality: int = 85) -> str | None:
    """Encode BGR ndarray to base64 JPEG; returns None if encode fails."""
    cv2 = _import_cv2()
    ok, buf = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
    )
    if not ok or buf is None:
        return None
    return base64.standard_b64encode(buf.tobytes()).decode("ascii")


def run_ingest_loop(
    *,
    settings: Settings,
    redis_client: Any,
    metrics: IngestMetrics,
    sleep_fn: Callable[[float], None] = time.sleep,
    stop_after_iterations: int | None = None,
) -> None:
    """Blocking loop: sleeps ``ingest_sample_interval_seconds`` between captures.

    ``stop_after_iterations``: stop after N successful Redis enqueues (tests).
    """
    url = settings.ingest_m3u8_url
    if not url:
        raise ValueError("INGEST_M3U8_URL / ingest_m3u8_url must be set")

    cv2 = _import_cv2()
    backoff = StreamBackoff(
        initial_seconds=settings.ingest_backoff_initial_seconds,
        max_seconds=settings.ingest_backoff_max_seconds,
        multiplier=settings.ingest_backoff_multiplier,
    )
    iterations = 0

    cap = cv2.VideoCapture(url)
    try:
        while True:
            if not cap.isOpened():
                wait = backoff.record_failure()
                metrics.frames_drop_read_fail += 1
                metrics.backoff_wait_seconds_total += wait
                logger.warning("VideoCapture not open; backoff %.2fs", wait)
                sleep_fn(wait)
                cap.open(url)
                continue

            ok, frame = cap.read()
            if not ok or frame is None:
                wait = backoff.record_failure()
                metrics.frames_drop_read_fail += 1
                metrics.backoff_wait_seconds_total += wait
                logger.warning("Frame read failed; backoff %.2fs", wait)
                sleep_fn(wait)
                continue

            backoff.reset()
            metrics.frames_read_ok += 1

            b64 = frame_to_b64_jpeg(frame, jpeg_quality=settings.ingest_jpeg_quality)
            if b64 is None:
                metrics.frames_drop_read_fail += 1
                logger.warning("JPEG encode failed; skipping frame")
                sleep_fn(settings.ingest_sample_interval_seconds)
                continue

            payload = FramePayload(
                camera_key=settings.ingest_camera_key,
                captured_at=datetime.now(UTC),
                frame_b64=b64,
            )
            enqueued = False
            try:
                push_frame(
                    redis_client,
                    queue_key=settings.ingest_queue_key,
                    payload=payload,
                    max_length=settings.ingest_max_queue_length,
                    metrics=metrics,
                )
                enqueued = True
            except RedisError as exc:
                logger.exception("Redis enqueue failed: %s", exc)

            if enqueued:
                iterations += 1
                limit = stop_after_iterations
                if limit is not None and iterations >= limit:
                    break

            sleep_fn(settings.ingest_sample_interval_seconds)
    finally:
        cap.release()
