"""FramePayload serialization."""

import json
from datetime import UTC, datetime

from city_pulse.ingest.models import FramePayload


def test_frame_payload_json_roundtrip() -> None:
    ts = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)
    p = FramePayload(camera_key="i695-north", captured_at=ts, frame_b64="YWFh")
    raw = p.model_dump_json()
    data = json.loads(raw)
    assert data["camera_key"] == "i695-north"
    assert data["frame_b64"] == "YWFh"
    assert data["captured_at"] == "2026-05-02T12:00:00Z"
