"""Simple counters for ingest observability."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IngestMetrics:
    frames_read_ok: int = 0
    frames_drop_read_fail: int = 0
    frames_enqueued: int = 0
    frames_drop_enqueue_fail: int = 0
    queue_overflow_evictions: int = 0
    backoff_wait_seconds_total: float = field(default=0.0, repr=False)
