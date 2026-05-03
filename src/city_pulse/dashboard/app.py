"""Streamlit dashboard: hourly counts + latest daily brief + ingest heartbeat."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import cast

import redis
import streamlit as st

from city_pulse.config import get_settings
from city_pulse.dashboard.data import (
    connect_readonly,
    fetch_hourly_series,
    fetch_latest_brief,
    list_cameras,
    read_ingest_heartbeat,
)


def _default_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=7), today


def main() -> None:
    st.set_page_config(page_title="City Pulse", layout="wide")
    st.title("City Pulse")
    st.caption("Read-only Timescale + Redis ops (public-feed pipeline demo).")

    settings = get_settings()

    try:
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except redis.RedisError as exc:
        st.error(f"Redis unavailable: {exc}")
        redis_client = None

    try:
        conn = connect_readonly(settings.database_readonly_url)
    except OSError as exc:
        st.error(f"Database unavailable: {exc}")
        st.stop()

    with conn:
        cameras_all = list_cameras(conn)
        brief = fetch_latest_brief(conn)

    conn.close()

    with st.sidebar:
        st.header("Filters")
        if not cameras_all:
            st.warning("No cameras in `vehicle_counts`. Seed sample data (README).")
            picked: list[str] = []
        else:
            picked = st.multiselect(
                "Cameras",
                options=cameras_all,
                default=cameras_all,
            )
        raw = st.date_input(
            "Date range (UTC)",
            value=_default_range(),
        )
        if isinstance(raw, tuple):
            pair = cast(tuple[date, date], raw)
            start_d, end_d = pair
        else:
            start_d = cast(date, raw)
            end_d = start_d

    col_chart, col_brief = st.columns((3, 2))

    with col_chart:
        st.subheader("Hourly vehicle counts")
        if not picked:
            st.info("Select at least one camera.")
        else:
            conn2 = connect_readonly(settings.database_readonly_url)
            try:
                df = fetch_hourly_series(
                    conn2,
                    cameras=picked,
                    start=start_d,
                    end_inclusive=end_d,
                )
            finally:
                conn2.close()

            if df.empty:
                st.warning("No rows in range.")
            else:
                pivot = df.pivot_table(
                    index="bucket",
                    columns="camera_location",
                    values="total",
                    aggfunc="sum",
                ).fillna(0)
                pivot.sort_index(inplace=True)
                st.line_chart(pivot)

    with col_brief:
        st.subheader("Latest daily brief")
        if brief is None:
            st.info("No rows in `daily_briefs`. Run `city-pulse-daily-brief` or seed.")
        else:
            st.metric("Day (UTC)", str(brief.day))
            st.caption(f"Generated {brief.generated_at.isoformat()}")
            # DB-stored brief: plain text avoids Markdown/HTML injection if misused.
            st.text(brief.body)

    with st.expander("Ops"):
        st.text(f"Queue key: {settings.ingest_queue_key}")
        qdepth = None
        err_q = None
        if redis_client is not None:
            try:
                qdepth = int(cast(int, redis_client.llen(settings.ingest_queue_key)))
            except redis.RedisError as exc:
                err_q = str(exc)
        if err_q:
            st.warning(f"Redis queue depth: error ({err_q})")
        elif qdepth is not None:
            st.text(f"Queue depth (frames): {qdepth}")

        hb = None
        err_hb = None
        if redis_client is None:
            st.text("Last ingest success: Redis unavailable")
        elif not settings.ingest_heartbeat_key:
            st.text("Last ingest success: (heartbeat disabled)")
        else:
            try:
                hb = read_ingest_heartbeat(
                    redis_client,
                    key=settings.ingest_heartbeat_key,
                )
            except redis.RedisError as exc:
                err_hb = str(exc)
            if err_hb:
                st.warning(f"Last ingest success: error ({err_hb})")
            elif hb:
                st.text(f"Last ingest success (UTC): {hb}")
            else:
                st.text("Last ingest success: no key yet (start ingest)")

    if redis_client is not None:
        try:
            redis_client.close()
        except redis.RedisError:
            pass


if __name__ == "__main__":
    main()
