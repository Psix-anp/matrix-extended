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


def test_registry_round_trips_json_safe_state_across_restart() -> None:
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
            },
            {
                "reaction": "🔕",
                "service": "input_boolean.turn_off",
            },
        ],
    )

    stored = registry.dump()
    restored = mod.ReactionActionRegistry(stored, max_entries=4)

    action = restored.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="💡",
    )
    assert action is not None
    assert action.service == "light.turn_on"
    assert action.target == {"entity_id": "light.gate"}
    assert action.data == {"brightness_pct": 50}
    assert restored.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="💡",
    ) is None


def test_dump_reflects_consumed_action_without_losing_other_reactions() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry()
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {"reaction": "💡", "service": "light.turn_on"},
            {"reaction": "🔕", "service": "input_boolean.turn_off"},
        ],
    )

    registry.consume(room_id="!room:example", event_id="$message", reaction="💡")
    stored = registry.dump()
    restored = mod.ReactionActionRegistry(stored)

    assert restored.consume(room_id="!room:example", event_id="$message", reaction="💡") is None
    second = restored.consume(room_id="!room:example", event_id="$message", reaction="🔕")
    assert second is not None
    assert second.service == "input_boolean.turn_off"


def test_restore_ignores_invalid_persisted_actions() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(
        {
            "!room:example": {
                "$message": {
                    "✅": {"service": "light.turn_on", "target": {}, "data": {}},
                    "bad": {"service": "not-a-service"},
                }
            },
            "": {"$ignored": {"✅": {"service": "light.turn_on"}}},
        }
    )

    action = registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="✅",
    )
    assert action is not None
    assert action.service == "light.turn_on"
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="bad",
    ) is None


def test_action_user_allowlist_does_not_consume_for_unauthorized_sender() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(now=lambda: 100.0)
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {
                "reaction": "🔓",
                "service": "lock.unlock",
                "allowed_users": ["@owner:example.org"],
                "max_uses": 2,
                "expires_in": 60,
            }
        ],
    )
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="🔓",
        sender="@guest:example.org",
    ) is None
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="🔓",
        sender="@owner:example.org",
    ) is not None
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="🔓",
        sender="@owner:example.org",
    ) is not None
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="🔓",
        sender="@owner:example.org",
    ) is None


def test_action_expiry_is_persisted_and_pruned() -> None:
    mod = load()
    clock = [100.0]
    registry = mod.ReactionActionRegistry(now=lambda: clock[0])
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {
                "reaction": "✅",
                "service": "light.turn_on",
                "expires_in": 10,
                "max_uses": 3,
            }
        ],
    )
    stored = registry.dump()
    action_data = stored["!room:example"]["$message"]["✅"]
    assert action_data["expires_at"] == 110.0
    assert action_data["remaining_uses"] == 3

    clock[0] = 111.0
    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="✅",
    ) is None
    assert registry.dump() == {}


def test_registry_restores_legacy_actions_with_safe_defaults() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(
        {
            "!room:example": {
                "$message": {
                    "✅": {"service": "light.turn_on", "target": {}, "data": {}}
                }
            }
        },
        now=lambda: 100.0,
    )
    stored = registry.dump()["!room:example"]["$message"]["✅"]
    assert stored["expires_at"] == 3700.0
    assert stored["remaining_uses"] == 1
    assert stored["allowed_users"] == []


def test_registry_validates_action_control_bounds() -> None:
    mod = load()
    registry = mod.ReactionActionRegistry(now=lambda: 100.0)
    for action, error in (
        ({"reaction": "✅", "service": "light.turn_on", "expires_in": 0}, "expires_in"),
        ({"reaction": "✅", "service": "light.turn_on", "expires_in": 604801}, "expires_in"),
        ({"reaction": "✅", "service": "light.turn_on", "max_uses": 0}, "max_uses"),
        ({"reaction": "✅", "service": "light.turn_on", "max_uses": 101}, "max_uses"),
    ):
        with pytest.raises(ValueError, match=error):
            registry.register(room_id="!room:example", event_id="$message", actions=[action])
