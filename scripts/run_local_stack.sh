#!/usr/bin/env bash
# Run ingest + vision worker + Streamlit in one terminal (foreground UI).
# Requires: Docker infra already up (redis, timescaledb, yolo), .venv, pip install -e ".[dev]"
#
#   rtk bash scripts/run_local_stack.sh
#
# Optional: start Compose services first —
#   RUN_STACK_INFRA=1 rtk bash scripts/run_local_stack.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${RUN_STACK_INFRA:-}" == "1" ]]; then
  echo "Starting Docker services (redis, timescaledb, yolo)..."
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

city-pulse-ingest &
PIDS+=("$!")
city-pulse-vision-worker &
PIDS+=("$!")

echo ""
echo "city-pulse-ingest pid=${PIDS[0]}  city-pulse-vision-worker pid=${PIDS[1]}"
echo "Starting Streamlit — open the printed URL (usually http://localhost:8501)."
echo "Ctrl+C stops ingest, vision worker, and Streamlit."
echo ""

streamlit run "${ROOT}/src/city_pulse/dashboard/app.py"
