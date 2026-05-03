"""Streamlit dashboard: live HLS, auto-refresh counts chart, brief, ops."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import cast

import pandas as pd
import redis
import streamlit as st
import streamlit.components.v1 as components

from city_pulse.config import get_settings
from city_pulse.config.settings import Settings
from city_pulse.dashboard.data import (
    connect_readonly,
    fetch_latest_brief,
    fetch_vehicle_series,
    list_cameras,
    read_ingest_heartbeat,
)
from city_pulse.dashboard.stream_preview import hls_preview_html


def _default_date_range() -> tuple[date, date]:
    """Last ~48h UTC — enough for live ingest without dominating chart."""
    today = datetime.now(UTC).date()
    return today - timedelta(days=1), today


def _default_cameras(settings: Settings, cameras_all: list[str]) -> list[str]:
    """Prefer the ingest camera key so live rows aren’t mixed with seed/demo keys."""
    key = settings.ingest_camera_key
    if key and key in cameras_all:
        return [key]
    return cameras_all


def _parse_date_range(raw: date | tuple[date, ...]) -> tuple[date, date]:
    if isinstance(raw, tuple):
        pair = cast(tuple[date, date], raw)
        return pair[0], pair[1]
    return raw, raw


def _chart_inputs(settings: Settings) -> tuple[list[str], tuple[date, date], str]:
    picked_live = st.session_state.get("dash_cameras") or []
    raw_d = st.session_state.get("dash_dates")
    if raw_d is None:
        drange = _default_date_range()
    else:
        drange = _parse_date_range(raw_d)
    choice = st.session_state.get("dash_bucket_choice", "5 minutes (live)")
    b_interval = "5 minutes" if str(choice).startswith("5") else "1 hour"
    return picked_live, drange, b_interval


def _draw_vehicle_chart(settings: Settings, *, static_caption: str | None) -> None:
    picked_live, (start_dc, end_dc), b_interval = _chart_inputs(settings)
    if not picked_live:
        st.info("Select at least one camera in the sidebar.")
        return
    conn_chart = connect_readonly(settings.database_readonly_url)
    try:
        df = fetch_vehicle_series(
            conn_chart,
            cameras=picked_live,
            start=start_dc,
            end_inclusive=end_dc,
            bucket_interval=b_interval,
        )
    finally:
        conn_chart.close()

    if df.empty:
        st.warning(
            "No rows in this range — run **city-pulse-ingest** + "
            "**city-pulse-vision-worker** with the same `INGEST_CAMERA_KEY`, "
            "or pick cameras that have data."
        )
        return

    pivot = df.pivot_table(
        index="bucket",
        columns="camera_location",
        values="total",
        aggfunc="sum",
    ).fillna(0)
    pivot.sort_index(inplace=True)
    st.line_chart(pivot)
    last_ts = pivot.index.max()
    if isinstance(last_ts, pd.Timestamp):
        ts_disp = last_ts.isoformat()
    else:
        ts_disp = str(last_ts)
    bits = [f"bucket={b_interval}", f"latest bucket UTC: {ts_disp}"]
    if static_caption:
        bits.append(static_caption)
    st.caption(" • ".join(bits))


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

    if cameras_all and "dash_cameras" not in st.session_state:
        st.session_state.dash_cameras = _default_cameras(settings, cameras_all)

    with st.sidebar:
        st.header("Filters")
        if not cameras_all:
            st.warning(
                "No cameras in `vehicle_counts`. "
                "Seed sample data or run ingest + vision."
            )
        else:
            st.multiselect(
                "Cameras",
                options=cameras_all,
                key="dash_cameras",
            )
        st.date_input(
            "Date range (UTC)",
            value=_default_date_range(),
            key="dash_dates",
        )

        st.selectbox(
            "Chart bucket (Timescale)",
            options=["5 minutes (live)", "1 hour"],
            index=0,
            key="dash_bucket_choice",
            help="5-minute buckets show counts rising during the current interval.",
        )
        st.checkbox(
            "Auto-refresh chart",
            value=True,
            key="dash_autorefresh",
            help=(
                f"Reloads the chart every {settings.dashboard_chart_refresh_seconds}s. "
                "Requires ingest + vision writing rows for your camera."
            ),
        )

    refresh_td = timedelta(seconds=settings.dashboard_chart_refresh_seconds)

    @st.fragment(run_every=refresh_td)
    def live_vehicle_chart_fragment() -> None:
        if not st.session_state.get("dash_autorefresh", True):
            return
        s = get_settings()
        _draw_vehicle_chart(
            s,
            static_caption=f"auto-refresh every {s.dashboard_chart_refresh_seconds}s",
        )

    if settings.ingest_m3u8_url:
        st.subheader("Live stream preview")
        st.caption(
            f"Public MDOT HLS — {settings.ingest_camera_key}. "
            "The player updates live segments; reload the page if the stream stalls."
        )
        components.html(
            hls_preview_html(settings.ingest_m3u8_url.strip()),
            height=400,
            scrolling=False,
        )

    col_chart, col_brief = st.columns((3, 2))

    with col_chart:
        st.subheader("Vehicle counts")
        if st.session_state.get("dash_autorefresh", True):
            live_vehicle_chart_fragment()
        else:
            _draw_vehicle_chart(
                settings,
                static_caption="auto-refresh off — change sidebar to reload",
            )

    with col_brief:
        st.subheader("Latest daily brief")
        if brief is None:
            st.info("No rows in `daily_briefs`. Run `city-pulse-daily-brief` or seed.")
        else:
            st.metric("Day (UTC)", str(brief.day))
            st.caption(f"Generated {brief.generated_at.isoformat()}")
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

        err_hb = None
        hb = None
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
