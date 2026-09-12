from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).parents[2]
BUILDER = ROOT / "ci" / "scripts" / "build-release.py"
COMPONENT = Path("custom_components/matrix_extended")


def load_builder():
    assert BUILDER.exists(), "release builder is not implemented"
    spec = importlib.util.spec_from_file_location("matrix_extended_release_builder", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "custom_components", repo / "custom_components")
    return repo


def test_release_archive_contains_only_install_tree_and_matches_source(tmp_path: Path) -> None:
    mod = load_builder()
    repo = make_repo(tmp_path)
    output_dir = tmp_path / "dist"

    archive = mod.build_release(repo, output_dir)

    manifest = json.loads((repo / COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert archive.name == f"matrix_extended-ha-install-v{manifest['version']}.zip"

    source_files = {
        path.relative_to(repo).as_posix(): path.read_bytes()
        for path in (repo / COMPONENT).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }
    with ZipFile(archive) as zf:
        archive_files = {name: zf.read(name) for name in zf.namelist() if not name.endswith("/")}

    assert archive_files == source_files
    assert all(name.startswith("custom_components/matrix_extended/") for name in archive_files)
    assert not any("__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in archive_files)


def test_release_builder_rejects_missing_or_invalid_manifest_version(tmp_path: Path) -> None:
    mod = load_builder()
    repo = make_repo(tmp_path)
    manifest_path = repo / COMPONENT / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        mod.build_release(repo, tmp_path / "dist")
    except ValueError as err:
        assert "version" in str(err).lower()
    else:
        raise AssertionError("invalid manifest version must be rejected")
