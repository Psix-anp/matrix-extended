#!/usr/bin/env python3
"""Patch a generated Synapse config for the disposable E2E server."""

from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import sys


def _replace_or_append(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    replacement = f"{key}: {value}"
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    suffix = "" if text.endswith("\n") else "\n"
    return text + suffix + replacement + "\n"


def patch_config(text: str, shared_secret: str) -> str:
    """Return Synapse YAML with deterministic E2E-only registration settings."""
    text = _replace_or_append(
        text,
        "registration_shared_secret",
        f'"{shared_secret}"',
    )
    text = _replace_or_append(text, "enable_registration", "false")
    return text


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: prepare-synapse.py HOMESERVER_YAML [SECRET_FILE]", file=sys.stderr)
        return 2
    config_path = Path(sys.argv[1])
    secret_path = Path(sys.argv[2]) if len(sys.argv) == 3 else Path(".ci/synapse-shared-secret")
    shared_secret = os.environ.get("MATRIX_REGISTRATION_SHARED_SECRET") or secrets.token_urlsafe(32)
    config_path.write_text(patch_config(config_path.read_text(), shared_secret))
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(shared_secret + "\n")
    secret_path.chmod(0o600)
    print(f"Synapse E2E config prepared: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
