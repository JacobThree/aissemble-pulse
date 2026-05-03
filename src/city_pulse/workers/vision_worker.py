"""Consume frame JSON from Redis, infer via MLServer, insert vehicle counts."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from json import dumps
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
    annotate_frame_b64,
    count_vehicle_detections,
    count_vehicle_detections_advanced,
    infer_url_for,
    infer_vehicle_count,
    parse_bboxes,
    parse_norm_roi,
    vehicle_label_allowlist,
)

logger = logging.getLogger(__name__)


def _normalize_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _frame_dims_from_b64(frame_b64: str) -> tuple[int, int] | None:
    """Decode JPEG to get width/height for ROI center filtering."""
    try:
        import cv2
        import numpy as np

        raw = base64.b64decode(frame_b64)
        buf = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        h, w = frame.shape[:2]
        return (w, h)
    except Exception:
        return None


def process_next(
    *,
    settings: Settings,
    redis_client: redis.Redis,
    http_client: httpx.Client,
    pool: ConnectionPool,
    dedup_state: (
        dict[str, list[tuple[str, tuple[float, float, float, float], datetime]]] | None
    ) = None,
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
    roi_norm = parse_norm_roi(settings.vision_roi_norm)
    local_dedup_state = dedup_state if dedup_state is not None else {}

    try:
        out = infer_vehicle_count(
            http_client,
            infer_url=infer_url,
            frame_b64=payload.frame_b64,
        )
        boxes = parse_bboxes(out["body"])
        if (
            boxes
            and settings.vision_dedup_enabled
            and (roi_norm is not None or settings.vision_dedup_enabled)
        ):
            dims = _frame_dims_from_b64(payload.frame_b64)
            frame_w, frame_h = dims if dims is not None else (None, None)
            count, recent = count_vehicle_detections_advanced(
                labels=out["labels"],
                scores=out["scores"],
                bboxes=boxes,
                allowed=allowed,
                min_confidence=settings.vision_min_confidence,
                frame_width=frame_w,
                frame_height=frame_h,
                roi_norm=roi_norm,
                dedup_recent=local_dedup_state.get(payload.camera_key, []),
                dedup_iou_threshold=settings.vision_dedup_iou_threshold,
                dedup_ttl_seconds=settings.vision_dedup_ttl_seconds,
                now_utc=cap,
            )
            local_dedup_state[payload.camera_key] = recent
        elif boxes and roi_norm is not None:
            dims = _frame_dims_from_b64(payload.frame_b64)
            frame_w, frame_h = dims if dims is not None else (None, None)
            count, _ = count_vehicle_detections_advanced(
                labels=out["labels"],
                scores=out["scores"],
                bboxes=boxes,
                allowed=allowed,
                min_confidence=settings.vision_min_confidence,
                frame_width=frame_w,
                frame_height=frame_h,
                roi_norm=roi_norm,
                dedup_recent=[],
                dedup_ttl_seconds=0.0,
                now_utc=cap,
            )
        else:
            count = count_vehicle_detections(
                out["labels"],
                out["scores"],
                allowed=allowed,
                min_confidence=settings.vision_min_confidence,
            )
        if settings.vision_debug_overlay_enabled:
            try:
                overlay_b64 = annotate_frame_b64(
                    frame_b64=payload.frame_b64,
                    labels=out["labels"],
                    scores=out["scores"],
                    bboxes=boxes,
                    min_confidence=settings.vision_min_confidence,
                    allowed=allowed,
                    roi_norm=roi_norm,
                )
                if overlay_b64:
                    redis_client.set(
                        settings.vision_debug_overlay_key,
                        dumps(
                            {
                                "camera_key": payload.camera_key,
                                "captured_at": cap.isoformat(),
                                "latency_ms": float(out["latency_ms"]),
                                "vehicle_count": count,
                                "annotated_jpeg_b64": overlay_b64,
                            }
                        ),
                        ex=settings.vision_debug_overlay_ttl_seconds,
                    )
            except Exception:
                logger.exception("overlay_write_failed camera=%s", payload.camera_key)
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
    dedup_state: dict[
        str, list[tuple[str, tuple[float, float, float, float], datetime]]
    ] = {}
    try:
        while True:
            process_next(
                settings=settings,
                redis_client=redis_client,
                http_client=http_client,
                pool=pool,
                dedup_state=dedup_state,
            )
    finally:
        http_client.close()
        pool.close()
        redis_client.close()
