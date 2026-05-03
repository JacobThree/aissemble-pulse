# Spec: City Pulse OSINT Tracker (I‑695 / MDOT lane)

_Portfolio MLOps demo: vision + NLP on public feeds using [aiSSEMBLE Inference](https://github.com/boozallen/aissemble-inference) (Apache-2.0 upstream; no affiliation)._

_Source: distilled from `inital ai convo`; aligned to `.cursor/rules/spec-driven-development.md`._

_All documented shell invocations obey `.cursor/rules/stack-runtime.md`: **outer prefix `rtk`._

_For phased implementation tasks, checkpoints, and risk table, see **`PLAN.md`**._

---

## Assumptions I'm making

Correct these before implementation proceeds.

1. **Runtime:** Primary language Python **3.11+** on dev (M1 Mac) and Fedora **server** VM (Proxmox or VPS); not a native mobile app.
2. **Packaging:** Services run in **Docker** / **Compose** locally and on VPS; MLServer/Kubernetes is a later stretch, not MVP.
3. **Feeds:** Only **public** MDOT CHART **HLS** (and optionally named public EarthCam/port URLs); no authenticated or non-public cameras.
4. **Auth:** Dashboard is **operator-local** — no multi-tenant login for v1 unless added later.
5. **Orchestration:** **FastAPI** = health/metadata only MVP; **Streamlit** connects to Timescale via **read-only DB role** inside Compose (see **Resolved questions**).
6. **Versions:** Exact PyPI pins for aiSSEMBLE wheels follow whatever is current on PyPI when `pyproject.toml` is added (`Ask first` to freeze).

---

## Objective

### What and why

Public traffic cameras produce video few people distill into repeatable metrics. We're building **City Pulse**: ingest MDOT CHART streams (Towson/I‑695 first), queue frames, count vehicles with **YOLO** via **MLServer**, store time series in **TimescaleDB**, generate a **daily text brief** with **Sumy**, and visualize trends in **Streamlit**. Demo goal: credible **enterprise-style MLOps** (deployed inference, queues, persisted signal) vs a one-off script.

### Who uses it

- **Builder** (you): run stack locally or on VPS, tune cameras, iterate models.
- **Reviewer** (portfolio): read README, reproduce Compose bring-up, see dashboard + sample brief.

### User stories / acceptance anchors

- As operator, I can point at MDOT `.m3u8` URLs and receive **steady 5–10 s** snapshots without ingestion blocking on inference.
- As operator, I see **counts over time per camera** in the dashboard for at least **one Towson-corridor cam**.
- As operator, I get a **generated daily paragraph** summarizing peaks/volume drawn from persisted aggregates.

---

## Tech Stack

| Area | Choice | Notes |
| --- | --- | --- |
| Language | Python **3.11+** | Async OK for ingestion; workers can be sync |
| API / glue | **FastAPI** | Health, optional config CRUD later |
| UI | **Streamlit** | Trends + brief |
| Inference | **MLServer** (+ **KServe** optional later) | OIP-compatible |
| Vision package | **`aissemble-inference-yolo`** | YOLO family via module |
| NLP package | **`aissemble-inference-sumy`** | Summarization |
| Deploy tooling | **`aissemble-inference-deploy`** | `inference deploy init --target docker` MVP |
| Core client | **`aissemble-inference-core`** | `InferenceClient`, registry |
| Queue | **Redis** | Frame/decoupled work queue |
| DB | **TimescaleDB** (Postgres extension) | Hypertable for counts |
| Containers | **Docker**, **Docker Compose** | Single-host MVP |
| Shell runtime | **`rtk`** CLI wrapper | All shell/documented commands prefixed; see `.cursor/rules/stack-runtime.md` |
| OS / host | **Fedora** on Proxmox VM or hardened **DigitalOcean** VPS | Document both paths |
| Video | **OpenCV** (`cv2.VideoCapture`), optional **ffmpeg** tooling | HLS ingestion |

_Pin exact versions in `pyproject.toml` / lockfile when scaffolding exists._

---

## Commands

Full commands once repo layout exists; adjust paths if repo uses `src/` layout. **Every runnable line:** `rtk <argv…>`.

```bash
# Infra + app (from repo root; compose filename may differ)
rtk docker compose up -d --build

# Python env (alternative to containerized dev; use 3.12+ if `python` is <3.11)
rtk python3.12 -m venv .venv
rtk bash -lc 'source .venv/bin/activate && pip install -e ".[dev]"'

# Tests
rtk pytest tests/ -q --cov=src/city_pulse --cov-report=term-missing

# Lint / format (Ruff assumed)
rtk bash -lc 'ruff check src tests && ruff format --check src tests'

# Types (optional, if mypy configured)
rtk mypy src/city_pulse

# API dev (adjust module path after scaffold)
rtk uvicorn city_pulse.api.main:app --reload --host 0.0.0.0 --port 8000

# Streamlit
rtk streamlit run src/city_pulse/dashboard/app.py

# aissemble inference deploy scaffold (examples; cwd = model/deploy project)
rtk pip install aissemble-inference-deploy
rtk inference deploy init --target docker
# rtk inference deploy init --target kubernetes --target kserve   # later
```

_Multi-step shell state (activate venv interactively):_ use **`rtk bash -lc '…'`** so the whole snippet stays under `rtk` per stack-runtime.

_Pre-scaffold:_ only installs/Compose marked "planned"; update when Make/`uv` tooling is introduced.

---

## Project Structure

Planned layout (create during implementation):

```text
.
├── SPEC.md                          → This living spec
├── pyproject.toml                   → Dependencies, tooling
├── README.md                        → How to reproduce
├── docker-compose.yml               → Redis, TimescaleDB, MLServer, workers, Streamlit (as needed)
├── deploy/                          → Generated MLServer manifests, Docker contexts from aiSSEMBLE
│   └── yolo/
│   └── sumy/
├── src/city_pulse/                  → Application packages
│   ├── api/                         → FastAPI app (routes, lifespan)
│   ├── ingest/                      → HLS grabber, backoff, enqueue
│   ├── workers/                     → Redis consumer → MLServer → DB
│   ├── nlp_jobs/                    → Daily summarization cron entrypoints
│   ├── dashboard/                   → Streamlit
│   ├── db/                          → Migrations/schema helpers (Alembic or SQL init)
│   └── config/                      → Pydantic settings, camera YAML/JSON lists
├── tests/
│   ├── unit/                        → Pure helpers, parsers, aggregation
│   └── integration/                 → Compose services, mocked MLServer fixtures
├── scripts/                         → One-shot: seed DB, GIS camera ID lookup
└── docs/                            → Ops runbooks (Fedora, Proxmox, DO)
```

_Unused directories may appear only after PLAN/TASK split — see spec-driven-development Phase 2–3._

---

## Code Style

**Conventions**

- **`snake_case`** functions/modules; **`PascalCase`** Pydantic models; **`SCREAMING_SNAKE`** env keys.
- **Types on public functions** where practical; **`httpx`** or **`requests`** for MLServer HTTP with explicit timeouts.
- **Structured logging** (`structlog` or stdlib `logging` JSON) — include `camera_id`, `latency_ms`.

**Snippet (illustrative — not committed until Implement phase)**

```python
# src/city_pulse/workers/vision.py — pattern to follow
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class FrameBatch:
    camera_key: str
    captured_at: datetime
    payload_b64: str


def iter_vehicle_counts(
    batches: Iterator[FrameBatch],
    *,
    min_confidence: float = 0.35,
) -> Iterator[tuple[str, datetime, int]]:
    """Map queued frames → (camera_key, utc_time, vehicle_count).

    Implements MLServer call + class filter; raise domain errors on 5xx/timeouts.
    """
    ...
```

Prefer **explicit** error handling around `VideoCapture.open` retries; **never** swallow connection failures without counters.

---

## Testing Strategy


| Level              | Scope                                                                                | Framework                                        | expectation                                    |
| ------------------ | ------------------------------------------------------------------------------------ | ------------------------------------------------ | ---------------------------------------------- |
| Unit               | Parsers (m3u8 URL validation), aggregation math, config loading                      | **pytest**                                       | Cover edge cases + Golden JSON for aggregates  |
| Integration        | Redis round-trip with fakes; MLServer mocked via **responses**/**pytest-httpserver** | **pytest**                                       | Critical paths ingest → count insert           |
| E2E (optional MVP) | `docker compose` smoke: one frame path through DB row | Makefile script or pytest + **`testcontainers`** | Manual acceptable for v1 if automated is heavy |


**Coverage:** Aim **≥75%** on `city_pulse.ingest`, `workers`, `nlp_jobs`; UI can stay thin.

**Markers:** `@pytest.mark.integration` vs `@pytest.mark.slow` to keep CI default fast.

---

## Boundaries

### Always do

- Prefix **every** Shell tool / CI bash step with **`rtk`** (see stack-runtime).
- Run **`rtk pytest tests/`** (or agreed subset) before commit when Python code changes.
- **Document camera URL sources** in config or README; no undocumented feeds.
- **Validate config** at startup (Pydantic settings); fail loud on malformed `DATABASE_URL`/Redis URL.
- **Multi-arch sanity:** note `DOCKER_DEFAULT_PLATFORM` or `buildx` in README when pushing M1-built images to amd64 VPS.

### Ask first

- **DB schema migrations** altering hypertables or retention policy.
- **New runtime dependencies** (extra Python wheels, systemd units, Prometheus).
- **CI provider or workflow** layout (GitHub Actions vs none).
- **Switching topology** — full Compose on VPS vs ingestion on laptop + remote DB/YOLO.

### Never do

- Commit **`.env`** with secrets, API keys, or production DB URLs.
- Ingest **private** or unclear-license camera feeds.
- **Remove or skip failing tests** without reviewer approval — fix or `@skip` with issue link.
- **Vendor** BoozAllen marketing PDFs/marketing blobs into repo; link upstream GitHub/docs only.

---

## Success Criteria

Specific, testable “done” for MVP (maps to Prior `F1–F8`):

1. **Ingest:** One configurable MDOT `.m3u8` runs **≥1 hour** unattended; grabs frame every **≤10 s**; no unbounded Redis growth (TTL or backlog cap documented).
2. **Queue:** Frames enter Redis serialized; worker drains without blocking ingestion loop (measure ingest vs inference concurrency in README).
3. **Vision:** `vehicle_count ≥ 0` rows written per sample with **`timestamptz` + `camera_location`** aligned to Appendix schema.
4. **NLP:** Scheduled job writes **≥1 dated brief string** referencing that day’s aggregates (fixture day OK with frozen data).
5. **UI:** Streamlit shows **multi-hour trend** chart from Timescale query + displays latest brief.
6. **Deploy credible:** Dockerfile/Compose brings up Redis, TimescaleDB, **YOLO** MLServer from aiSSEMBLE deploy output; `./README` reproducible commands work on clean clone (minus optional GPU).
7. **Legal posture:** SPEC + README state **public feeds only**: MDOT pattern `https://strmr5.sha.maryland.gov/rtplive/{camera_id}/playlist.m3u8` + instruction to validate ArcGIS-backed `camera_id`.

**Stretch:** Second feed (EarthCam or Port) gated behind feature flag → not required for MVP success box-tick above.

---

## Resolved questions (recommended answers)


| Question                                 | Recommendation                                                                                                                                                                                                                                                                                                                                                                                  | Why                                                                                                           |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Compose vs split topology**            | **Single Docker Compose stack** on one machine (Fedora Proxmox VM, DO VPS, or Docker Desktop Mac). Hybrid “ingest on laptop + Redis/DB on VPS” stays **defer** until VPS cannot run OpenCV+HLS cleanly.                                                                                                                                                                                         | One network boundary, reproducible README, smallest moving parts for portfolio reviewer.                      |
| **Vehicle taxonomy**                     | **Single `vehicle_count` for MVP**: sum detections whose label ∈ `{car, truck, bus, motorcycle}` — exact id list config-driven from model labels file. Optional **stretch:** add breakdown columns after MVP when queries need commodity vs heavy split.                                                                                                                                        | Matches Appendix B schema; avoids migration churn during first demo.                                          |
| **Anomaly / “interesting day” for Sumy** | **Rules-first MVP:** roll hourly totals; narrative inputs = (1) peak hour + magnitude vs daily median hour, (2) top **3** hours by count, (3) daylight total vs nightly total wording. Use **simple z-score vs trailing 7-day same weekday mean** only once ≥**14** usable days exist; before that skip statistical language. Static absolute threshold optional env var for “heavy day” flair. | Deterministic summary text without fragile stats at low sample size; richer stats gated on data accumulation. |
| **GIS → `camera_id` for Towson / I‑695** | Maintain **`scripts/export_mdot_cameras.py`**: ArcGIS REST `query` FeatureServer layer (Md SHA traffic cams layer — pin layer URL once discovered), optional `bbox`/highway filters, emit **`deploy/cameras.towson.yaml`** checked into repo (`camera_id`, `camera_location`, `m3u8_url` built from pattern). README: “refresh quarterly.” **Fallback:** manual YAML row for pilot cam IDs. | Single reproducible curator path; survives chat context loss; human can still hand-edit YAML. |
| **Streamlit ↔ DB** | **Direct SQL** inside trusted Docker network via **`DATABASE_READONLY_URL`** (Postgres role `city_pulse_reader` — `SELECT` only). **Defer FastAPI read API** until public deploy, auth gate, or second client needs sharing the same contract. | Fastest MVP; DB not exposed publicly if firewall/compose binds localhost; upgrade path documented. |


**Reconsider** (triggers revise SPEC+PLAN): public internet exposure for dashboard → add auth + REST/BFF layer; sustained multi-camera scale → split ingest tier; stakeholder wants class mix charts → widen schema deliberately.

---

## Appendix A — Functional requirements traceability


| ID  | Requirement                                                      | Priority |
| --- | ---------------------------------------------------------------- | -------- |
| F1  | Ingest HLS from configurable URLs; **1 frame / 5–10 s**          | must     |
| F2  | Serialize frames (e.g. base64) → **Redis**                       | must     |
| F3  | Worker → MLServer (OIP) via aiSSEMBLE client → **vehicle_count** | must     |
| F4  | Persist **time**, **camera_location**, **vehicle_count**         | must     |
| F5  | Daily job → aggregates → Sumy MLServer → store brief             | must     |
| F6  | Streamlit: charts + brief                                        | must     |
| F7  | `inference deploy init` **Docker** target for MLServer           | should   |
| F8  | Configurable cameras + stable **camera_location** labels         | should   |


---

## Appendix B — Data sources & schema

### MDOT CHART

- **Catalog:** Maryland open ArcGIS traffic camera dataset.
- **Stream pattern:** `https://strmr5.sha.maryland.gov/rtplive/{camera_id}/playlist.m3u8`
- **Ingestion:** `cv2.VideoCapture(hls_url)` + retry/backoff for segment churn.

### Optional feeds

- Baltimore Inner Harbor (EarthCam) — richer scenes.
- Port of Baltimore — logistics angle if detector classes justify it.

### TimescaleDB (minimal)


| Column            | Type          |
| ----------------- | ------------- |
| `time`            | `timestamptz` |
| `camera_location` | `text`        |
| `vehicle_count`   | `integer`     |


### Redis role

Decouple capture rate from inference; optional dedup/rate-limit keys.

---

## Appendix C — Architecture overview

```text
HLS URLs → Capture → Redis queue → MLServer (YOLO) → TimescaleDB
                                              ↓
                         Daily cron → MLServer (Sumy) → Brief → Streamlit
```

**Workers:** ingestion (Python/OpenCV); vision worker; cron NLP; Streamlit frontend.

---

## Appendix D — Phased rollout (informal PLAN seed)

_Use formal Plan doc or tasks file per spec-driven-development Phases 2–3._

1. **Ingest + local sanity:** Fedora or Mac; one MDOT stream; MLServer smoke for YOLO on M1/VM.
2. **Pipeline:** Redis + Timescale via Compose; YOLO container; ingestion → inference → inserts.
3. **NLP + UI:** Sumy MLServer; daily summarization; Streamlit dashboard; README reproducibility pass.

---

## Appendix E — Non-functional reminders

- M1 builds targeting **amd64** VPS → document `docker buildx` or platform flags.
- Ingest never blocks on YOLO — Redis absorbs mismatch.
- **License:** Inference repo **`LICENSE.txt`** (Apache-2.0 migration per upstream history) overrides older marketing mentions of other licenses where different product.

---

## Spec verification checklist

_(Human signs off before heavy implementation.)_

- [ ] All six core areas present (Objective, Tech Stack, Commands, Project Structure, Code Style, Testing Strategy, Boundaries).
- [ ] Success Criteria are specific and testable.
- [ ] Boundaries (Always / Ask first / Never) defined.
- [ ] Human reviewed assumptions + resolved-question recommendations (or overridden them explicitly).

