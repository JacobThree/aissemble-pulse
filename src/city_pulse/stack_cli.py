"""CLI entrypoint: run ``scripts/run_local_stack.sh`` from any cwd."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "run_local_stack.sh"
    if not script.is_file():
        sys.stderr.write(f"Missing {script}\n")
        raise SystemExit(1)
    raise SystemExit(subprocess.call(["bash", str(script)], cwd=str(repo)))


if __name__ == "__main__":
    main()
