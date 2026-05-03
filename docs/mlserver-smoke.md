# MLServer / YOLO smoke checks

Stack: **MLServer** + **aissemble-inference-yolo** (see `models/yolov8/model-settings.json`). HTTP **8080**, gRPC **8081** (Compose defaults).

## Ready

```bash
rtk bash -lc "curl -sf http://127.0.0.1:8080/v2/health/ready >/dev/null && echo OK"
```

## Model metadata

```bash
rtk bash -lc "curl -s http://127.0.0.1:8080/v2/models/yolov8"
```

## Infer (tiny JPEG base64)

Replace `BASE64_JPEG` with a real base64 payload (or use a client that posts multipart).

```bash
rtk bash -lc 'curl -s -X POST http://127.0.0.1:8080/v2/models/yolov8/infer \
  -H "Content-Type: application/json" \
  -d "{\"inputs\":[{\"name\":\"input\",\"shape\":[1],\"datatype\":\"BYTES\",\"data\":[\"BASE64_JPEG\"]}]}"'
```

First cold start may download `yolov8n.pt` inside the container (**minutes** + GPU optional). Watch `docker compose logs -f yolo`.

## Regenerate Docker assets

From repo root (after `pip install aissemble-inference-deploy`):

```bash
rtk bash -lc 'source .venv/bin/activate && inference deploy init --target docker --model-dir models --output-dir deploy'
```

If the CLI errors mid-run, files may still appear under `deploy/docker/`; fix paths and image name (`city-pulse-yolo:local`) in generated compose snippets before commit.
