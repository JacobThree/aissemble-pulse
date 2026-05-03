"""Wire payloads for the frame queue."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer


class FramePayload(BaseModel):
    """JSON envelope pushed to Redis for downstream inference."""

    camera_key: str = Field(min_length=1)
    captured_at: datetime
    frame_b64: str = Field(min_length=1)

    @field_serializer("captured_at")
    def _serialize_ts(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")
