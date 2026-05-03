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
