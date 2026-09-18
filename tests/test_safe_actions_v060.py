from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
SAFE_ACTIONS = COMP / "safe_actions.py"
SAFE_ACTION_EXECUTOR = COMP / "safe_action_executor.py"


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


def load_safe_action_executor():
    assert SAFE_ACTION_EXECUTOR.exists(), "safe_action_executor.py is not implemented yet"
    pkg_name = "matrix_extended_safe_action_executor_v060_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    actions_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.safe_actions", SAFE_ACTIONS
    )
    assert actions_spec and actions_spec.loader
    actions = importlib.util.module_from_spec(actions_spec)
    sys.modules[actions_spec.name] = actions
    actions_spec.loader.exec_module(actions)

    executor_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.safe_action_executor", SAFE_ACTION_EXECUTOR
    )
    assert executor_spec and executor_spec.loader
    executor = importlib.util.module_from_spec(executor_spec)
    sys.modules[executor_spec.name] = executor
    executor_spec.loader.exec_module(executor)
    return executor, actions


class FakeServices:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error

    async def async_call(self, domain, service, data, *, blocking, target):
        self.calls.append((domain, service, data, blocking, target))
        if self.error is not None:
            raise self.error


class FakeHass:
    def __init__(self, error: Exception | None = None) -> None:
        self.services = FakeServices(error)


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


@pytest.mark.asyncio
async def test_safe_action_executor_calls_only_stored_service_payload() -> None:
    executor_mod, actions = load_safe_action_executor()
    hass = FakeHass()
    action = actions.SafeActionDefinition(
        id="garage.open",
        handler=actions.ServiceActionHandler(
            service="cover.open_cover",
            target={"entity_id": "cover.garage"},
            data={},
        ),
    )

    result = await executor_mod.SafeActionExecutor(hass).async_execute(action)

    assert result == executor_mod.SafeActionExecutionResult(
        action_id="garage.open",
        status="success",
        handler_type="service",
        error=None,
    )
    assert hass.services.calls == [
        ("cover", "open_cover", {}, True, {"entity_id": "cover.garage"})
    ]


@pytest.mark.asyncio
async def test_safe_action_executor_redacts_and_bounds_errors() -> None:
    executor_mod, actions = load_safe_action_executor()
    hass = FakeHass(RuntimeError("token=abc123 " + "x" * 500))
    action = actions.SafeActionDefinition(
        id="garage.open",
        handler=actions.ServiceActionHandler(
            service="cover.open_cover",
            target={"entity_id": "cover.garage"},
            data={},
        ),
    )

    result = await executor_mod.SafeActionExecutor(hass).async_execute(action)

    assert result.status == "failed"
    assert result.error is not None
    assert "abc123" not in result.error
    assert "token=<redacted>" in result.error
    assert len(result.error) <= 200
