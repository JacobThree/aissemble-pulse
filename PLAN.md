# Implementation Plan: City Pulse OSINT Tracker (I‑695 / MDOT lane)

*Source of truth for product intent:* `[SPEC.md](SPEC.md)`.

*This doc is Phase 2 (Plan) output per `.cursor/rules/planning-and-task-breakdown.md` and `.cursor/rules/spec-driven-development.md`. All shell snippets use `**rtk*`* per `.cursor/rules/stack-runtime.md`.*

---

## Overview

Implement **City Pulse**: pull public MDOT **HLS** frames on an interval → **Redis** queue → **MLServer/YOLO** (aiSSEMBLE Inference) → **TimescaleDB** counts; cron-style **daily brief** via **Sumy** MLServer; **Streamlit** for trends + latest brief — all bring-up via **Docker Compose** for portfolio-grade MLOps demo.

**Decisions:** aligned with SPEC § “Resolved questions (recommended answers)” — summarized here for implementers:


| Topic                        | Decision                                                                                                                                                                                                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Topology                     | **Single Compose stack** — Fedora VPS / DO / Docker Desktop Mac; hybrid laptop-ingest deferred.                                                                                                                  |
| Streamlit ↔ data             | **Direct Timescale reads** via `DATABASE_READONLY_URL` + Postgres role `**city_pulse_reader`**; FastAPI = health + optional config later — **no REST read model** until expose dashboard beyond trusted network. |
| Vehicle taxonomy             | **Single `vehicle_count*`* MVP; detector labels summed from configurable allow-list (`car`, `truck`, `bus`, `motorcycle`).                                                                                       |
| NLP “interesting day” signal | Hourly rollup + **top-3 busy hours + peak vs median** prose; rolling **z-score vs same-DOW trailing 7d** only after **≥14 days** telemetry; optional env absolute threshold flair.                               |
| GIS camera roster            | `**scripts/export_mdot_cameras.py`** → `**deploy/cameras.towson.yaml`** checked in + README quarterly refresh note; YAML hand-edit fallback.                                                                     |


---

## Architecture decisions

1. **Decouple ingest from inference:** Redis list or stream acts shock absorber; ingest never awaits YOLO.
2. **OIP-first:** Prefer aiSSEMBLE Inference **client abstractions** over hand-rolled tensors; MLServer endpoints match deploy scaffold.
3. **Schema v1 frozen small:** `(time timestamptz, camera_location text, vehicle_count int)` hypertable plus separate `daily_briefs (day date pk, body text)` (or equivalent) — widen schema only after SPEC “Ask first.”
4. **Config-driven cameras:** YAML/JSON keyed list with `camera_id`, `camera_location`, `m3u8_url` validated at startup.
5. **Multi-arch documented:** Compose/README call out `DOCKER_DEFAULT_PLATFORM` / `docker buildx` when M1 → amd64 VPS.

---

## Component dependency graph

```text
                    ┌─────────────────┐
                    │  camera config   │
                    └────────┬────────┘
                             │
camera_config ──► ingest ──► Redis ◄──── vision_worker
                                         │ calls
                                         ▼
                                    MLServer(YOLO)
                                         │
                                         ▼
                                    TimescaleDB ◄──── nlp_daily_job
                                         │                   │
                                         │                   ▼
                                         │            MLServer(Sumy)
                                         ▼                   │
                                       Streamlit ◄───────────┘
                                         ▲
                                    (brief table + counts)
FastAPI ──► health (/healthz) ─ optional future
```

*Build order respects bottom-up infra, then vertical slice ingest→DB, then NLP→UI.*

---

## Task list

### Phase 1: Foundation

#### Task 1: Python package scaffold + toolchain

**Description:** Establish `city_pulse` installable layout, pytest/ruff configs, typed settings stub for env vars.

**Acceptance criteria:**

- `rtk pytest tests/` runs (collection OK; smallest placeholder test passes).
- `pyproject.toml` pins dev deps (`pytest`, `ruff`, optionally `mypy`).
- Empty `city_pulse.config` exposes Pydantic `Settings` with `DATABASE_URL`, `REDIS_URL`, placeholder `YOLO_ENDPOINT`.

**Verification:**

- `rtk pytest tests/ -q`
- `rtk bash -lc 'ruff check src tests && ruff format --check src tests'`

**Dependencies:** None

**Files likely touched:**

- `pyproject.toml`
- `src/city_pulse/__init__.py`
- `src/city_pulse/config/__init__.py`
- `src/city_pulse/config/settings.py`
- `tests/test_smoke.py`

**Estimated scope:** Small

---

#### Task 2: Compose — Redis + TimescaleDB + init schema

**Description:** Working `docker-compose.yml` wiring Redis and Timescale; SQL init enables Timescale extension, creates hypertable for counts table and `daily_briefs` storage.

**Acceptance criteria:**

- `rtk docker compose up -d redis timescaledb` (service names illustrative) exits clean; containers healthy.
- Applying init SQL yields hypertable-ready table matching SPEC Appendix B (+ brief table).

**Verification:**

- `rtk docker compose ps` shows healthy services.
- Manual: `rtk bash -lc 'docker compose exec timescaledb psql -U ... -d ... -c "\dt"'` lists expected tables (*or scripted check*).

**Dependencies:** Task 1 (optional tooling only — can parallel if human prefers; schema files live in-repo either way).

**Files likely touched:**

- `docker-compose.yml`
- `deploy/sql/` or `scripts/init-timescale.sql`
- `README.md` (short “infra up” blurb)

**Estimated scope:** Medium

---

### Checkpoint: Foundation

- `rtk pytest` passes.
- Redis + Timescale reachable from host per README.
- Brief human skim of compose + SQL before pipelines.

---

### Phase 2: Vertical slice — capture → persist counts

#### Task 3: HLS ingestion → Redis enqueue

**Description:** Minimal worker looping `cv2.VideoCapture` on configurable `.m3u8`, samples every 5–10s, pushes JSON `{camera_key, captured_at, frame_b64}` to Redis queue with bounded length / TTL documented.

**Acceptance criteria:**

- Restart-tolerant backoff on stream failure; metrics counter for drops.
- Unit tests for serialization + backoff helper (deterministic clock/mocks).

**Verification:**

- `rtk pytest tests/unit/ -q` includes ingest coverage.
- Manual smoke: ingest runs 2 min against one MDOT URL, `redis-cli` shows queue depth non-zero then draining when worker mocked.

**Dependencies:** Tasks 1–2.

**Files likely touched:**

- `src/city_pulse/ingest/capture.py`
- `src/city_pulse/ingest/redis_queue.py`
- `tests/unit/test_ingest_*.py`
- `README.md`

**Estimated scope:** Medium

---

#### Task 4: YOLO MLServer footprint in Compose

**Description:** Vendor `deploy/yolo/` (or subdirectory) consistent with `**rtk inference deploy init --target docker`** output documented in SPEC; Compose service exposes OIP-compatible port wired to `.env`; smoke health check curls inference metadata or dummy predict with fixture image bytes.

**Acceptance criteria:**

- YOLO container starts via Compose; reproducible README steps.
- Smoke script or pytest integration mark hits endpoint (may use canned base64 fixture).

**Verification:**

- `rtk docker compose up -d yolo`
- Smoke: HTTP 200 predict path *(or graceful skip documented if GPU optional — must not fail silently).*

**Dependencies:** Task 2 *(same `docker-compose.yml`; coordinate merges if Task 3 edits Compose in parallel).*

**Files likely touched:**

- `deploy/yolo/`**
- `docker-compose.yml`
- `.env.example`
- `docs/mlserver-smoke.md` or README section

**Estimated scope:** Large → if >5 files, split into Task 4a “generated assets” + Task 4b “compose wiring” internally in one PR or two sequential tasks by human choice.

---

#### Task 5: Vision worker — Redis consumer → MLServer → Timescale

**Description:** Dedicated process pulls frames from Redis, calls inference client (**httpx**/aiSSEMBLE Inference client), derives `vehicle_count`, inserts row into hypertable transactionally.

**Acceptance criteria:**

- Configurable parallelism (single worker MVP OK).
- Structured logs with `camera_key`, inference latency_ms, Redis lag.
- Integration test with faker MLServer (**pytest-httpserver**/*responses*) + either real Redis in Compose or faker.

**Verification:**

- `rtk pytest tests/integration/ -m integration -q`

**Dependencies:** Tasks 3, 4.

**Files likely touched:**

- `src/city_pulse/workers/vision_worker.py`
- `src/city_pulse/db/pool.py` + `metrics_repo.py`
- `tests/integration/test_vision_path.py`

**Estimated scope:** Medium–Large *(keep ≤5 files per PR iteration; extract repo module if swell).*

---

### Checkpoint: Pipe A (vision) alive

- End-to-end manual: ingest + worker + MLServer ⇒ new rows in hypertable across ≥10 samples.
- No Redis unbounded growth (documented maxlen/TTL/eviction).

---

### Phase 3: NLP brief + dashboard

#### Task 6: Sumy MLServer + daily brief job

**Description:** Compose service for `**aissemble-inference-sumy`**; Python job aggregates last 24h per camera (“peak windows”, totals), builds Markdown/plain text capsule, POSTs to Sumy → stores `daily_briefs`.

**Acceptance criteria:**

- Idempotent rerun for same `day`.
- Unit test aggregates math with frozen hourly fixture data.

**Verification:**

- `rtk pytest tests/unit/test_daily_aggregate.py -q`
- Manual: job prints/stores paragraph referencing known fixture peak.

**Dependencies:** Tasks 2, 5.

**Files likely touched:**

- `deploy/sumy/`**
- `docker-compose.yml`
- `src/city_pulse/nlp_jobs/daily_brief.py`
- `tests/unit/test_daily_aggregate.py`

**Estimated scope:** Medium

---

#### Task 7: Streamlit dashboard

**Description:** Read-only dashboard: selectors for camera + date range chart from Timescale, panel for latest brief from `daily_briefs`; optional ops panel (“last ingest time” Redis key or heartbeat table).

**Acceptance criteria:**

- Charts render with seeded sample data *(document seed script).*

**Verification:**

- Manual `rtk streamlit run src/city_pulse/dashboard/app.py`.
- Screenshot checklist in README (optional).

**Dependencies:** Tasks 5–6.

**Files likely touched:**

- `src/city_pulse/dashboard/app.py`
- `src/city_pulse/dashboard/queries.sql` or inlined safe queries
- `README.md`

**Estimated scope:** Medium

---

#### Task 8: README + reproducibility pass

**Description:** README “clone → compose up → ingest → dashboard” narrative; GIS note for deriving `camera_id`; legal **public-feed-only** stance; `**rtk`** command copy-paste aligns with SPEC.

**Acceptance criteria:**

- Fresh clone checklist verified by practitioner (human or scripted smoke).
- `.env.example` covers all URLs/secrets placeholders.

**Verification:**

- Human walk-through against SPEC §Success Criteria 1–7.

**Dependencies:** Tasks 6–7 (and all prior infra).

**Files likely touched:**

- `README.md`
- `.env.example`
- `SPEC.md` (only if deltas discovered — prefer PR note)

**Estimated scope:** Small

---

### Checkpoint: MVP complete

- SPEC **Success Criteria** section satisfied (numbered list 1–7).
- All automated tests passing; manual E2E path documented.

---

### Phase 4 (stretch — gated)

Post-MVP backlog (not MVP acceptance):

- Second feed toggle (EarthCam / Port YAML entry + separate ingest profile).
- `**rtk inference deploy init --target kubernetes --target kserve`** path doc only or light manifest.
- Prometheus metrics exporter on workers.

---

## Risks and mitigations


| Risk                                          | Impact              | Mitigation                                                                        |
| --------------------------------------------- | ------------------- | --------------------------------------------------------------------------------- |
| MDOT CDN / GIS URL churn                      | Breaks ingest       | Config externalized; backoff; monitor health; GIS export script pinned in README. |
| MLServer container size / model pull timeouts | Compose fails CI    | Slim base + documented pre-pull; GHCR mirror optional.                            |
| M1 ↔ amd64 image mismatch                     | VPS deploy broken   | Compose `platform: linux/amd64` docs + local buildx snippet.                      |
| OpenCV/ffmpeg HLS quirks on Fedora            | Drops frames        | Optional ffmpeg subprocess path fallback; backoff metrics.                        |
| aiSSEMBLE Inference API churn                 | Broken client calls | Pin versions in pyproject once stable; smoke tests on upgrade.                    |


---

## Resolved questions (same recommendations as SPEC)

Details + rationale live in SPEC § **Resolved questions (recommended answers)**. Implementation stance:


| #   | Former open item     | Locked direction                                                                                                                                    |
| --- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Topology             | **Compose single-host** MVP.                                                                                                                        |
| 2   | Taxonomy / per-class | **Roll up** to `vehicle_count`; extend schema **post-MVP** if charts demand.                                                                        |
| 3   | Anomaly heuristic    | `**nlp_jobs` builds deterministic bullet facts** (`peak hour`, top-3, median contrast); gates stats richness on dataset age (**14-day** threshold). |
| 4   | GIS → cameras        | `**export_mdot_cameras.py` + YAML artifact** + manual fallback.                                                                                     |
| 5   | Streamlit REST       | **Not for MVP**; add BFF/read API only on **security trigger** (public route, auth, multi-consumer).                                                |


**Change control:** revise SPEC table first, then mirror here.

---

## Parallelization


| Parallel OK (after prerequisites)                                                 | Must stay sequential                         |
| --------------------------------------------------------------------------------- | -------------------------------------------- |
| README polish while infra reviewed (avoid blocking code) after Task schema stable | DB schema init → workers writing rows        |
| Unit tests alongside Task 4 container bring-up *(contract tests)*                 | YOLO service healthy → Task 5 integration    |
| Separate agents: Task 7 UI mocks vs Task 6 NLP aggregates *if Sumy mocked*        | Compose network + Volume layout agreed first |


Define **MLServer inference HTTP contract** (payload shape stub) early so Tasks 5–6 can mock in parallel.

---

## Plan verification checklist

Before implementation starts:

- Every task lists acceptance criteria + verification + deps.
- No single task nominally edits **> ~5 files** without split (adjust Task 4 or 5 if needed).
- Checkpoints cover foundation, vision slice, NLP/UI, MVP done.
- Human acknowledged resolved-question defaults (SPEC + this section) or recorded overrides.

