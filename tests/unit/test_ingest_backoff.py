"""Tests for StreamBackoff."""

from city_pulse.ingest.backoff import StreamBackoff


def test_backoff_exponential_then_caps() -> None:
    b = StreamBackoff(initial_seconds=1.0, max_seconds=5.0, multiplier=2.0)
    assert b.record_failure() == 1.0  # 1 * 2^0
    assert b.record_failure() == 2.0  # 1 * 2^1
    assert b.record_failure() == 4.0  # 1 * 2^2
    assert b.record_failure() == 5.0  # capped at max_seconds
    assert b.record_failure() == 5.0


def test_backoff_reset_clears_streak() -> None:
    b = StreamBackoff(initial_seconds=2.0, max_seconds=100.0, multiplier=2.0)
    assert b.record_failure() == 2.0
    b.reset()
    assert b.record_failure() == 2.0
