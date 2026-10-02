from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
PKG = "matrix_extended_e2ee_preflight_v060b2_testpkg"
package = types.ModuleType(PKG)
package.__path__ = [str(COMP)]
sys.modules[PKG] = package
client = importlib.import_module(f"{PKG}.client")


def test_e2ee_preflight_reports_missing_vodozemac_cleanly(monkeypatch) -> None:
    monkeypatch.setattr(client, "ENCRYPTION_ENABLED", False)
    with pytest.raises(client.MatrixEncryptionError) as err:
        client.ensure_e2ee_runtime_available()
    message = str(err.value)
    assert "E2EE dependencies are unavailable" in message
    assert "vodozemac" in message
    assert "ImportWarning" not in message


def test_e2ee_preflight_is_noop_when_runtime_is_available(monkeypatch) -> None:
    monkeypatch.setattr(client, "ENCRYPTION_ENABLED", True)
    client.ensure_e2ee_runtime_available()
