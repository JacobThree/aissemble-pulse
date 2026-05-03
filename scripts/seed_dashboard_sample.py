#!/usr/bin/env python3
"""Insert sample `vehicle_counts` + one `daily_briefs` row for dashboard dev.

Requires write access: **DATABASE_URL** (default user `city_pulse`, not the read-only role).

```bash
rtk bash -lc 'source .venv/bin/activate && set -a && source .env && set +a && python scripts/seed_dashboard_sample.py'
```
"""

from __future__ import annotations

import os
import random
import sys
from datetime import UTC, date, datetime, timedelta

import psycopg


def _dsn() -> str:
    u = os.environ.get("DATABASE_URL")
    if not u:
        print("DATABASE_URL is required", file=sys.stderr)
        raise SystemExit(1)
    return u


def main() -> None:
    random.seed(42)
    dsn = _dsn()
    cams = ("i695-demo-nb", "i695-demo-sb")
    # Last 7 UTC days, one aggregate row per camera per hour
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)

    rows: list[tuple[datetime, str, int]] = []
    t = start
    while t < end:
        for cam in cams:
            n = int(random.uniform(2, 40) + 5 * (1 if 7 <= t.hour < 20 else 0))
            rows.append((t, cam, n))
        t += timedelta(hours=1)

    report = date.today() - timedelta(days=1)
    body = (
        f"Sample brief (seeded) for {report}: morning peaks on {cams[0]}; "
        f"afternoon activity on {cams[1]}. See hourly chart in the dashboard."
    )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO vehicle_counts (time, camera_location, vehicle_count)
                VALUES (%s, %s, %s)
                """,
                rows,
            )
            cur.execute(
                """
                INSERT INTO daily_briefs (day, body, generated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (day) DO UPDATE SET
                    body = EXCLUDED.body,
                    generated_at = now()
                """,
                (report, body),
            )
        conn.commit()
    n = len(rows)
    print(f"Inserted {n} vehicle_counts rows; upserted daily_briefs for {report}.")


if __name__ == "__main__":
    main()
