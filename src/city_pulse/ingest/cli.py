"""CLI entry for long-running ingest."""

from __future__ import annotations

import logging
import sys

import redis

from city_pulse.config import get_settings
from city_pulse.ingest.capture import run_ingest_loop
from city_pulse.ingest.metrics import IngestMetrics


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    if not settings.ingest_m3u8_url:
        sys.stderr.write(
            "Set INGEST_M3U8_URL (or ingest_m3u8_url) to an HLS playlist URL.\n",
        )
        sys.exit(1)

    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    metrics = IngestMetrics()
    run_ingest_loop(settings=settings, redis_client=client, metrics=metrics)


if __name__ == "__main__":
    main()
