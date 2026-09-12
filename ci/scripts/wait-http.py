#!/usr/bin/env python3
"""Wait for an HTTP endpoint to become ready with a bounded timeout."""

from __future__ import annotations

import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def wait(url: str, timeout: float = 60.0, interval: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= response.status < 500:
                    return
        except (HTTPError, URLError, OSError) as err:
            last_error = err
        time.sleep(interval)
    raise TimeoutError(f"endpoint did not become ready: {url}; last_error={type(last_error).__name__ if last_error else 'none'}")


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: wait-http.py URL [TIMEOUT_SECONDS]", file=sys.stderr)
        return 2
    wait(sys.argv[1], float(sys.argv[2]) if len(sys.argv) == 3 else 60.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
