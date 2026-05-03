"""Redis queue caps and metrics."""

from datetime import UTC, datetime

import fakeredis
import pytest

from city_pulse.ingest.metrics import IngestMetrics
from city_pulse.ingest.models import FramePayload
from city_pulse.ingest.redis_queue import push_frame


@pytest.fixture
def redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _payload() -> FramePayload:
    return FramePayload(
        camera_key="test",
        captured_at=datetime.now(UTC),
        frame_b64="Zm9v",
    )


def test_push_increments_length(redis_client: fakeredis.FakeRedis) -> None:
    m = IngestMetrics()
    push_frame(
        redis_client,
        queue_key="q",
        payload=_payload(),
        max_length=10,
        metrics=m,
    )
    assert int(redis_client.llen("q")) == 1
    assert m.frames_enqueued == 1
    assert m.queue_overflow_evictions == 0


def test_push_trims_and_counts_overflow(redis_client: fakeredis.FakeRedis) -> None:
    m = IngestMetrics()
    key = "q2"
    redis_client.lpush(key, "old")
    redis_client.lpush(key, "older")
    assert redis_client.llen(key) == 2

    push_frame(
        redis_client,
        queue_key=key,
        payload=_payload(),
        max_length=2,
        metrics=m,
    )
    assert redis_client.llen(key) == 2
    assert m.queue_overflow_evictions == 1


def test_push_invalid_max_length() -> None:
    with pytest.raises(ValueError, match="max_length"):
        push_frame(
            fakeredis.FakeRedis(decode_responses=True),
            queue_key="q",
            payload=_payload(),
            max_length=0,
            metrics=IngestMetrics(),
        )
