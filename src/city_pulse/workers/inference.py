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
    "bbox_iou",
    "count_vehicle_detections_advanced",
    "count_vehicle_detections",
    "infer_url_for",
    "infer_vehicle_count",
    "parse_norm_roi",
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


def parse_norm_roi(raw: str | None) -> tuple[float, float, float, float] | None:
    """Parse ROI string ``x1,y1,x2,y2`` normalized in [0,1]."""
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (
            float(parts[0]),
            float(parts[1]),
            float(parts[2]),
            float(parts[3]),
        )
    except ValueError:
        return None
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return None
    return (x1, y1, x2, y2)


def bbox_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Compute IoU for two ``xyxy`` boxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    denom = area_a + area_b - inter
    if denom <= 0:
        return 0.0
    return inter / denom


def count_vehicle_detections_advanced(
    *,
    labels: list[str],
    scores: list[float],
    bboxes: list[tuple[float, float, float, float]],
    allowed: set[str],
    min_confidence: float,
    frame_width: int | None = None,
    frame_height: int | None = None,
    roi_norm: tuple[float, float, float, float] | None = None,
    dedup_recent: (
        list[tuple[str, tuple[float, float, float, float], datetime]] | None
    ) = None,
    dedup_iou_threshold: float = 0.6,
    dedup_ttl_seconds: float = 2.0,
    now_utc: datetime | None = None,
) -> tuple[int, list[tuple[str, tuple[float, float, float, float], datetime]]]:
    """Count detections with optional ROI filter and temporal de-dup."""
    now = now_utc or datetime.now(UTC)
    recent = dedup_recent or []
    if roi_norm and frame_width and frame_height:
        rx1 = roi_norm[0] * frame_width
        ry1 = roi_norm[1] * frame_height
        rx2 = roi_norm[2] * frame_width
        ry2 = roi_norm[3] * frame_height
    else:
        rx1 = ry1 = rx2 = ry2 = None

    kept_recent: list[tuple[str, tuple[float, float, float, float], datetime]] = []
    for lab, bb, ts in recent:
        if (now - ts).total_seconds() <= dedup_ttl_seconds:
            kept_recent.append((lab, bb, ts))
    recent = kept_recent

    n = min(len(labels), len(scores), len(bboxes))
    count = 0
    for i in range(n):
        lab = labels[i].lower()
        score = scores[i]
        if lab not in allowed or score < min_confidence:
            continue
        bb = bboxes[i]
        if rx1 is not None:
            cx = (bb[0] + bb[2]) / 2.0
            cy = (bb[1] + bb[3]) / 2.0
            if not (rx1 <= cx <= rx2 and ry1 <= cy <= ry2):
                continue
        is_dup = False
        for old_lab, old_bb, _ in recent:
            if old_lab != lab:
                continue
            if bbox_iou(bb, old_bb) >= dedup_iou_threshold:
                is_dup = True
                break
        if is_dup:
            continue
        count += 1
        recent.append((lab, bb, now))
    return count, recent


def annotate_frame_b64(
    *,
    frame_b64: str,
    labels: list[str],
    scores: list[float],
    bboxes: list[tuple[float, float, float, float]],
    min_confidence: float,
    allowed: set[str],
    roi_norm: tuple[float, float, float, float] | None = None,
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
        if roi_norm:
            rx1 = int(round(roi_norm[0] * w))
            ry1 = int(round(roi_norm[1] * h))
            rx2 = int(round(roi_norm[2] * w))
            ry2 = int(round(roi_norm[3] * h))
            cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (255, 80, 80), 2)
            cv2.putText(
                frame,
                "ROI",
                (rx1, max(0, ry1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 80, 80),
                2,
                cv2.LINE_AA,
            )
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
