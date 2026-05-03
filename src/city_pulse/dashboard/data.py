"""Read-only Timescale + Redis helpers for the Streamlit dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from json import loads

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


def fetch_vehicle_series(
    conn: Connection,
    *,
    cameras: list[str],
    start: date,
    end_inclusive: date,
    bucket_interval: str,
) -> pd.DataFrame:
    """Aggregate with Timescale ``time_bucket`` (e.g. ``5 minutes``, ``1 hour``)."""
    if not cameras:
        return pd.DataFrame(columns=["bucket", "camera_location", "total"])
    lo, hi = utc_window(start, end_inclusive)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT time_bucket(%s::interval, time) AS bucket,
                   camera_location,
                   SUM(vehicle_count)::bigint AS total
            FROM vehicle_counts
            WHERE camera_location = ANY(%s)
              AND time >= %s
              AND time < %s
            GROUP BY 1, 2
            ORDER BY 1, 2
            """,
            (bucket_interval, cameras, lo, hi),
        )
        rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["bucket", "camera_location", "total"])
    df = pd.DataFrame(rows, columns=["bucket", "camera_location", "total"])
    df["bucket"] = pd.to_datetime(df["bucket"], utc=True)
    df["total"] = df["total"].astype(int)
    return df


@dataclass(frozen=True)
class LiveRollupStats:
    """Recent raw DB activity for the live strip (independent of time_bucket)."""

    latest_detection_utc: datetime | None
    total_vehicles_all_time: int
    vehicles_sum_last_window: int
    window_minutes: int


def fetch_live_rollup(
    conn: Connection,
    *,
    cameras: list[str],
    window_minutes: int = 15,
) -> LiveRollupStats:
    """How active ingest+vision were recently (raw rows, not time_bucket)."""
    if not cameras:
        return LiveRollupStats(None, 0, 0, window_minutes)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT MAX(time) AS latest,
                   COALESCE(SUM(vehicle_count), 0)::bigint AS n_total,
                   COALESCE(SUM(vehicle_count), 0)::bigint AS n_vehicles
            FROM vehicle_counts
            WHERE camera_location = ANY(%s)
            """,
            (cameras,),
        )
        total_row = cur.fetchone()
        cur.execute(
            """
            SELECT COALESCE(SUM(vehicle_count), 0)::bigint AS n_vehicles_recent
            FROM vehicle_counts
            WHERE camera_location = ANY(%s)
              AND time >= NOW() - (%s::integer * INTERVAL '1 minute')
            """,
            (cameras, window_minutes),
        )
        recent_row = cur.fetchone()
    if total_row is None or total_row[0] is None:
        return LiveRollupStats(None, 0, 0, window_minutes)
    latest, n_total, _ = total_row
    n_veh_recent = 0 if recent_row is None else int(recent_row[0])
    if isinstance(latest, datetime):
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=UTC)
        else:
            latest = latest.astimezone(UTC)
    else:
        latest = None
    return LiveRollupStats(latest, int(n_total), n_veh_recent, window_minutes)


def fetch_hourly_series(
    conn: Connection,
    *,
    cameras: list[str],
    start: date,
    end_inclusive: date,
) -> pd.DataFrame:
    """Hourly sums per camera (compat wrapper)."""
    return fetch_vehicle_series(
        conn,
        cameras=cameras,
        start=start,
        end_inclusive=end_inclusive,
        bucket_interval="1 hour",
    )


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


def read_ingest_sample_override(
    redis_client: redis.Redis,
    *,
    key: str | None,
) -> float | None:
    """Return runtime ingest sample interval override from Redis, if set."""
    if not key:
        return None
    raw = redis_client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        val = float(str(raw))
    except ValueError:
        return None
    if val <= 0:
        return None
    return val


def write_ingest_sample_override(
    redis_client: redis.Redis,
    *,
    key: str | None,
    seconds: float,
) -> bool:
    """Set runtime ingest sample override. Returns False if key is disabled."""
    if not key:
        return False
    redis_client.set(key, f"{seconds:.3f}")
    return True


@dataclass(frozen=True)
class OverlayRow:
    camera_key: str
    captured_at: str
    latency_ms: float
    vehicle_count: int
    annotated_jpeg_b64: str


def read_latest_overlay(
    redis_client: redis.Redis,
    *,
    key: str,
) -> OverlayRow | None:
    """Read latest vision overlay payload from Redis JSON blob."""
    raw = redis_client.get(key)
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        obj = loads(str(raw))
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return OverlayRow(
            camera_key=str(obj["camera_key"]),
            captured_at=str(obj["captured_at"]),
            latency_ms=float(obj["latency_ms"]),
            vehicle_count=int(obj["vehicle_count"]),
            annotated_jpeg_b64=str(obj["annotated_jpeg_b64"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
