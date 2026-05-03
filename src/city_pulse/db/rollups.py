"""Read-side rollups for NLP jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg import Connection


@dataclass(frozen=True)
class HourlyVehicleSum:
    """One camera’s vehicle sum for a single UTC hour within the query window."""

    camera_location: str
    hour_utc: int
    total: int


def fetch_hourly_vehicle_sums(
    conn: Connection,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[HourlyVehicleSum]:
    """Sparse hourly sums (0–23 UTC) per camera for ``[window_start, window_end)``."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT camera_location,
                   (EXTRACT(HOUR FROM time AT TIME ZONE 'UTC'))::int AS hr,
                   SUM(vehicle_count)::bigint AS total
            FROM vehicle_counts
            WHERE time >= %s AND time < %s
            GROUP BY camera_location, hr
            ORDER BY camera_location, hr
            """,
            (window_start, window_end),
        )
        rows = cur.fetchall()
    out: list[HourlyVehicleSum] = []
    for cam, hr, total in rows:
        h = int(hr)
        if not 0 <= h < 24:
            continue
        out.append(
            HourlyVehicleSum(
                camera_location=str(cam),
                hour_utc=h,
                total=int(total),
            )
        )
    return out
