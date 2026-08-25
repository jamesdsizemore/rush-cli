"""Standalone detached-process entrypoint for a persisted benchmark job."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .jobs import run_job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rush-benchmark-worker")
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_job(args.job, wait_for_pid=True)


if __name__ == "__main__":
    sys.exit(main())
