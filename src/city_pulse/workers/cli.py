"""CLI for vision worker."""

from __future__ import annotations

import logging
import sys

from city_pulse.config import get_settings
from city_pulse.workers.vision_worker import run_forever


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run_forever(get_settings())
    except KeyboardInterrupt:
        sys.stderr.write("Stopping vision worker.\n")


if __name__ == "__main__":
    main()
