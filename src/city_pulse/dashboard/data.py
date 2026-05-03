"""Read-only Timescale + Redis helpers for the Streamlit dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import psycopg
import redis
from psycopg import Connection


def connect_readonly(dsn: str) -> Connection:
    """Session timezone UTC for consistent hour buckets."""
    return psycopg.connect(
        dsn,
        connect_timeout=15,
        options="-c timezone=UTC",
    )


def utc_window(start: date, end_inclusive: date) -> tuple[datetime, datetime]:
    """Return ``[start 00:00 UTC, day_after_end 00:00 UTC)`` for filtering."""
    if end_inclusive < start:
        raise ValueError("end_inclusive must be >= start")
    lo = datetime(start.year, start.month, start.day, tzinfo=UTC)
    hi = datetime(
        end_inclusive.year,
        end_inclusive.month,
        end_inclusive.day,
        tzinfo=UTC,
    ) + timedelta(days=1)
    return lo, hi


def list_cameras(conn: Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT camera_location
            FROM vehicle_counts
            ORDER BY 1
            """
        )
        return [str(r[0]) for r in cur.fetchall()]


def fetch_hourly_series(
    conn: Connection,
    *,
    cameras: list[str],
    start: date,
    end_inclusive: date,
) -> pd.DataFrame:
    """Hourly sums per camera; empty frame if ``cameras`` is empty."""
    if not cameras:
        return pd.DataFrame(columns=["bucket", "camera_location", "total"])
    lo, hi = utc_window(start, end_inclusive)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT date_trunc('hour', time) AS bucket,
                   camera_location,
                   SUM(vehicle_count)::bigint AS total
            FROM vehicle_counts
            WHERE camera_location = ANY(%s)
              AND time >= %s
              AND time < %s
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            (cameras, lo, hi),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["bucket", "camera_location", "total"])
    df = pd.DataFrame(rows, columns=["bucket", "camera_location", "total"])
    df["bucket"] = pd.to_datetime(df["bucket"], utc=True)
    df["total"] = df["total"].astype(int)
    return df


@dataclass(frozen=True)
class BriefRow:
    day: date
    body: str
    generated_at: datetime


def fetch_latest_brief(conn: Connection) -> BriefRow | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT day::text, body, generated_at
            FROM daily_briefs
            ORDER BY day DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if row is None:
        return None
    day_s, body, gen_at = row
    return BriefRow(
        day=date.fromisoformat(str(day_s)),
        body=str(body),
        generated_at=gen_at,
    )


def read_ingest_heartbeat(
    redis_client: redis.Redis,
    *,
    key: str | None,
) -> str | None:
    """Return ISO timestamp string from Redis, or None if missing/disabled."""
    if not key:
        return None
    raw = redis_client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)
