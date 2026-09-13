"""Filesystem-safe retention helpers for downloaded Matrix media."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time


@dataclass(slots=True, frozen=True)
class CleanupResult:
    """Summary of files removed by retention or manual purge."""

    removed_files: int = 0
    removed_bytes: int = 0


def _regular_files(path: Path) -> list[tuple[Path, float, int]]:
    """Return direct regular files only; never follow symlinks or recurse."""
    try:
        entries = list(path.iterdir())
    except FileNotFoundError:
        return []
    files: list[tuple[Path, float, int]] = []
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            stat = entry.stat(follow_symlinks=False)
        except (FileNotFoundError, OSError):
            continue
        files.append((entry, stat.st_mtime, stat.st_size))
    return files


def _remove(entries: list[tuple[Path, float, int]]) -> CleanupResult:
    removed_files = 0
    removed_bytes = 0
    for path, _mtime, size in entries:
        try:
            if path.is_symlink() or not path.is_file():
                continue
            path.unlink()
        except (FileNotFoundError, OSError):
            continue
        removed_files += 1
        removed_bytes += size
    return CleanupResult(removed_files=removed_files, removed_bytes=removed_bytes)


def cleanup_media_directory(
    path: Path,
    *,
    retention_days: int,
    max_bytes: int,
    now: float | None = None,
) -> CleanupResult:
    """Apply age then size retention to direct regular files in one directory."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    current_time = time.time() if now is None else float(now)
    files = _regular_files(path)
    removed_files = 0
    removed_bytes = 0

    if retention_days > 0:
        cutoff = current_time - retention_days * 86400
        expired = [item for item in files if item[1] < cutoff]
        result = _remove(expired)
        removed_files += result.removed_files
        removed_bytes += result.removed_bytes
        expired_paths = {item[0] for item in expired}
        files = [item for item in files if item[0] not in expired_paths and item[0].exists()]

    total_bytes = sum(size for _path, _mtime, size in files)
    if total_bytes > max_bytes:
        for item in sorted(files, key=lambda value: (value[1], value[0].name)):
            if total_bytes <= max_bytes:
                break
            result = _remove([item])
            if result.removed_files:
                removed_files += result.removed_files
                removed_bytes += result.removed_bytes
                total_bytes -= item[2]

    return CleanupResult(removed_files=removed_files, removed_bytes=removed_bytes)


def purge_media_directory(path: Path) -> CleanupResult:
    """Delete all direct regular files in one incoming-media directory."""
    return _remove(_regular_files(path))
