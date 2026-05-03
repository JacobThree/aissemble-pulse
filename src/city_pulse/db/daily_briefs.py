"""Writes to ``daily_briefs`` (idempotent upsert)."""

from __future__ import annotations

from datetime import date

from psycopg import Connection


def upsert_daily_brief(conn: Connection, *, day: date, body: str) -> None:
    """Insert or replace brief body for ``day`` (UTC calendar date)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO daily_briefs (day, body, generated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (day) DO UPDATE SET
                body = EXCLUDED.body,
                generated_at = now()
            """,
            (day, body),
        )
