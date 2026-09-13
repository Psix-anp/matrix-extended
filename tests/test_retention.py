from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "retention.py"


def load():
    assert PATH.exists(), "retention.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_retention", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_file(path: Path, data: bytes, *, mtime: float) -> None:
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))


def test_cleanup_removes_files_older_than_retention_window(tmp_path: Path) -> None:
    mod = load()
    now = 1_000_000.0
    old = tmp_path / "old.bin"
    fresh = tmp_path / "fresh.bin"
    write_file(old, b"old", mtime=now - 8 * 86400)
    write_file(fresh, b"fresh", mtime=now - 2 * 86400)

    result = mod.cleanup_media_directory(
        tmp_path,
        retention_days=7,
        max_bytes=1024,
        now=now,
    )

    assert result.removed_files == 1
    assert result.removed_bytes == 3
    assert not old.exists()
    assert fresh.exists()


def test_zero_retention_days_disables_age_cleanup(tmp_path: Path) -> None:
    mod = load()
    now = 1_000_000.0
    old = tmp_path / "old.bin"
    write_file(old, b"abc", mtime=now - 100 * 86400)

    result = mod.cleanup_media_directory(
        tmp_path,
        retention_days=0,
        max_bytes=1024,
        now=now,
    )

    assert result.removed_files == 0
    assert old.exists()


def test_quota_cleanup_removes_oldest_remaining_files_first(tmp_path: Path) -> None:
    mod = load()
    now = 1_000_000.0
    oldest = tmp_path / "a.bin"
    middle = tmp_path / "b.bin"
    newest = tmp_path / "c.bin"
    write_file(oldest, b"aaaa", mtime=now - 30)
    write_file(middle, b"bbbb", mtime=now - 20)
    write_file(newest, b"cccc", mtime=now - 10)

    result = mod.cleanup_media_directory(
        tmp_path,
        retention_days=0,
        max_bytes=8,
        now=now,
    )

    assert result.removed_files == 1
    assert result.removed_bytes == 4
    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()


def test_cleanup_skips_directories_and_symlinks(tmp_path: Path) -> None:
    mod = load()
    now = 1_000_000.0
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"outside")
    link = tmp_path / "link.bin"
    link.symlink_to(outside)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.bin").write_bytes(b"inside")

    result = mod.cleanup_media_directory(
        tmp_path,
        retention_days=0,
        max_bytes=0,
        now=now,
    )

    assert result.removed_files == 0
    assert link.is_symlink()
    assert outside.exists()
    assert (nested / "inside.bin").exists()


def test_purge_removes_only_regular_files_and_reports_counts(tmp_path: Path) -> None:
    mod = load()
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"abc")
    b.write_bytes(b"12345")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "keep.bin").write_bytes(b"keep")
    outside = tmp_path.parent / "outside-purge.bin"
    outside.write_bytes(b"outside")
    (tmp_path / "outside-link").symlink_to(outside)

    result = mod.purge_media_directory(tmp_path)

    assert result.removed_files == 2
    assert result.removed_bytes == 8
    assert not a.exists()
    assert not b.exists()
    assert (nested / "keep.bin").exists()
    assert outside.exists()


def test_missing_directory_is_safe_for_cleanup_and_purge(tmp_path: Path) -> None:
    mod = load()
    missing = tmp_path / "missing"
    cleanup = mod.cleanup_media_directory(
        missing,
        retention_days=7,
        max_bytes=1024,
        now=1_000_000.0,
    )
    purge = mod.purge_media_directory(missing)
    assert cleanup.removed_files == cleanup.removed_bytes == 0
    assert purge.removed_files == purge.removed_bytes == 0
