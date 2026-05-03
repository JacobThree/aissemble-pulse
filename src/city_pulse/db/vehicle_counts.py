"""Writes to ``vehicle_counts`` hypertable."""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection


def insert_vehicle_count(
    conn: Connection,
    *,
    captured_at: datetime,
    camera_location: str,
    vehicle_count: int,
) -> None:
    """Insert one observation row."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO vehicle_counts (time, camera_location, vehicle_count)
            VALUES (%s, %s, %s)
            """,
            (captured_at, camera_location, vehicle_count),
        )
