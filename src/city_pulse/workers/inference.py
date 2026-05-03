"""MLServer OIP infer + aissemble YOLO output parsing."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np

from city_pulse.oip import infer_url as infer_url_for

__all__ = [
    "annotate_frame_b64",
    "count_vehicle_detections",
    "infer_url_for",
    "infer_vehicle_count",
    "parse_bboxes",
    "parse_infer_outputs",
    "vehicle_label_allowlist",
]


def vehicle_label_allowlist(csv: str) -> set[str]:
    return {x.strip().lower() for x in csv.split(",") if x.strip()}


def count_vehicle_detections(
    labels: list[str],
    scores: list[float],
    *,
    allowed: set[str],
    min_confidence: float,
) -> int:
    """Count detections whose label is allowed and score meets threshold."""
    n = 0
    for i, lab in enumerate(labels):
        if lab.lower() not in allowed:
            continue
        score = scores[i] if i < len(scores) else 1.0
        if score >= min_confidence:
            n += 1
    return n


def parse_infer_outputs(body: dict[str, Any]) -> tuple[list[str], list[float]]:
    """Extract parallel ``labels`` + ``scores`` lists from MLServer JSON infer body."""
    outputs = body.get("outputs", [])
    labels_out = next((o for o in outputs if o.get("name") == "labels"), None)
    scores_out = next((o for o in outputs if o.get("name") == "scores"), None)
    raw_labels: list[Any] = []
    raw_scores: list[Any] = []
    if labels_out and isinstance(labels_out.get("data"), list):
        raw_labels = labels_out["data"]
    if scores_out and isinstance(scores_out.get("data"), list):
        raw_scores = scores_out["data"]

    labels: list[str] = [str(x) for x in raw_labels]
    scores: list[float] = []
    for x in raw_scores:
        try:
            scores.append(float(x))
        except (TypeError, ValueError):
            scores.append(0.0)
    return labels, scores


def parse_bboxes(body: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """Extract 4-tuples ``(x1, y1, x2, y2)`` if model returns bbox-like output."""
    outputs = body.get("outputs", [])
    box_out = next(
        (
            o
            for o in outputs
            if str(o.get("name", "")).lower() in {"boxes", "bboxes", "xyxy"}
        ),
        None,
    )
    if not box_out or not isinstance(box_out.get("data"), list):
        return []
    raw = box_out["data"]
    bboxes: list[tuple[float, float, float, float]] = []
    # Common case: [[x1,y1,x2,y2], ...]
    if raw and isinstance(raw[0], list):
        for item in raw:
            if not isinstance(item, list) or len(item) < 4:
                continue
            try:
                bboxes.append(
                    (float(item[0]), float(item[1]), float(item[2]), float(item[3]))
                )
            except (TypeError, ValueError):
                continue
        return bboxes

    # Flattened case: [x1,y1,x2,y2,...]
    for i in range(0, len(raw) - 3, 4):
        try:
            bboxes.append(
                (
                    float(raw[i]),
                    float(raw[i + 1]),
                    float(raw[i + 2]),
                    float(raw[i + 3]),
                )
            )
        except (TypeError, ValueError):
            continue
    return bboxes


def annotate_frame_b64(
    *,
    frame_b64: str,
    labels: list[str],
    scores: list[float],
    bboxes: list[tuple[float, float, float, float]],
    min_confidence: float,
    allowed: set[str],
) -> str | None:
    """Draw green YOLO boxes on a JPEG payload and return base64 JPEG."""
    if not frame_b64:
        return None
    try:
        import cv2

        img_raw = base64.b64decode(frame_b64)
        np_buf = np.frombuffer(img_raw, dtype=np.uint8)
        frame = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        h, w = frame.shape[:2]
        n = min(len(labels), len(scores), len(bboxes))
        for i in range(n):
            label = labels[i].lower()
            score = scores[i]
            if label not in allowed or score < min_confidence:
                continue
            x1f, y1f, x2f, y2f = bboxes[i]
            x1 = max(0, min(w - 1, int(round(x1f))))
            y1 = max(0, min(h - 1, int(round(y1f))))
            x2 = max(0, min(w - 1, int(round(x2f))))
            y2 = max(0, min(h - 1, int(round(y2f))))
            if x2 <= x1 or y2 <= y1:
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), (64, 255, 64), 2)
            text = f"{labels[i]} {score:.2f}"
            cv2.putText(
                frame,
                text,
                (x1, max(0, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (64, 255, 64),
                1,
                cv2.LINE_AA,
            )
        ok, out_buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok or out_buf is None:
            return None
        return base64.standard_b64encode(out_buf.tobytes()).decode("ascii")
    except Exception:
        return None


def infer_vehicle_count(
    client: httpx.Client,
    *,
    infer_url: str,
    frame_b64: str,
) -> dict[str, Any]:
    """POST one JPEG (base64) to MLServer; returns parsed payload + timing metadata."""
    payload = {
        "inputs": [
            {
                "name": "image",
                "shape": [1],
                "datatype": "BYTES",
                "data": [frame_b64],
            }
        ]
    }
    t0 = datetime.now(UTC)
    resp = client.post(infer_url, json=payload)
    latency_ms = (datetime.now(UTC) - t0).total_seconds() * 1000.0
    resp.raise_for_status()
    body = resp.json()
    labels, scores = parse_infer_outputs(body)
    return {
        "body": body,
        "labels": labels,
        "scores": scores,
        "latency_ms": latency_ms,
    }
