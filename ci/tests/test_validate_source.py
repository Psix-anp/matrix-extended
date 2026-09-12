from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).parents[2]
VALIDATOR = ROOT / "ci" / "scripts" / "validate-source.py"


def load_validator():
    assert VALIDATOR.exists(), "source validator is not implemented"
    spec = importlib.util.spec_from_file_location("matrix_extended_source_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT / "custom_components",
        repo / "custom_components",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    (repo / "tests").mkdir()
    (repo / "README.md").write_text("# Matrix Extended\n", encoding="utf-8")
    (repo / "hacs.json").write_text('{"name":"Matrix Extended"}\n', encoding="utf-8")
    return repo


def test_clean_repository_passes(tmp_path: Path) -> None:
    mod = load_validator()
    repo = make_repo(tmp_path)
    assert mod.validate_repository(repo) == []


def test_forbidden_generated_artifact_is_rejected(tmp_path: Path) -> None:
    mod = load_validator()
    repo = make_repo(tmp_path)
    bad = repo / "custom_components" / "matrix_extended" / "__pycache__"
    bad.mkdir(exist_ok=True)
    (bad / "client.pyc").write_bytes(b"junk")
    errors = mod.validate_repository(repo)
    assert any("forbidden generated artifact" in error for error in errors)


def test_missing_required_runtime_file_is_rejected(tmp_path: Path) -> None:
    mod = load_validator()
    repo = make_repo(tmp_path)
    (repo / "custom_components" / "matrix_extended" / "receiver.py").unlink()
    errors = mod.validate_repository(repo)
    assert any("missing required file" in error and "receiver.py" in error for error in errors)


def test_wrong_manifest_version_is_rejected(tmp_path: Path) -> None:
    mod = load_validator()
    repo = make_repo(tmp_path)
    manifest_path = repo / "custom_components" / "matrix_extended" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = "9.9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = mod.validate_repository(repo)
    assert any("manifest version must be 0.4.1" in error for error in errors)


def test_invalid_translation_json_is_rejected(tmp_path: Path) -> None:
    mod = load_validator()
    repo = make_repo(tmp_path)
    (repo / "custom_components" / "matrix_extended" / "translations" / "ru.json").write_text(
        "{invalid", encoding="utf-8"
    )
    errors = mod.validate_repository(repo)
    assert any("invalid JSON" in error and "ru.json" in error for error in errors)
