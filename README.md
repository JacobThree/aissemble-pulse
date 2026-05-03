# City Pulse (I-695 / MDOT)

City Pulse is a local MLOps demo that samples public MDOT traffic video, runs YOLO detections, stores counts in TimescaleDB, and shows live trends in Streamlit.

Pipeline:

`HLS (.m3u8) -> ingest -> Redis -> vision worker -> YOLO (MLServer/aiSSEMBLE Inference) -> TimescaleDB -> Streamlit`

## Dependencies

- Python 3.12 (recommended)
- Docker Desktop (Compose)
- Redis
- TimescaleDB/Postgres
- MLServer YOLO container (`aissemble-inference-yolo`)
- Optional: Sumy container (`aissemble-inference-sumy`) for daily brief generation

Python dependencies are installed from `pyproject.toml`:

- core app deps: Streamlit, psycopg, redis, opencv, etc.
- optional `aissemble` extras for inference deploy tooling/runtimes

## Quick start (local)

From repo root:

```bash
rtk python3.12 -m venv .venv
rtk bash -lc 'source .venv/bin/activate && pip install -e ".[dev]"'
cp .env.example .env
rtk bash scripts/run_local_stack.sh
```

Open: `http://localhost:8501`

What `scripts/run_local_stack.sh` does:

1. Starts Docker services (`redis`, `timescaledb`, `yolo`) unless skipped
2. Runs preflight checks (Redis, Postgres, YOLO readiness)
3. Runs:
   - `city-pulse-ingest`
   - `city-pulse-vision-worker`
   - Streamlit dashboard

Logs:

- `logs/ingest.log`
- `logs/vision.log`
- `logs/stack-console.log`

## Key environment variables

See `.env.example` for all options. Most important:

- `DATABASE_URL`, `DATABASE_READONLY_URL`
- `REDIS_URL`
- `YOLO_ENDPOINT`
- `INGEST_M3U8_URL`
- `INGEST_CAMERA_KEY`
- `INGEST_SAMPLE_INTERVAL_SECONDS`
- `VISION_MIN_CONFIDENCE`
- `VISION_DEBUG_OVERLAY_ENABLED`

Advanced counting controls:

- `VISION_ROI_NORM` (normalized ROI: `x1,y1,x2,y2`)
- `VISION_DEDUP_ENABLED`
- `VISION_DEDUP_IOU_THRESHOLD`
- `VISION_DEDUP_TTL_SECONDS`

## Deploy (concise)

This project is currently optimized for Docker/Compose deployment.

1. Build images:

```bash
docker compose build yolo
```

2. Set production env vars (`.env` or secrets manager): DB/Redis/YOLO endpoints, ingest URL, camera key, and counting thresholds.

3. Start services:

```bash
docker compose up -d redis timescaledb yolo
```

4. Start app processes (systemd/supervisor/containers):

- `city-pulse-ingest`
- `city-pulse-vision-worker`
- `streamlit run src/city_pulse/dashboard/app.py`

5. Verify health:

```bash
curl -sf http://127.0.0.1:8080/v2/health/ready && echo "YOLO OK"
```

## Notes

- Use only public, permitted camera feeds.
- Reset DB volume (destructive):

```bash
docker compose down -v
```

- Full troubleshooting history: `docs/city-pulse-debugging-retrospective.md`

