"""MLServer OIP infer + aissemble YOLO output parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from city_pulse.oip import infer_url as infer_url_for

__all__ = [
    "count_vehicle_detections",
    "infer_url_for",
    "infer_vehicle_count",
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
