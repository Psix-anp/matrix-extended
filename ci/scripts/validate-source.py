#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

EXPECTED_VERSION = "0.5.2"
COMPONENT = Path("custom_components/matrix_extended")
REQUIRED = {
    "__init__.py",
    "manifest.json",
    "config_flow.py",
    "client.py",
    "receiver.py",
    "media.py",
    "notify.py",
    "services.yaml",
    "strings.json",
    "translations/en.json",
    "translations/ru.json",
}
FORBIDDEN_DIRS = {"__pycache__", ".pytest_cache"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_FILES = {
    "mutation-results.json",
    "mutation-client-results.json",
    "mutation-media-results.json",
}


def validate_repository(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    component = root / COMPONENT

    for relative in sorted(REQUIRED):
        if not (component / relative).is_file():
            errors.append(f"missing required file: {COMPONENT / relative}")

    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            errors.append(f"forbidden generated artifact: {relative}")
            continue
        if path.is_file() and (path.suffix in FORBIDDEN_SUFFIXES or path.name in FORBIDDEN_FILES):
            errors.append(f"forbidden generated artifact: {relative}")

    json_paths = [
        component / "manifest.json",
        component / "strings.json",
        *(sorted((component / "translations").glob("*.json")) if (component / "translations").is_dir() else []),
        root / "hacs.json",
    ]
    parsed: dict[Path, object] = {}
    for path in json_paths:
        if not path.is_file():
            continue
        try:
            parsed[path] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            errors.append(f"invalid JSON: {path.relative_to(root)}: {err}")

    manifest_path = component / "manifest.json"
    manifest = parsed.get(manifest_path)
    if isinstance(manifest, dict) and manifest.get("version") != EXPECTED_VERSION:
        errors.append(
            f"manifest version must be {EXPECTED_VERSION}, got {manifest.get('version')!r}"
        )

    return errors


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    errors = validate_repository(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"source validation ok: Matrix Extended {EXPECTED_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
