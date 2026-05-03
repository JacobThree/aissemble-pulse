#!/usr/bin/env python3
"""Verify Redis, Timescale, and YOLO before starting ingest + vision + Streamlit."""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _check_redis(url: str) -> None:
    import redis as redis_lib

    r = redis_lib.Redis.from_url(url, socket_connect_timeout=5)
    try:
        r.ping()
    finally:
        r.close()


def _check_pg(url: str) -> None:
    import psycopg

    with psycopg.connect(url, connect_timeout=10) as conn:
        conn.execute("SELECT 1")


def _check_yolo_ready(
    base: str, *, wait_s: float = 240.0, interval_s: float = 5.0
) -> bool:
    root = base.rstrip("/")
    url = f"{root}/v2/health/ready"
    deadline = time.monotonic() + wait_s
    last_err: str | None = None
    print(
        "  [Errno 61] connection refused is normal until MLServer binds :8080 "
        "(yolo container still starting, or not running).",
        flush=True,
    )
    print(
        "  If this never clears: rtk docker compose ps && "
        "rtk docker compose logs -f yolo",
        flush=True,
    )
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status == 200:
                    print(
                        f"YOLO MLServer is ready ({base}). "
                        "First boot can take several minutes while weights load.",
                        flush=True,
                    )
                    return True
        except KeyboardInterrupt:
            print("\nStopped waiting for YOLO (Ctrl+C).", file=sys.stderr, flush=True)
            raise SystemExit(130) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = str(exc)
        print(
            f"Waiting for YOLO at {url} … ({last_err or 'not ready yet'})",
            flush=True,
        )
        try:
            time.sleep(interval_s)
        except KeyboardInterrupt:
            print("\nStopped waiting for YOLO (Ctrl+C).", file=sys.stderr, flush=True)
            raise SystemExit(130) from None
    print(
        "\nGive up: YOLO never became ready. Try:\n"
        "  rtk docker compose up -d yolo\n"
        "  rtk docker compose logs -f yolo\n"
        f"Last error: {last_err}",
        file=sys.stderr,
        flush=True,
    )
    return False


def _print_db_hint(database_url: str, camera_key: str) -> None:
    import psycopg

    try:
        with psycopg.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT camera_location, COUNT(*) AS n,
                           MAX(time) AS last_ts
                    FROM vehicle_counts
                    GROUP BY 1
                    ORDER BY 1
                    """
                )
                rows = cur.fetchall()
        if not rows:
            print(
                "\nNo rows in vehicle_counts yet — normal until "
                "ingest + vision run successfully.",
                flush=True,
            )
            return
        print("\nvehicle_counts summary:", flush=True)
        for loc, n, last_ts in rows:
            mark = " ← INGEST_CAMERA_KEY" if loc == camera_key else ""
            print(f"  {loc}: {n} rows, last {last_ts}{mark}", flush=True)
        if camera_key and not any(r[0] == camera_key for r in rows):
            print(
                f"\nNo data for INGEST_CAMERA_KEY={camera_key!r} yet — "
                "chart stays empty for that camera until vision inserts rows.",
                flush=True,
            )
    except Exception as exc:
        print(f"(Could not summarize DB: {exc})", flush=True)


def main() -> int:
    _load_dotenv()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://city_pulse:city_pulse@localhost:5433/city_pulse",
    )
    yolo_base = os.environ.get("YOLO_ENDPOINT", "http://localhost:8080")
    camera_key = os.environ.get("INGEST_CAMERA_KEY", "")

    print("Preflight: Redis …", flush=True)
    try:
        _check_redis(redis_url)
        print("  OK", flush=True)
    except Exception as exc:
        print(f"\nRedis failed ({redis_url}): {exc}", file=sys.stderr)
        print("Run: rtk docker compose up -d redis", file=sys.stderr)
        return 1

    print("Preflight: Timescale …", flush=True)
    try:
        _check_pg(database_url)
        print("  OK", flush=True)
    except Exception as exc:
        print(f"\nPostgres failed ({database_url}): {exc}", file=sys.stderr)
        print("Run: rtk docker compose up -d timescaledb", file=sys.stderr)
        return 1

    print(
        "Preflight: YOLO MLServer (may wait up to ~4 min on cold start) …",
        flush=True,
    )
    if not _check_yolo_ready(yolo_base):
        return 2

    _print_db_hint(database_url, camera_key)
    print("Preflight passed.\n", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("", file=sys.stderr)  # newline after ^C if outside wait loop
        raise SystemExit(130) from None
