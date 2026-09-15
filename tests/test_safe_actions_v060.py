from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
SAFE_ACTIONS = ROOT / "custom_components" / "matrix_extended" / "safe_actions.py"


def load_safe_actions():
    assert SAFE_ACTIONS.exists(), "safe_actions.py is not implemented yet"
    spec = importlib.util.spec_from_file_location(
        "matrix_extended_safe_actions_v060_test", SAFE_ACTIONS
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_service_handler_rejects_invalid_service() -> None:
    mod = load_safe_actions()
    with pytest.raises(ValueError, match="domain.service"):
        mod.parse_service_handler({"service": "broken"})


def test_safe_action_keeps_preconfigured_payload() -> None:
    mod = load_safe_actions()
    action = mod.SafeActionDefinition(
        id="garage.open",
        handler=mod.ServiceActionHandler(
            service="cover.open_cover",
            target={"entity_id": "cover.garage"},
            data={},
        ),
        confirmation_required=True,
    )

    assert action.id == "garage.open"
    assert action.handler.service == "cover.open_cover"
    assert action.handler.target == {"entity_id": "cover.garage"}
    assert action.handler.data == {}
    assert action.confirmation_required is True


def test_parse_service_handler_copies_json_safe_mappings() -> None:
    mod = load_safe_actions()
    target = {"entity_id": "light.garage"}
    data = {"brightness_pct": 50}

    handler = mod.parse_service_handler(
        {
            "service": "light.turn_on",
            "target": target,
            "data": data,
        }
    )
    target["entity_id"] = "light.changed"
    data["brightness_pct"] = 1

    assert handler.target == {"entity_id": "light.garage"}
    assert handler.data == {"brightness_pct": 50}


def test_service_action_dump_is_stable_and_json_safe() -> None:
    mod = load_safe_actions()
    action = mod.SafeActionDefinition(
        id="garage.light",
        handler=mod.ServiceActionHandler(
            service="light.toggle",
            target={"entity_id": "light.garage"},
            data={},
        ),
        confirmation_required=False,
    )

    assert mod.dump_safe_action(action) == {
        "id": "garage.light",
        "confirmation_required": False,
        "handler": {
            "type": "service",
            "service": "light.toggle",
            "target": {"entity_id": "light.garage"},
            "data": {},
        },
    }
