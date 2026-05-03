"""Streamlit dashboard: live HLS, auto-refresh counts chart, brief, ops."""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, timedelta
from textwrap import dedent
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
    fetch_live_rollup,
    fetch_vehicle_series,
    list_cameras,
    read_ingest_heartbeat,
    read_ingest_sample_override,
    read_latest_overlay,
    write_ingest_sample_override,
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


def _bucket_interval_from_ui(choice: object) -> str:
    """Map sidebar label to a Postgres ``interval`` string for ``time_bucket``."""
    s = str(choice).lower()
    if s.startswith("1 minute"):
        return "1 minute"
    if s.startswith("1 hour"):
        return "1 hour"
    # "5 minutes (default|live|…)" and legacy session keys
    return "5 minutes"


def _chart_inputs(settings: Settings) -> tuple[list[str], tuple[date, date], str]:
    picked_live = st.session_state.get("dash_cameras") or []
    raw_d = st.session_state.get("dash_dates")
    if raw_d is None:
        drange = _default_date_range()
    else:
        drange = _parse_date_range(raw_d)
    choice = st.session_state.get("dash_bucket_choice", "5 minutes (default)")
    b_interval = _bucket_interval_from_ui(choice)
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
        live = fetch_live_rollup(conn_chart, cameras=picked_live, window_minutes=15)
    finally:
        conn_chart.close()

    if df.empty:
        st.warning(
            "No `vehicle_counts` rows in this range for the selected camera(s). "
            "The **live HLS player** only loads the public stream in your browser — "
            "it does **not** write the database. "
            "Counts need **city-pulse-ingest** (sample → Redis) and "
            "**city-pulse-vision-worker** (Redis → YOLO → DB), e.g. "
            "`rtk city-pulse-stack`, matching `INGEST_CAMERA_KEY` in the sidebar, "
            "or pick cameras that already have data."
        )
        return

    m1, m2, m3 = st.columns(3)
    with m1:
        if live.latest_detection_utc:
            st.metric(
                "Last detection row (UTC)",
                live.latest_detection_utc.strftime("%H:%M:%S"),
                help="New frames refresh this timestamp when vision writes DB rows.",
            )
        else:
            st.metric("Last detection row (UTC)", "—")
    with m2:
        st.metric(
            f"Rows written ({live.window_minutes} min)",
            live.rows_last_window,
            help="Raw inserts into vehicle_counts (≈ one per sampled frame).",
        )
    with m3:
        st.metric(
            f"Vehicles summed ({live.window_minutes} min)",
            live.vehicles_sum_last_window,
            help=(
                "Sum of bounding-box counts from YOLO on sampled frames — not "
                "'every car on screen,' and not unique vehicles across frames."
            ),
        )

    with st.expander("Why totals look much lower than the live video"):
        st.markdown(
            dedent(
                """
                The player shows **continuous** video. The database only sees
                **occasional still JPEGs** from ingest, each run through a **small**
                detector.

                - **Sparse sampling** — one frame every
                  **INGEST_SAMPLE_INTERVAL_SECONDS** (see `.env`). Almost all video
                  frames are never scored.
                - **Boxes, not a census** — we add up **YOLO detections** whose labels
                  are in **VISION_VEHICLE_LABELS** and scores ≥
                  **VISION_MIN_CONFIDENCE**. Far away, overlapping, or poorly lit
                  vehicles are often missed.
                - **Model + feed** — default Docker image uses **YOLOv8n** on
                  compressed HLS; night and glare cost recall. This is an **activity
                  index**, not a traffic survey.

                **To nudge counts up:** shorten the ingest interval, slightly lower
                **VISION_MIN_CONFIDENCE**, raise **INGEST_JPEG_QUALITY**, or switch
                `models/yolov8/model-settings.json` to a larger `.pt` and **rebuild**
                the `yolo` image. Restart workers and Streamlit after `.env` changes.
                """
            )
        )
        st.caption(
            f"Running with: sample every {settings.ingest_sample_interval_seconds}s · "
            f"min_confidence={settings.vision_min_confidence} · "
            f"labels={settings.vision_vehicle_labels}"
        )

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
    st.caption(
        f"bucket={b_interval} • latest chart bucket UTC: {ts_disp}"
        + (f" • {static_caption}" if static_caption else "")
    )
    st.caption(
        "Chart points are **cumulative sums per UTC bucket** — the line can look "
        "stuck until more vehicles are counted in that bucket or the clock advances "
        "to the next bucket. Use **1 minute** in the sidebar for quicker steps; "
        "watch **Last detection** for proof that new rows are still landing."
    )


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
            "Chart bucket (Timescale, UTC)",
            options=[
                "1 minute (most responsive)",
                "5 minutes (default)",
                "1 hour",
            ],
            index=1,
            key="dash_bucket_choice",
            help=(
                "Each point is the **sum** of all detections in that time window. "
                "Within one bucket the line stays flat until more frames arrive or "
                "the clock enters the next bucket. Use 1-minute buckets to see "
                "motion sooner."
            ),
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
        st.divider()
        st.subheader("Runtime controls")
        st.caption("These update Redis keys read by running workers.")
        if redis_client is None:
            st.info("Redis unavailable — runtime controls disabled.")
        else:
            current_override = None
            if settings.ingest_sample_interval_override_key:
                try:
                    current_override = read_ingest_sample_override(
                        redis_client,
                        key=settings.ingest_sample_interval_override_key,
                    )
                except redis.RedisError as exc:
                    st.warning(f"Cannot read ingest override: {exc}")
            default_interval = settings.ingest_sample_interval_seconds
            active_interval = current_override or default_interval
            st.caption(
                f"Current ingest interval: {active_interval:.2f}s "
                f"(default {default_interval:.2f}s)"
            )
            new_interval = st.slider(
                "Ingest sample interval (seconds)",
                min_value=0.5,
                max_value=15.0,
                value=float(active_interval),
                step=0.5,
                key="dash_ingest_interval_slider",
                help=(
                    "Lower means more frequent frames and smoother overlay, but "
                    "more CPU load."
                ),
            )
            if st.button(
                "Apply ingest interval",
                key="dash_apply_ingest_interval",
                use_container_width=True,
            ):
                try:
                    ok = write_ingest_sample_override(
                        redis_client,
                        key=settings.ingest_sample_interval_override_key,
                        seconds=float(new_interval),
                    )
                except redis.RedisError as exc:
                    st.error(f"Failed to set ingest interval: {exc}")
                else:
                    if ok:
                        st.success(
                            f"Ingest interval override set to {new_interval:.2f}s."
                        )
                    else:
                        st.warning("Ingest override key disabled in settings/env.")
            st.checkbox(
                "Show live detection overlay",
                value=False,
                key="dash_show_overlay",
                help=(
                    "Shows latest YOLO-annotated frame from the vision worker. "
                    "Requires VISION_DEBUG_OVERLAY_ENABLED=1."
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

    @st.fragment(run_every=refresh_td)
    def live_overlay_fragment() -> None:
        if not st.session_state.get("dash_show_overlay", False):
            return
        if redis_client is None:
            st.info("Redis unavailable — cannot load overlay frame.")
            return
        try:
            overlay = read_latest_overlay(
                redis_client,
                key=settings.vision_debug_overlay_key,
            )
        except redis.RedisError as exc:
            st.warning(f"Overlay read failed: {exc}")
            return
        if overlay is None:
            st.info(
                "No overlay frame yet. Enable "
                "`VISION_DEBUG_OVERLAY_ENABLED=1`, restart "
                "`city-pulse-vision-worker`, and wait a few samples."
            )
            return
        try:
            img = base64.b64decode(overlay.annotated_jpeg_b64)
        except ValueError:
            st.warning("Overlay payload decode failed (invalid base64).")
            return
        st.image(
            img,
            caption=(
                f"{overlay.camera_key} • {overlay.captured_at} UTC • "
                f"count={overlay.vehicle_count} • "
                f"infer={overlay.latency_ms:.1f}ms"
            ),
            use_container_width=True,
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
        st.info(
            "**Vehicle counts are separate from this video.** "
            "The player only fetches the same public `.m3u8` in your browser. "
            "The database updates only when **city-pulse-ingest** and "
            "**city-pulse-vision-worker** run "
            "(frames → Redis → YOLO :8080 → Timescale). "
            "Use `rtk city-pulse-stack` for ingest + vision + this UI, "
            "or check queue / heartbeat under **Vehicle counts** and **Ops**."
        )
        if st.session_state.get("dash_show_overlay", False):
            st.subheader("Live detections (annotated)")
            live_overlay_fragment()

    col_chart, col_brief = st.columns((3, 2))

    with col_chart:
        st.subheader("Vehicle counts")
        parts: list[str] = []
        if redis_client is not None:
            try:
                qd = int(cast(int, redis_client.llen(settings.ingest_queue_key)))
                parts.append(f"Redis frame queue: **{qd}**")
            except redis.RedisError as exc:
                parts.append(f"Redis queue error: {exc}")
        else:
            parts.append("Redis unavailable — cannot show queue depth")
        if settings.ingest_heartbeat_key and redis_client is not None:
            try:
                hb_q = read_ingest_heartbeat(
                    redis_client,
                    key=settings.ingest_heartbeat_key,
                )
                if hb_q:
                    parts.append(f"Last ingest enqueue (UTC): {hb_q}")
                else:
                    parts.append(
                        "Ingest heartbeat missing — start **city-pulse-ingest**"
                    )
            except redis.RedisError as exc:
                parts.append(f"Heartbeat error: {exc}")
        elif settings.ingest_heartbeat_key and redis_client is None:
            parts.append("(heartbeat needs Redis)")
        if parts:
            st.caption(" · ".join(parts))
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
