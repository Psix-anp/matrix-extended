from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "custom_components" / "matrix_extended" / "notifications.py"


def load():
    assert PATH.exists(), "notifications.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_v04_notifications", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_notification_registry_maps_key_per_room_and_replaces_event() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry()
    registry.set("download.movie", "!one:ex", "$first")
    registry.set("download.movie", "!two:ex", "$second")
    registry.set("download.movie", "!one:ex", "$replacement")
    assert registry.get("download.movie", "!one:ex") == "$replacement"
    assert registry.get("download.movie", "!two:ex") == "$second"


def test_notification_registry_round_trips_storage_shape() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry(
        {"alarm.front": {"!security:ex": "$event"}}
    )
    assert registry.dump() == {"alarm.front": {"!security:ex": "$event"}}


def test_notification_registry_rejects_blank_key() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry()
    with pytest.raises(ValueError, match="notification_key"):
        registry.set("   ", "!room:ex", "$event")


def test_notification_registry_ignores_corrupt_non_mapping_store() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry(["broken"])
    assert registry.dump() == {}


def test_registry_ignores_invalid_stored_keys_and_mappings() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry(
        {
            "": {"!room:ex": "$event"},
            "bad-room": {"": "$event"},
            "bad-event": {"!room:ex": ""},
            "not-a-map": ["broken"],
        }
    )
    assert registry.dump() == {}


def test_notification_key_length_boundary() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry()
    key128 = "x" * 128
    registry.set(key128, "!room:ex", "$event")
    assert registry.get(key128, "!room:ex") == "$event"
    with pytest.raises(ValueError, match="128"):
        registry.set("x" * 129, "!room:ex", "$event")


def test_registry_rejects_individually_blank_room_or_event() -> None:
    mod = load()
    registry = mod.NotificationKeyRegistry()
    with pytest.raises(ValueError, match="room_id and event_id"):
        registry.set("key", "", "$event")
    with pytest.raises(ValueError, match="room_id and event_id"):
        registry.set("key", "!room:ex", "")
