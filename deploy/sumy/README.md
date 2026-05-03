# Sumy MLServer (aiSSEMBLE)

Text summarization via **`aissemble-inference-sumy`** and MLServer. Model config: `models/sumy/model-settings.json`.

Build (from repo root):

```bash
rtk docker compose build sumy
rtk docker compose up -d sumy
rtk bash -lc 'curl -sf http://127.0.0.1:8090/v2/health/ready && echo OK'
```

HTTP is mapped to host **8090** (gRPC **8091**) so the YOLO service can keep **8080/8081**. Set **`SUMY_ENDPOINT=http://localhost:8090`** for the daily brief job.

Regenerate this Dockerfile from the deploy CLI when iterating (optional):

```bash
rtk bash -lc 'source .venv/bin/activate && pip install -e ".[aissemble]" && inference deploy init --target docker --model-dir models --output-dir deploy'
```

(If the generator overwrites paths, keep this `deploy/sumy/Dockerfile` as the source of truth for the dedicated Sumy service.)
