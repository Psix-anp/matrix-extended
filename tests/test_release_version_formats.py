import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", ["build-release.py", "validate-source.py"])
@pytest.mark.parametrize("version, valid", [
    ("0.5.10", True), ("0.5.10b1", True), ("0.5.10a1", True),
    ("0.5.10rc2", True), ("0.5.10b", False), ("0.5.10-beta1", False),
])
def test_release_version_formats(script: str, version: str, valid: bool) -> None:
    spec = importlib.util.spec_from_file_location("version_check", ROOT / "ci" / "scripts" / script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert bool(module.VERSION_RE.fullmatch(version)) is valid
