#!/usr/bin/env bash
# Local smoke after clone: venv + install + tests + linters.
# From repo root:  rtk bash -lc 'bash scripts/verify_local.sh'
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  echo "Create a venv first, e.g.  rtk python3.12 -m venv .venv" >&2
  echo "Then:  rtk bash -lc 'source .venv/bin/activate && pip install -e .[dev]'" >&2
  exit 1
fi
rtk bash -lc "cd \"$ROOT\" && source .venv/bin/activate && pytest tests/ -q && ruff check src tests && ruff format --check src tests && mypy src/city_pulse"
echo "OK: tests + ruff + mypy"
