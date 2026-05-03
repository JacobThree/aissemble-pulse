# City Pulse (I‑695 / MDOT)

Public-camera ingest → YOLO → Timescale → daily briefs. See [`SPEC.md`](SPEC.md) and [`PLAN.md`](PLAN.md).

## Dev

Requires **Python 3.11+** (repo tested with 3.12; macOS `python3` may be older — use `python3.12 -m venv .venv`).

```bash
rtk python3.12 -m venv .venv
rtk bash -lc 'source .venv/bin/activate && pip install -e ".[dev]"'
rtk bash -lc 'source .venv/bin/activate && pytest tests/ -q'
rtk bash -lc 'source .venv/bin/activate && ruff check src tests && ruff format --check src tests'
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
