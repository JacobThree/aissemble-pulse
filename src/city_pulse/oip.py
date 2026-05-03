"""MLServer Open Inference Protocol (OIP) HTTP URL helpers."""

from __future__ import annotations


def infer_url(base: str, model_name: str) -> str:
    """``{base}/v2/models/{model_name}/infer`` (no trailing slash on base)."""
    root = base.rstrip("/")
    return f"{root}/v2/models/{model_name}/infer"
