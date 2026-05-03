"""Opt-in smoke against a running MLServer YOLO container."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

_READY_URL = "http://127.0.0.1:8080/v2/health/ready"


@pytest.mark.integration
def test_mlserver_ready_returns_200() -> None:
    try:
        with urllib.request.urlopen(_READY_URL, timeout=5) as resp:
            assert resp.status == 200
    except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
        pytest.skip(
            f"MLServer not up — start with: rtk docker compose up -d yolo ({exc})",
        )
