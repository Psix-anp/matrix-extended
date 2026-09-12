from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "ha-reconnect.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ha_reconnect", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_find_matrix_state_filters_domain_and_matrix_friendly_name():
    module = _load_module()
    states = [
        {
            "entity_id": "binary_sensor.router_connection",
            "state": "on",
            "attributes": {"friendly_name": "Router Connection"},
        },
        {
            "entity_id": "sensor.matrix_bot_connection",
            "state": "wrong-domain",
            "attributes": {"friendly_name": "Matrix bot Connection"},
        },
        {
            "entity_id": "binary_sensor.matrix_bot_connection",
            "state": "off",
            "attributes": {"friendly_name": "Matrix @ha_bot:matrix.test Connection"},
        },
    ]
    state = module.find_matrix_state(
        states,
        entity_domain="binary_sensor",
        friendly_suffix="Connection",
    )
    assert state["state"] == "off"


def test_find_matrix_state_raises_when_missing():
    module = _load_module()
    with pytest.raises(LookupError, match="Last incoming event"):
        module.find_matrix_state(
            [],
            entity_domain="sensor",
            friendly_suffix="Last incoming event",
        )
