"""Exponential backoff for flaky HLS streams (injectable for tests)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StreamBackoff:
    """Failures lengthen delay; call ``reset`` after a successful frame read."""

    initial_seconds: float = 1.0
    max_seconds: float = 60.0
    multiplier: float = 2.0
    consecutive_failures: int = 0

    def reset(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> float:
        """Increment failure streak and return sleep seconds before next retry."""
        sleep_s = min(
            self.initial_seconds * (self.multiplier**self.consecutive_failures),
            self.max_seconds,
        )
        self.consecutive_failures += 1
        return sleep_s
