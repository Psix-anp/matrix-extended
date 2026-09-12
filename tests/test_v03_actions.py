from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "actions.py"


def load():
    assert PATH.exists(), "actions.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_actions", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reaction_action_registry_is_one_shot() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(max_entries=4)
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {
                "reaction": "💡",
                "service": "light.turn_on",
                "target": {"entity_id": "light.gate"},
                "data": {"brightness_pct": 50},
            }
        ],
    )
    action = registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="💡",
    )
    assert action.service == "light.turn_on"
    assert action.target == {"entity_id": "light.gate"}
    assert action.data == {"brightness_pct": 50}
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="💡",
    ) is None


def test_registry_rejects_bad_service_name() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry()
    with pytest.raises(ValueError, match="domain.service"):
        registry.register(
            room_id="!room:example",
            event_id="$message",
            actions=[{"reaction": "X", "service": "not-a-service"}],
        )


def test_registry_caps_old_entries() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(max_entries=2)
    for i in range(3):
        registry.register(
            room_id="!room:example",
            event_id=f"${i}",
            actions=[{"reaction": "✅", "service": "light.turn_on"}],
        )
    assert registry.consume(room_id="!room:example", event_id="$0", reaction="✅") is None
    assert registry.consume(room_id="!room:example", event_id="$2", reaction="✅") is not None


def test_registry_max_entries_boundary_accepts_one_and_rejects_zero() -> None:
    mod = load()
    mod.ReactionActionRegistry(max_entries=1)
    with pytest.raises(ValueError, match="at least 1"):
        mod.ReactionActionRegistry(max_entries=0)


def test_registry_default_capacity_is_exactly_256() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry()
    for i in range(257):
        registry.register(
            room_id="!room:example",
            event_id=f"${i}",
            actions=[{"reaction": "✅", "service": "light.turn_on"}],
        )
    assert registry.consume(room_id="!room:example", event_id="$0", reaction="✅") is None
    assert registry.consume(room_id="!room:example", event_id="$1", reaction="✅") is not None


def test_registry_rejects_service_with_empty_domain_or_name() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry()
    for service in (".turn_on", "light."):
        with pytest.raises(ValueError, match="domain.service"):
            registry.register(
                room_id="!room:example",
                event_id="$message",
                actions=[{"reaction": "X", "service": service}],
            )


def test_registry_keeps_other_recent_entry_at_capacity() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(max_entries=2)
    for i in range(3):
        registry.register(
            room_id="!room:example",
            event_id=f"${i}",
            actions=[{"reaction": "✅", "service": "light.turn_on"}],
        )
    assert registry.consume(room_id="!room:example", event_id="$1", reaction="✅") is not None
    assert registry.consume(room_id="!room:example", event_id="$2", reaction="✅") is not None


def test_consuming_one_reaction_preserves_other_action() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(max_entries=2)
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {"reaction": "💡", "service": "light.turn_on"},
            {"reaction": "🔕", "service": "input_boolean.turn_off"},
        ],
    )
    assert registry.consume(room_id="!room:example", event_id="$message", reaction="💡") is not None
    second = registry.consume(room_id="!room:example", event_id="$message", reaction="🔕")
    assert second is not None
    assert second.service == "input_boolean.turn_off"
