# City Pulse Debugging & Build Retrospective

## Why this document exists

This project went through an end-to-end debugging and hardening cycle: from "video loads but chart is flat" to a working local stack with real-time-ish overlay, runtime tuning controls, and better counting controls (ROI + temporal dedup).

This write-up captures:

- What the system is
- What failed and why
- What we changed
- What remains to optimize
- How to run/debug it reproducibly

---

## Project goal

Build a local-first MLOps traffic pipeline using public Maryland DOT HLS streams:

1. Sample frames from HLS
2. Queue in Redis
3. Run YOLO inference through MLServer / aiSSEMBLE Inference runtime
4. Write counts to TimescaleDB
5. Display trends + operations state in Streamlit
6. (Optional) generate daily text briefs with Sumy

---

## Tech stack

- **Language/runtime:** Python 3.12 (local venv)
- **Queue:** Redis
- **DB:** TimescaleDB (Postgres)
- **Inference serving:** MLServer
- **Model runtime:** `aissemble-inference-yolo`
- **NLP runtime:** `aissemble-inference-sumy`
- **Container orchestration:** Docker Compose
- **UI:** Streamlit
- **Data source:** Public MDOT HLS (`playlist.m3u8`)

Core services/processes:

- `city-pulse-ingest`
- `city-pulse-vision-worker`
- `streamlit run src/city_pulse/dashboard/app.py`
- Docker services: `redis`, `timescaledb`, `yolo` (and optional `sumy`)

---

## Architecture (current)

`HLS stream -> ingest -> Redis list -> vision worker -> YOLO infer -> vehicle_counts -> Streamlit dashboard`

Important distinction that caused confusion early:

- **Live preview video** in Streamlit is browser-side HLS playback.
- **Chart data** only updates from `vehicle_counts` DB writes.
- Therefore: moving cars in preview != pipeline writing rows.

---

## Major issues we hit and how we fixed them

## 1) "Chart not updating" while video looked live

### Symptoms

- Stream preview worked.
- Chart stayed flat or empty.
- User suspected `.env`, DB, YOLO, or test data mismatch.

### Root causes

- Inference service not healthy/loaded
- No visibility into ingest/vision failures
- Camera key mismatch between seeded demo data and live camera

### Fixes

- Added `scripts/preflight_stack.py`:
  - Redis ping
  - Postgres connect check
  - YOLO readiness polling (`/v2/health/ready`)
  - camera/data summary hint
- Updated one-command runner to include preflight and log files:
  - `logs/ingest.log`
  - `logs/vision.log`
- Updated docs and messages to explain preview-vs-pipeline difference.

---

## 2) YOLO container started then disappeared

### Symptoms

- `docker compose ps` showed only Redis + Timescale
- health checks on `:8080` failed/refused

### Root causes and fixes (in sequence)

1. **Wrong model tree copied into YOLO image**
   - YOLO image copied full `models/` directory including `sumy/`
   - MLServer attempted to load Sumy runtime in YOLO container
   - error: `ModuleNotFoundError: aissemble_inference_sumy`
   - **Fix:** copy only `models/yolov8/` in YOLO Dockerfile

2. **Missing ultralytics dependency**
   - error: `ModuleNotFoundError: ultralytics`
   - **Fix:** add `ultralytics` to YOLO image requirements

3. **OpenCV GUI dependency failure on slim image**
   - error: `ImportError: libxcb.so.1`
   - **Fix:** replace `opencv-python` with `opencv-python-headless` in YOLO image build

After these, YOLO reached healthy state and served infer requests.

---

## 3) Counts felt low / undercounted vs visible traffic

### Why this happened

- Sampling is sparse vs full video
- YOLO on compressed HLS can miss small/far/night objects
- confidence threshold filtered weak detections
- small model (`yolov8n`) favored speed over recall

### Fixes and tuning

- Added explanatory UI copy in dashboard
- Added responsive chart options:
  - 1-minute bucket
  - smoothed trend view
- Exposed runtime tuning controls:
  - ingest sample interval override (Redis-backed)
- Added debug overlay to visually inspect detections
- Upgraded model to `yolov8s.pt` for better recall
- Tuned defaults for better practical recall:
  - lower confidence
  - faster sampling
  - higher JPEG quality

---

## 4) Overlay toggle did nothing initially

### Symptoms

- Checkbox enabled but no visible annotated panel content

### Root causes

- Worker overlay setting not enabled/restarted in some runs
- UI state/process restarts out of sync

### Fixes

- Enabled `VISION_DEBUG_OVERLAY_ENABLED`
- Restarted worker/stack with updated env
- Added UI warnings for misconfiguration
- Verified overlay payload directly in Redis
- Added periodic overlay fragment refresh

---

## 5) Recounting across frames

### Symptoms

- Same vehicles effectively counted repeatedly

### Why

- Baseline implementation counts detections per frame, not tracked IDs

### Fixes implemented

- Added **optional ROI filter** (`VISION_ROI_NORM`) to focus counting area
- Added **temporal IoU dedup**:
  - `VISION_DEDUP_ENABLED`
  - `VISION_DEDUP_IOU_THRESHOLD`
  - `VISION_DEDUP_TTL_SECONDS`
- Drew ROI box on overlay for visual verification

### Limitation

This is still approximate. It reduces recounting, but does not fully solve identity persistence like a true tracker would.

---

## UI/UX improvements made

- Side-by-side layout: live preview and annotated overlay
- Smaller preview footprint
- Better metrics:
  - total vehicles (all-time for selected cameras)
  - vehicles summed (last 15 min)
- Removed less useful "last row detected" metric
- Better runtime controls and operational hints

---

## Operational tooling added

- `scripts/preflight_stack.py`
- improved `scripts/run_local_stack.sh` behavior
- clearer startup logs
- explicit troubleshooting docs

---

## Current known gaps / technical debt

1. **Counting semantics**
   - Still frame-based detection sums; not strict "count each car once"
2. **Tracking quality**
   - Temporal IoU dedup is heuristic and camera-specific
3. **Performance**
   - `yolov8s` improves recall but increases inference latency
4. **Streamlit deprecation warnings**
   - `st.components.v1.html` and `use_container_width` warnings should be cleaned up
5. **Runtime resiliency**
   - Better automatic restart/backoff behavior for transient Redis/HLS interruptions
6. **Config UX**
   - ROI editor in UI (drag box) not yet implemented

---

## Optimization roadmap (recommended next)

## Phase 1 (short-term, practical)

- Add dashboard controls for:
  - ROI presets per camera
  - dedup IoU/TTL sliders
- Add latency/throughput panel:
  - infer p50/p95, queue age, frames/sec
- Add a "safe preset" selector (Recall / Balanced / Fast)

## Phase 2 (accuracy)

- Implement simple multi-object tracking (e.g., ByteTrack-style IDs) for stronger anti-recount behavior
- Add optional line-crossing mode ("count each object once when crossing line")

## Phase 3 (performance)

- Profile bottlenecks and tune:
  - frame size
  - model size
  - interval
  - batch strategy (if viable)
- Evaluate hardware acceleration path for Apple Silicon outside current container constraints

---

## Reproducible runbook (post-reboot)

```bash
cd "/Users/jacobsmythe/i695 traffic"
source .venv/bin/activate
rtk docker compose up -d redis timescaledb yolo
rtk bash scripts/run_local_stack.sh
```

Open: `http://localhost:8501`

If needed:

```bash
tail -f logs/ingest.log logs/vision.log
```

---

## Suggested baseline env for this camera

Example settings that worked better during this debugging cycle:

- `VISION_MIN_CONFIDENCE=0.15`
- `INGEST_SAMPLE_INTERVAL_SECONDS=2.0`
- `INGEST_JPEG_QUALITY=92`
- `VISION_DEBUG_OVERLAY_ENABLED=1`
- `VISION_ROI_NORM=0.40,0.20,1.00,1.00`
- `VISION_DEDUP_ENABLED=1`
- `VISION_DEDUP_IOU_THRESHOLD=0.35` to `0.60` (camera dependent)
- `VISION_DEDUP_TTL_SECONDS=2.0` to `5.0`

Tune for your tolerance of:

- false positives
- recounting
- responsiveness
- CPU/GPU load

---

## Closing summary

The project is now in a significantly more usable state than the original baseline:

- one-command local bring-up with preflight
- reliable YOLO container startup
- live visual debugging overlay
- runtime ingest tuning
- ROI + temporal dedup controls
- clearer dashboard behavior and metrics

The next meaningful quality jump is moving from heuristic dedup to true object tracking/line-crossing counting.
