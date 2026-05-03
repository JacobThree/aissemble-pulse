# YOLO deployment (aiSSEMBLE Inference)

MLServer image build + Compose wiring live in **[`../docker/`](../docker/)** (from `inference deploy init --target docker`).

- **Model config:** [`../../models/yolov8/model-settings.json`](../../models/yolov8/model-settings.json)
- **Upstream example:** [aissemble-object-detection-example](https://github.com/boozallen/aissemble-inference/tree/dev/aissemble-inference-examples/aissemble-object-detection-example)

Bring up with root Compose:

```bash
rtk docker compose up -d yolo
```

Smoke HTTP checks: [`../../docs/mlserver-smoke.md`](../../docs/mlserver-smoke.md).
