"""Aggregate counts, summarize with Sumy MLServer, upsert ``daily_briefs``."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from city_pulse.config.settings import Settings
from city_pulse.db.daily_briefs import upsert_daily_brief
from city_pulse.db.pool import create_pool
from city_pulse.db.rollups import fetch_hourly_vehicle_sums
from city_pulse.nlp_jobs.daily_aggregate import (
    aggregate_cameras,
    build_brief_draft,
)

logger = logging.getLogger(__name__)


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Inclusive-exclusive window ``[day 00:00 UTC, next day 00:00 UTC)``."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


def sumy_infer_url(base: str, model_name: str) -> str:
    root = base.rstrip("/")
    return f"{root}/v2/models/{model_name}/infer"


def parse_sumy_summary(body: dict[str, Any]) -> str:
    for out in body.get("outputs", []):
        if out.get("name") != "summary":
            continue
        data = out.get("data")
        if not isinstance(data, list) or not data:
            continue
        raw = data[0]
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)
    raise ValueError("Sumy infer response missing outputs[].name==summary data")


def summarize_with_sumy(
    client: httpx.Client,
    *,
    infer_url: str,
    text: str,
) -> str:
    payload = {
        "inputs": [
            {
                "name": "text",
                "shape": [1],
                "datatype": "BYTES",
                "data": [text],
            }
        ]
    }
    resp = client.post(infer_url, json=payload)
    resp.raise_for_status()
    return parse_sumy_summary(resp.json())


def run_daily_brief_for_day(settings: Settings, *, report_day: date) -> str:
    """Fetch hourly sums, build draft, call Sumy, upsert row. Returns stored body."""
    start, end = utc_day_bounds(report_day)
    pool = create_pool(
        settings.database_url,
        max_size=settings.daily_brief_db_pool_max,
    )
    timeout = httpx.Timeout(settings.sumy_http_timeout_seconds)
    http_client = httpx.Client(timeout=timeout)
    infer_url = sumy_infer_url(settings.sumy_endpoint, settings.sumy_model_name)
    try:
        with pool.connection() as conn:
            hourly = fetch_hourly_vehicle_sums(conn, window_start=start, window_end=end)
        rows = [(h.camera_location, h.hour_utc, h.total) for h in hourly]
        by_camera = aggregate_cameras(rows)

        if not by_camera:
            body = (
                f"No vehicle count rows for {report_day.isoformat()} (UTC). "
                "Brief stored without Sumy summarization."
            )
            logger.warning("daily_brief_empty_window day=%s", report_day)
            with pool.connection() as conn:
                upsert_daily_brief(conn, day=report_day, body=body)
            return body

        draft = build_brief_draft(report_day, by_camera)
        try:
            summary = summarize_with_sumy(http_client, infer_url=infer_url, text=draft)
        except httpx.HTTPError:
            logger.exception("sumy_infer_failed day=%s", report_day)
            summary = f"[Sumy unavailable] Fallback draft:\n\n{draft}"
        except ValueError:
            logger.exception("sumy_parse_failed day=%s", report_day)
            summary = f"[Sumy parse error] Fallback draft:\n\n{draft}"

        with pool.connection() as conn:
            upsert_daily_brief(conn, day=report_day, body=summary)

        logger.info(
            "daily_brief_upsert day=%s cameras=%d chars=%d",
            report_day,
            len(by_camera),
            len(summary),
        )
        return summary
    finally:
        http_client.close()
        pool.close()
