"""Pure aggregation for daily traffic briefs (unit-tested)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median


@dataclass(frozen=True)
class CameraDayStats:
    """Per-camera stats for one UTC calendar day window."""

    camera_location: str
    total_vehicles: int
    hourly_counts: tuple[int, ...]
    top_hours: tuple[tuple[int, int], ...]
    peak_hour: int
    median_hourly: float


def _hourly_vector(rows: Sequence[tuple[str, int, int]]) -> dict[str, list[int]]:
    """Build 24-length hourly totals per camera from sparse (camera, hour, total)."""
    buckets: dict[str, list[int]] = defaultdict(lambda: [0] * 24)
    for camera, hour, total in rows:
        if 0 <= hour < 24:
            buckets[camera][hour] += total
    return dict(buckets)


def aggregate_cameras(
    hourly_rows: Sequence[tuple[str, int, int]],
) -> dict[str, CameraDayStats]:
    """Compute per-camera stats from sparse hourly sums.

    ``hourly_rows`` items are ``(camera_location, hour_utc_0_23, vehicle_total)``.
    """
    vec = _hourly_vector(hourly_rows)
    out: dict[str, CameraDayStats] = {}
    for camera, hourly in vec.items():
        total = sum(hourly)
        med = float(median(hourly)) if hourly else 0.0
        # Peak: max count, tie-break lower hour
        peak_hour = max(range(24), key=lambda h: (hourly[h], -h))
        pairs = [(h, hourly[h]) for h in range(24)]
        pairs.sort(key=lambda p: (-p[1], p[0]))
        top = tuple(pairs[:3])
        out[camera] = CameraDayStats(
            camera_location=camera,
            total_vehicles=total,
            hourly_counts=tuple(hourly),
            top_hours=top,
            peak_hour=peak_hour,
            median_hourly=med,
        )
    return out


def build_brief_draft(
    report_day: date,
    by_camera: dict[str, CameraDayStats],
) -> str:
    """Long-form Markdown capsule for Sumy input."""
    lines = [
        f"# City Pulse traffic draft — {report_day.isoformat()} (UTC)",
        "",
        "Per-camera vehicle detections (hourly buckets, UTC):",
        "",
    ]
    for cam in sorted(by_camera.keys()):
        s = by_camera[cam]
        h1, c1 = s.top_hours[0]
        h2, c2 = s.top_hours[1]
        h3, c3 = s.top_hours[2]
        lines.append(f"## {cam}")
        lines.append(f"- Total vehicles (sum of hourly counts): {s.total_vehicles}")
        lines.append(
            f"- Top hours: {h1:02d}:00 ({c1}), {h2:02d}:00 ({c2}), {h3:02d}:00 ({c3})"
        )
        lines.append(
            f"- Peak hour {s.peak_hour:02d}:00 vs median hourly count: "
            f"{s.hourly_counts[s.peak_hour]} vs {s.median_hourly:.1f}"
        )
        lines.append("")
    return "\n".join(lines).strip() + "\n"
