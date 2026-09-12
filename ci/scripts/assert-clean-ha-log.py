#!/usr/bin/env python3
"""Fail CI when Matrix Extended produces known unsafe/unhandled HA log entries."""

from __future__ import annotations

from pathlib import Path
import sys


def assert_clean(text: str) -> None:
    if "Detected blocking call" in text and "matrix_extended" in text:
        raise AssertionError("Matrix Extended performed blocking I/O in Home Assistant event loop")
    if "Task exception was never retrieved" in text and "matrix_extended" in text:
        raise AssertionError("Matrix Extended leaked an unhandled background task exception")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: assert-clean-ha-log.py PATH")
    text = Path(sys.argv[1]).read_text(errors="replace")
    assert_clean(text)
    print("Matrix Extended Home Assistant log checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
