#!/usr/bin/env bash
# Run ingest + vision worker + Streamlit in one terminal (foreground UI).
# Requires: Docker (redis, timescaledb, yolo), .venv, pip install -e ".[dev]"
#
# One shot (starts Compose + preflight + workers + dashboard):
#   rtk bash scripts/run_local_stack.sh
#
# Skip bringing Compose up (already running):
#   SKIP_STACK_INFRA=1 rtk bash scripts/run_local_stack.sh
#
# Legacy (still supported): RUN_STACK_INFRA=0 disables auto Compose like SKIP_STACK_INFRA=1

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

start_infra=1
if [[ "${SKIP_STACK_INFRA:-}" == "1" ]]; then
  start_infra=0
elif [[ "${RUN_STACK_INFRA:-}" == "0" ]]; then
  start_infra=0
fi

if [[ "$start_infra" -eq 1 ]]; then
  echo "Starting Docker services (redis, timescaledb, yolo) — first YOLO boot can take a few minutes."
  rtk docker compose up -d redis timescaledb yolo
fi

if [[ ! -d .venv ]]; then
  echo "Missing .venv — run: rtk python3.12 -m venv .venv && rtk bash -lc 'source .venv/bin/activate && pip install -e \"[.]dev\"'" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${ROOT}/.venv/bin/activate"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

echo "Running preflight (Redis, Postgres, YOLO readiness)…"
rtk python "${ROOT}/scripts/preflight_stack.py" || exit "$?"

mkdir -p "${ROOT}/logs"

PIDS=()
cleanup() {
  local p
  for p in "${PIDS[@]:-}"; do
    if kill -0 "$p" 2>/dev/null; then
      kill "$p" 2>/dev/null || true
      wait "$p" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM HUP

city-pulse-ingest >> "${ROOT}/logs/ingest.log" 2>&1 &
PIDS+=("$!")
city-pulse-vision-worker >> "${ROOT}/logs/vision.log" 2>&1 &
PIDS+=("$!")

echo ""
echo "city-pulse-ingest pid=${PIDS[0]}  → logs/ingest.log"
echo "city-pulse-vision-worker pid=${PIDS[1]}  → logs/vision.log"
echo "If the chart is flat: tail -f logs/ingest.log logs/vision.log"
echo "Starting Streamlit — open the printed URL (usually http://localhost:8501)."
echo "Ctrl+C stops ingest, vision worker, and Streamlit."
echo ""

streamlit run "${ROOT}/src/city_pulse/dashboard/app.py"
