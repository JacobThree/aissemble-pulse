"""Push serialized frames to a capped Redis list."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from redis import Redis
from redis.exceptions import RedisError

from city_pulse.ingest.metrics import IngestMetrics
from city_pulse.ingest.models import FramePayload


def push_frame(
    client: Redis,
    *,
    queue_key: str,
    payload: FramePayload,
    max_length: int,
    metrics: IngestMetrics,
    heartbeat_key: str | None = None,
) -> None:
    """LPUSH JSON + LTRIM so list keeps at most ``max_length`` newest items.

    When the queue is already full, one oldest element is dropped — counted in
    ``metrics.queue_overflow_evictions``.
    """
    if max_length < 1:
        raise ValueError("max_length must be >= 1")

    raw = payload.model_dump_json()
    try:
        length_before = cast(int, client.llen(queue_key))
        if length_before >= max_length:
            metrics.queue_overflow_evictions += 1
        pipe = client.pipeline()
        pipe.lpush(queue_key, raw)
        pipe.ltrim(queue_key, 0, max_length - 1)
        pipe.execute()
    except RedisError:
        metrics.frames_drop_enqueue_fail += 1
        raise

    metrics.frames_enqueued += 1
    if heartbeat_key:
        client.set(
            heartbeat_key,
            datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
