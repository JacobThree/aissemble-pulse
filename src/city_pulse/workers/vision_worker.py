"""Consume frame JSON from Redis, infer via MLServer, insert vehicle counts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

import httpx
import redis
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from city_pulse.config.settings import Settings
from city_pulse.db.pool import create_pool
from city_pulse.db.vehicle_counts import insert_vehicle_count
from city_pulse.ingest.models import FramePayload
from city_pulse.workers.inference import (
    count_vehicle_detections,
    infer_url_for,
    infer_vehicle_count,
    vehicle_label_allowlist,
)

logger = logging.getLogger(__name__)


def _normalize_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def process_next(
    *,
    settings: Settings,
    redis_client: redis.Redis,
    http_client: httpx.Client,
    pool: ConnectionPool,
) -> bool:
    """Blocking pop one frame, infer, insert. Returns ``False`` on idle timeout."""
    item = redis_client.brpop(
        settings.ingest_queue_key,
        timeout=settings.vision_brpop_timeout_seconds,
    )
    if item is None:
        return False
    _, raw = cast(tuple[str, str], item)
    try:
        payload = FramePayload.model_validate_json(raw)
    except ValidationError:
        logger.exception("invalid_frame_json")
        return True

    cap = _normalize_ts(payload.captured_at)
    redis_lag_ms = (datetime.now(UTC) - cap).total_seconds() * 1000.0

    infer_url = infer_url_for(settings.yolo_endpoint, settings.vision_model_name)
    allowed = vehicle_label_allowlist(settings.vision_vehicle_labels)

    try:
        out = infer_vehicle_count(
            http_client,
            infer_url=infer_url,
            frame_b64=payload.frame_b64,
        )
        count = count_vehicle_detections(
            out["labels"],
            out["scores"],
            allowed=allowed,
            min_confidence=settings.vision_min_confidence,
        )
        with pool.connection() as conn:
            insert_vehicle_count(
                conn,
                captured_at=cap,
                camera_location=payload.camera_key,
                vehicle_count=count,
            )
        logger.info(
            "vision_inference camera=%s count=%d latency_ms=%.1f redis_lag_ms=%.1f",
            payload.camera_key,
            count,
            float(out["latency_ms"]),
            redis_lag_ms,
        )
    except httpx.HTTPError:
        logger.exception("infer_http_failed camera=%s", payload.camera_key)
    except Exception:
        logger.exception("vision_frame_failed camera=%s", payload.camera_key)

    return True


def run_forever(settings: Settings) -> None:
    """Long-running worker loop."""
    pool = create_pool(
        settings.database_url,
        max_size=settings.vision_db_pool_max,
    )
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    timeout = httpx.Timeout(settings.vision_http_timeout_seconds)
    http_client = httpx.Client(timeout=timeout)
    try:
        while True:
            process_next(
                settings=settings,
                redis_client=redis_client,
                http_client=http_client,
                pool=pool,
            )
    finally:
        http_client.close()
        pool.close()
        redis_client.close()
