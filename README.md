# City Pulse (I‑695 / MDOT)

Public-camera ingest → YOLO → Timescale → daily briefs. See [`SPEC.md`](SPEC.md) and [`PLAN.md`](PLAN.md).

## Clone → dashboard (reproducible path)

Commands assume repo root and the **`rtk`** prefix on runnable shells ([`.cursor/rules/stack-runtime.md`](.cursor/rules/stack-runtime.md)).

1. **Clone** this repository and enter the project directory (`cd` …).
2. **Python env**
   ```bash
   rtk python3.12 -m venv .venv
   rtk bash -lc 'source .venv/bin/activate && pip install -e ".[dev]"'
   ```
3. **Environment** — copy [`.env.example`](.env.example) → `.env` (defaults match Compose on **localhost:5433**).
4. **Infra** — Redis + TimescaleDB (required for DB-backed UI):
   ```bash
   rtk docker compose up -d redis timescaledb
   ```
5. **Sample data + Streamlit** — seeds hourly counts + one brief (loads `.env` so **`DATABASE_URL`** is set for write user `city_pulse`):
   ```bash
   rtk bash -lc 'source .venv/bin/activate && set -a && source .env && set +a && python scripts/seed_dashboard_sample.py'
   rtk bash -lc 'source .venv/bin/activate && set -a && source .env && set +a && streamlit run src/city_pulse/dashboard/app.py'
   ```
6. **Optional full ML pipeline** — bring up YOLO + Sumy, run ingest (real public `.m3u8`), vision worker, daily brief — see sections below.

**Automated checks (after `pip install -e ".[dev]"`):**

```bash
rtk bash -lc 'bash scripts/verify_local.sh'
```

## Legal & feeds

Use **only public, operator-published streams** you are allowed to observe (Maryland SHA traffic cameras are intended as public situational awareness). Do **not** point this pipeline at private, authenticated, or unclear-license feeds. See SPEC **Success Criteria §7** and **Boundaries → Never do**.

## Camera IDs (`camera_id`) & GIS

MDOT CHART HLS URLs follow:

`https://strmr5.sha.maryland.gov/rtplive/{camera_id}/playlist.m3u8`

Resolve **`camera_id`** from Maryland’s open ArcGIS traffic-camera catalog (Towson / I‑695 corridor filters). Validate IDs against that catalog when adding cameras; **SPEC §Resolved questions** describes a planned **`scripts/export_mdot_cameras.py`** → YAML workflow — until that lands, hand-pick IDs from the catalog and set **`INGEST_CAMERA_KEY`** / **`INGEST_M3U8_URL`** accordingly.

## SPEC success criteria (MVP trace)

| # | Criterion | Where in this README |
| --- | --- | --- |
| 1 | Ingest MDOT `.m3u8`, bounded Redis queue | **Ingest (HLS → Redis)**, `INGEST_MAX_QUEUE_LENGTH` in [`.env.example`](.env.example) |
| 2 | Frames in Redis; ingest ≠ inference | **Vision worker (Redis → YOLO → Timescale)** |
| 3 | `vehicle_counts` rows | Vision worker; **Infra** for Timescale |
| 4 | Daily brief in DB | **Daily brief job**; optional seed in **Clone → dashboard** |
| 5 | Streamlit chart + brief | **Dashboard (Streamlit)** |
| 6 | Compose + MLServer | **Infra**, **YOLO (MLServer)**, **Sumy (MLServer)** |
| 7 | Public-feed stance + `camera_id` | **Legal & feeds**, **Camera IDs (GIS)** |

## Multi-arch Docker builds

If you build images on **Apple Silicon** and deploy to **amd64** (typical Linux VPS), set e.g. `DOCKER_DEFAULT_PLATFORM=linux/amd64` or use **`docker buildx`** when building/pushing — see [Docker multi-platform](https://docs.docker.com/build/building/multi-platform/).

## Dev

Requires **Python 3.11+** (repo tested with 3.12; macOS `python3` may be older — use `python3.12 -m venv .venv`).

```bash
rtk python3.12 -m venv .venv
rtk bash -lc 'source .venv/bin/activate && pip install -e ".[dev]"'
rtk bash -lc 'source .venv/bin/activate && pytest tests/ -q'
rtk bash -lc 'source .venv/bin/activate && ruff check src tests && ruff format --check src tests'
rtk bash -lc 'bash scripts/verify_local.sh'
```

Shell commands use the **`rtk`** prefix per [`.cursor/rules/stack-runtime.md`](.cursor/rules/stack-runtime.md).

## Infra (Redis + TimescaleDB)

Requires [Docker](https://docs.docker.com/get-docker/). First-time DB init runs `deploy/sql/init-timescale.sql` (hypertable `vehicle_counts`, table `daily_briefs`, dev-only read-only role `city_pulse_reader`).

```bash
rtk docker compose up -d redis timescaledb
rtk docker compose ps
```

Stop and remove containers (keep DB volume):

```bash
rtk docker compose down
```

Reset DB (**destroys** volume):

```bash
rtk docker compose down -v
```

Smoke-check tables:

```bash
rtk bash -lc 'docker compose exec timescaledb psql -U city_pulse -d city_pulse -c "\\dt"'
```

Copy `.env.example` → `.env` so app defaults match Compose (`DATABASE_URL` uses host port **5433**).

## Ingest (HLS → Redis)

Requires Redis up (`docker compose up -d redis`). Set **`INGEST_M3U8_URL`** to a public `.m3u8` (see SPEC — MDOT CHART pattern). Frames are JPEG base64 JSON blobs on list **`INGEST_QUEUE_KEY`** (default `city_pulse:frames`), capped at **`INGEST_MAX_QUEUE_LENGTH`** (oldest dropped when full).

```bash
rtk bash -lc 'source .venv/bin/activate && export INGEST_M3U8_URL="https://example.invalid/stream.m3u8" && city-pulse-ingest'
# or: rtk bash -lc 'source .venv/bin/activate && python -m city_pulse.ingest'
```

Queue depth:

```bash
rtk bash -lc 'docker compose exec redis redis-cli LLEN city_pulse:frames'
```

## YOLO (MLServer)

Dockerfile + MLServer layout come from **aissemble-inference-deploy** (`inference deploy init --target docker`). Model definition: `models/yolov8/model-settings.json` (downloads **`yolov8n.pt`** on first run inside the image).

```bash
rtk docker compose up -d yolo
rtk bash -lc 'curl -sf http://127.0.0.1:8080/v2/health/ready && echo OK'
```

Regenerate `deploy/docker/` after editing model configs (requires `.venv` + **`pip install -e ".[aissemble]"`**):

```bash
rtk bash -lc 'source .venv/bin/activate && inference deploy init --target docker --model-dir models --output-dir deploy'
```

More checks: [`docs/mlserver-smoke.md`](docs/mlserver-smoke.md). **`YOLO_ENDPOINT`** defaults to `http://localhost:8080` (REST/OIP).

## Sumy (MLServer)

Text summarization via **`aissemble-inference-sumy`** (`models/sumy/model-settings.json`). Compose maps container HTTP **8080** → host **8090** so YOLO can keep **8080**.

```bash
rtk docker compose up -d sumy
rtk bash -lc 'curl -sf http://127.0.0.1:8090/v2/health/ready && echo OK'
```

Details: [`deploy/sumy/README.md`](deploy/sumy/README.md). Set **`SUMY_ENDPOINT=http://localhost:8090`** for the daily brief job.

## Daily brief job

Rolls up **`vehicle_counts`** into hourly buckets per camera for a **UTC calendar day**, builds a draft capsule, POSTs to Sumy infer, and **`UPSERT`** into **`daily_briefs`** (same `day` overwrites — safe to rerun). Default **`--day`**: **yesterday UTC**.

```bash
rtk docker compose up -d timescaledb sumy
rtk bash -lc 'source .venv/bin/activate && city-pulse-daily-brief'
# Pin the window explicitly:
rtk bash -lc 'source .venv/bin/activate && city-pulse-daily-brief --day 2026-05-01'
```

## Dashboard (Streamlit)

Read-only **Timescale** via **`DATABASE_READONLY_URL`** (role `city_pulse_reader`) plus **Redis** for queue depth + last ingest time (see **`INGEST_HEARTBEAT_KEY`**, set by **`city-pulse-ingest`** after each successful enqueue).

**Seed sample series + one brief** (requires DB up, write user `city_pulse`):

```bash
rtk docker compose up -d timescaledb redis
rtk bash -lc 'source .venv/bin/activate && set -a && source .env && set +a && python scripts/seed_dashboard_sample.py'
```

**Run the UI**

```bash
rtk bash -lc 'source .venv/bin/activate && streamlit run src/city_pulse/dashboard/app.py'
```

**Quick visual check (optional):** line chart shows two demo cameras; “Latest daily brief” shows seeded Markdown; Ops shows queue length and “Last ingest success” after a short ingest run (or “no key yet” if ingest never ran).

## Vision worker (Redis → YOLO → Timescale)

Consumes **`INGEST_QUEUE_KEY`** with [`FramePayload`](src/city_pulse/ingest/models.py) JSON (`camera_key`, `captured_at`, `frame_b64`), POSTs the frame to MLServer OIP infer, counts allowed labels above **`VISION_MIN_CONFIDENCE`**, and inserts into **`vehicle_counts`**. Needs Redis, TimescaleDB, and the **`yolo`** service (or any compatible OIP endpoint).

```bash
rtk bash -lc 'source .venv/bin/activate && city-pulse-vision-worker'
# or: rtk bash -lc 'source .venv/bin/activate && python -m city_pulse.workers'
```

Tune labels/timeouts via **`VISION_*`** env vars (see `.env.example`).

Integration smoke (skipped if MLServer down):

```bash
rtk bash -lc 'source .venv/bin/activate && pytest tests/integration/test_mlserver_ready.py -q -m integration'
```
