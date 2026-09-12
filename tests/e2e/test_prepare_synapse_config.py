from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "prepare-synapse.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_synapse", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_patch_config_replaces_existing_secret_and_disables_registration():
    module = _load_module()
    original = "server_name: matrix.test\nregistration_shared_secret: old\nenable_registration: true\n"
    patched = module.patch_config(original, "new-secret")
    assert patched.count("registration_shared_secret:") == 1
    assert 'registration_shared_secret: "new-secret"' in patched
    assert patched.count("enable_registration:") == 1
    assert "enable_registration: false" in patched


def test_patch_config_adds_missing_settings():
    module = _load_module()
    patched = module.patch_config("server_name: matrix.test\n", "secret")
    assert 'registration_shared_secret: "secret"' in patched
    assert "enable_registration: false" in patched
