"""Pure date-window helpers for the dashboard."""

from datetime import UTC, date, datetime, timedelta

import pytest

from city_pulse.dashboard.data import utc_window


def test_utc_window_inclusive_end() -> None:
    start, end_excl = utc_window(date(2026, 5, 1), date(2026, 5, 3))
    assert start == datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
    assert end_excl == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    assert end_excl - start == timedelta(days=3)


def test_utc_window_single_day() -> None:
    lo, hi = utc_window(date(2026, 1, 2), date(2026, 1, 2))
    assert hi - lo == timedelta(days=1)


def test_utc_window_invalid() -> None:
    with pytest.raises(ValueError, match="end_inclusive"):
        utc_window(date(2026, 2, 2), date(2026, 2, 1))
