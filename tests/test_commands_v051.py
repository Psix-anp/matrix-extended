from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
COMMANDS = ROOT / "custom_components" / "matrix_extended" / "commands.py"


def load_commands():
    spec = importlib.util.spec_from_file_location("matrix_extended_commands_v051_test", COMMANDS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeStore:
    def __init__(self) -> None:
        self.saved = []

    async def async_save(self, value):
        self.saved.append(value)


def service_definition(**overrides):
    value = {
        "id": "garage_open",
        "trigger": "garage open",
        "aliases": ["open gate"],
        "description": "Open garage",
        "enabled": True,
        "allowed_users": ["@owner:example.org"],
        "allowed_rooms": ["!home:example.org"],
        "progress": True,
        "handler": {
            "type": "service",
            "service": "script.turn_on",
            "target": {"entity_id": "script.open_garage"},
            "data": {"variables": {"source": "matrix"}},
        },
    }
    value.update(overrides)
    return value


def camera_definition(**overrides):
    value = {
        "id": "camera_gate",
        "trigger": "camera gate",
        "aliases": ["gate camera"],
        "description": "Front gate snapshot",
        "enabled": True,
        "allowed_users": [],
        "allowed_rooms": [],
        "progress": True,
        "handler": {
            "type": "camera_snapshot",
            "entity_id": "camera.gate",
            "caption": "Gate camera",
        },
    }
    value.update(overrides)
    return value


def test_normalize_command_phrase() -> None:
    mod = load_commands()
    assert mod.normalize_command_phrase("  !Garage   OPEN  ") == "garage open"
    assert mod.normalize_command_phrase("!!Status") == "!status"


def test_registry_rejects_duplicate_alias_across_commands() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    registry.register(service_definition())
    with pytest.raises(ValueError, match="duplicate command phrase"):
        registry.register(
            service_definition(
                id="other",
                trigger="gate open",
                aliases=["open gate"],
                handler={
                    "type": "service",
                    "service": "script.turn_on",
                    "target": {"entity_id": "script.other"},
                    "data": {},
                },
            )
        )


def test_registry_exact_match_requires_leading_bang_and_command_allowlists() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    command = registry.register(service_definition())

    assert registry.match(
        " !GARAGE   open ",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) == command
    assert registry.match(
        "garage open",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None
    assert registry.match(
        "!garage open now",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None
    assert registry.match(
        "!garage open",
        sender="@intruder:example.org",
        room_id="!home:example.org",
    ) is None
    assert registry.match(
        "!garage open",
        sender="@owner:example.org",
        room_id="!other:example.org",
    ) is None


def test_disabled_command_never_matches() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    registry.register(service_definition(enabled=False))
    assert registry.match(
        "!garage open",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None


def test_service_and_camera_models_are_immutable_and_typed() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    service = registry.register(service_definition())
    camera = registry.register(camera_definition())

    assert isinstance(service.handler, mod.ServiceCommandHandler)
    assert service.handler.service == "script.turn_on"
    assert service.handler.target == {"entity_id": "script.open_garage"}
    assert isinstance(camera.handler, mod.CameraSnapshotCommandHandler)
    assert camera.handler.entity_id == "camera.gate"
    with pytest.raises((AttributeError, TypeError)):
        service.id = "changed"


def test_same_id_replaces_definition_and_releases_old_phrases() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    registry.register(service_definition())
    replacement = registry.register(
        service_definition(trigger="garage unlock", aliases=["unlock garage"])
    )

    assert registry.count == 1
    assert registry.match(
        "!garage open",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None
    assert registry.match(
        "!garage unlock",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) == replacement


def test_unregister_returns_removed_flag() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    registry.register(camera_definition())
    assert registry.unregister("camera_gate") is True
    assert registry.unregister("camera_gate") is False
    assert registry.count == 0


def test_dump_restore_round_trip_preserves_handlers_and_policy() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    registry.register(service_definition())
    registry.register(camera_definition(progress=False))

    restored = mod.CommandRegistry(registry.dump())
    assert restored.dump() == registry.dump()
    assert restored.count == 2
    camera = restored.match(
        "!gate camera",
        sender="@any:example.org",
        room_id="!any:example.org",
    )
    assert camera is not None
    assert camera.progress is False
    assert isinstance(camera.handler, mod.CameraSnapshotCommandHandler)


def test_malformed_stored_entries_are_skipped_fail_closed() -> None:
    mod = load_commands()
    restored = mod.CommandRegistry(
        {
            "commands": [
                service_definition(),
                {"id": "bad", "trigger": "bad", "handler": {"type": "service"}},
                camera_definition(id="bad_camera", handler={"type": "camera_snapshot", "entity_id": "light.not_camera"}),
            ]
        }
    )
    assert restored.count == 1
    assert restored.match(
        "!bad",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None


def test_runtime_registration_rejects_invalid_handler_shapes() -> None:
    mod = load_commands()
    registry = mod.CommandRegistry()
    with pytest.raises(ValueError):
        registry.register(service_definition(handler={"type": "service", "service": "invalid", "target": {}, "data": {}}))
    with pytest.raises(ValueError):
        registry.register(camera_definition(handler={"type": "camera_snapshot", "entity_id": "light.gate", "caption": "x"}))


@pytest.mark.asyncio
async def test_async_save_uses_attached_store() -> None:
    mod = load_commands()
    store = FakeStore()
    registry = mod.CommandRegistry(store=store)
    registry.register(camera_definition())
    await registry.async_save()
    assert store.saved == [registry.dump()]
