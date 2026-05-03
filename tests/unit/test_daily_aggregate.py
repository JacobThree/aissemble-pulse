"""Aggregation math for daily brief draft (frozen fixtures)."""

from datetime import date

from city_pulse.nlp_jobs.daily_aggregate import (
    aggregate_cameras,
    build_brief_draft,
)


def test_aggregate_two_cameras_peak_and_top_hours() -> None:
    """Sparse hourly rows roll into 24-bin vectors with correct peak/top."""
    rows = [
        ("towson-nb", 7, 11),
        ("towson-nb", 8, 45),
        ("towson-nb", 9, 99),
        ("towson-nb", 17, 33),
        ("i695-w", 7, 5),
        ("i695-w", 9, 40),
        ("i695-w", 10, 38),
    ]
    stats = aggregate_cameras(rows)
    assert set(stats.keys()) == {"towson-nb", "i695-w"}

    nb = stats["towson-nb"]
    assert nb.total_vehicles == 11 + 45 + 99 + 33
    assert nb.peak_hour == 9
    assert nb.top_hours[0] == (9, 99)
    assert nb.top_hours[1][0] == 8  # second busiest
    assert nb.median_hourly == 0.0  # mostly zeros in 24 bins -> median 0

    w = stats["i695-w"]
    assert w.peak_hour == 9
    assert w.total_vehicles == 5 + 40 + 38


def test_peak_hour_tie_prefers_lower_hour() -> None:
    rows = [("tie-cam", 8, 50), ("tie-cam", 9, 50)]
    s = aggregate_cameras(rows)["tie-cam"]
    assert s.peak_hour == 8


def test_build_brief_draft_contains_camera_sections() -> None:
    rows = [("alpha", 12, 10), ("beta", 12, 5)]
    stats = aggregate_cameras(rows)
    text = build_brief_draft(date(2026, 5, 1), stats)
    assert "2026-05-01" in text
    assert "## alpha" in text
    assert "## beta" in text
    assert "Total vehicles" in text


def test_aggregate_empty() -> None:
    assert aggregate_cameras([]) == {}
