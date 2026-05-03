"""Shared psycopg connection pool."""

from __future__ import annotations

from psycopg_pool import ConnectionPool


def create_pool(database_url: str, *, max_size: int = 4) -> ConnectionPool:
    """Small sync pool for worker processes (autocommit per statement)."""
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True},
        open=True,
    )
