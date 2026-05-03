"""CLI for scheduled NLP jobs."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta

from city_pulse.config import get_settings
from city_pulse.nlp_jobs.daily_brief import run_daily_brief_for_day


def _default_report_day() -> date:
    """Yesterday in UTC (typical cron: summarize the completed day)."""
    today_utc = datetime.now(UTC).date()
    return today_utc - timedelta(days=1)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Generate daily traffic brief (Sumy).")
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        default=None,
        help="UTC calendar day (YYYY-MM-DD). Default: yesterday UTC.",
    )
    args = parser.parse_args()
    report_day = args.day or _default_report_day()
    settings = get_settings()
    try:
        body = run_daily_brief_for_day(settings, report_day=report_day)
    except Exception as exc:
        sys.stderr.write(f"daily brief failed: {exc}\n")
        raise SystemExit(1) from exc
    sys.stdout.write(body)
    if not body.endswith("\n"):
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
