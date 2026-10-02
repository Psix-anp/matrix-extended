#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

COMPONENT = Path("custom_components/matrix_extended")
WIDGET_DIST = Path("widget/dist")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def _source_files(root: Path) -> dict[str, bytes]:
    component = root / COMPONENT
    if not component.is_dir():
        raise FileNotFoundError(f"missing component tree: {COMPONENT}")

    files: dict[str, bytes] = {}
    for path in sorted(component.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        files[relative.as_posix()] = path.read_bytes()
    return files


def _widget_files(root: Path) -> dict[str, bytes]:
    dist = root / WIDGET_DIST
    if not dist.is_dir():
        raise FileNotFoundError(
            "missing widget/dist; run `cd widget && npm install && npm run build` first"
        )
    files = {
        path.relative_to(dist).as_posix(): path.read_bytes()
        for path in sorted(dist.rglob("*"))
        if path.is_file()
    }
    required = {"index.html", "widget.js", "widget.css"}
    missing = sorted(required - set(files))
    if missing:
        raise ValueError(f"Widget dist is incomplete: missing={missing}")
    forbidden = [name for name in files if name.endswith((".map", ".ts")) or "node_modules/" in name]
    if forbidden:
        raise ValueError(f"Widget dist contains non-release files: {forbidden}")
    return files


def _version(root: Path) -> str:
    manifest_path = root / COMPONENT / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError(f"invalid manifest: {err}") from err

    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid manifest version: {version!r}")
    return version


def _write_archive(archive: Path, files: dict[str, bytes]) -> None:
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in files.items():
            info = ZipInfo(name, date_time=FIXED_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)


def _verify_archive(archive: Path, expected: dict[str, bytes]) -> None:
    with ZipFile(archive) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
        actual = {name: zf.read(name) for name in names}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            name for name in set(expected) & set(actual) if expected[name] != actual[name]
        )
        raise ValueError(
            "release archive does not match source tree: "
            f"missing={missing} extra={extra} changed={changed}"
        )


def verify_release(root: Path, archive: Path) -> None:
    expected = _source_files(root)
    _verify_archive(archive, expected)
    with ZipFile(archive) as zf:
        names = [name for name in zf.namelist() if not name.endswith("/")]
    if any(not name.startswith(f"{COMPONENT.as_posix()}/") for name in names):
        raise ValueError("release archive contains files outside the install tree")


def build_release(root: Path, output_dir: Path) -> Path:
    root = root.resolve()
    output_dir = output_dir.resolve()
    version = _version(root)
    source_files = _source_files(root)
    if not source_files:
        raise ValueError("component tree is empty")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"matrix_extended-ha-install-v{version}.zip"
    _write_archive(archive, source_files)
    verify_release(root, archive)
    return archive


def build_widget_release(root: Path, output_dir: Path) -> Path:
    """Build a deterministic static Widget ZIP from the tested frontend bundle."""
    root = root.resolve()
    output_dir = output_dir.resolve()
    version = _version(root)
    widget_files = _widget_files(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"matrix_extended-widget-v{version}.zip"
    _write_archive(archive, widget_files)
    _verify_archive(archive, widget_files)
    return archive


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "dist"
    ha_archive = build_release(root, output_dir)
    widget_archive = build_widget_release(root, output_dir)
    print(f"release archive: {ha_archive}")
    print(f"sha256: {_digest(ha_archive)}")
    print(f"widget archive: {widget_archive}")
    print(f"sha256: {_digest(widget_archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
