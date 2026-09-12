from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load(name: str):
    path = COMP / f"{name}.py"
    assert path.exists(), f"{name}.py implementation is absent"
    spec = importlib.util.spec_from_file_location(f"matrix_extended_v04_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_room_info_reads_nio_room_metadata() -> None:
    mod = load("rooms")

    class Room:
        room_id = "!garage:example"
        display_name = "Garage"
        canonical_alias = "#garage:example"
        encrypted = True
        joined_count = 3

    info = mod.room_info_from_nio(Room())
    assert info.room_id == "!garage:example"
    assert info.display_name == "Garage"
    assert info.canonical_alias == "#garage:example"
    assert info.encrypted is True
    assert info.joined_count == 3


def test_room_labels_disambiguate_duplicate_names() -> None:
    mod = load("rooms")
    rooms = [
        mod.MatrixRoomInfo("!one:ex", "Home", None, True, 2),
        mod.MatrixRoomInfo("!two:ex", "Home", "#home2:ex", True, 4),
        mod.MatrixRoomInfo("!three:ex", "Garage", None, True, 1),
    ]
    labels = mod.build_room_labels(rooms)
    assert labels["Garage"] == "!three:ex"
    assert labels["Home · !one:ex"] == "!one:ex"
    assert labels["Home · #home2:ex"] == "!two:ex"


def test_route_resolution_and_deduplication() -> None:
    mod = load("routing")
    assert mod.resolve_targets(
        explicit_targets=None,
        route="security",
        default_room="!default:ex",
        routing_profiles={"security": ["!a:ex", "!b:ex", "!a:ex"]},
    ) == ["!a:ex", "!b:ex"]


def test_explicit_targets_override_default_and_are_deduplicated() -> None:
    mod = load("routing")
    assert mod.resolve_targets(
        explicit_targets=["!x:ex", "!x:ex", "!y:ex"],
        route=None,
        default_room="!default:ex",
        routing_profiles={},
    ) == ["!x:ex", "!y:ex"]


def test_target_and_route_are_mutually_exclusive() -> None:
    mod = load("routing")
    with pytest.raises(ValueError, match="target.*route"):
        mod.resolve_targets(
            explicit_targets=["!x:ex"],
            route="security",
            default_room="!default:ex",
            routing_profiles={"security": ["!a:ex"]},
        )


def test_unknown_or_empty_route_is_rejected() -> None:
    mod = load("routing")
    with pytest.raises(ValueError, match="Unknown Matrix route"):
        mod.resolve_targets(
            explicit_targets=None,
            route="missing",
            default_room="!default:ex",
            routing_profiles={},
        )
    with pytest.raises(ValueError, match="has no rooms"):
        mod.resolve_targets(
            explicit_targets=None,
            route="empty",
            default_room="!default:ex",
            routing_profiles={"empty": []},
        )


def test_routing_profile_rejects_nested_object_instead_of_room_list() -> None:
    mod = load("routing")
    with pytest.raises(ValueError, match="room list"):
        mod.normalize_routing_profiles({"security": {"room": "!x:ex"}})


def test_normalize_routing_profiles_accepts_mapping_and_rejects_blank_name() -> None:
    mod = load("routing")
    assert mod.normalize_routing_profiles(
        {"security": [" !a:ex ", "!a:ex", "", "!b:ex"]}
    ) == {"security": ["!a:ex", "!b:ex"]}
    with pytest.raises(ValueError, match="cannot be blank"):
        mod.normalize_routing_profiles({"   ": ["!a:ex"]})


def test_resolve_targets_rejects_blank_default_room() -> None:
    mod = load("routing")
    with pytest.raises(ValueError, match="default room"):
        mod.resolve_targets(
            explicit_targets=None,
            route=None,
            default_room="   ",
            routing_profiles={},
        )


def test_room_machine_name_prefers_alias_then_room_id() -> None:
    mod = load("rooms")
    aliased = mod.MatrixRoomInfo("!one:ex", "One", "#one:ex", True, 1)
    plain = mod.MatrixRoomInfo("!two:ex", "Two", None, True, 1)
    assert aliased.machine_name == "#one:ex"
    assert plain.machine_name == "!two:ex"


def test_room_info_metadata_fallbacks_are_stable() -> None:
    mod = load("rooms")

    class Missing:
        room_id = "!missing:ex"

    class NoneCount:
        room_id = "!none:ex"
        display_name = "NoneCount"
        joined_count = None

    class BadCount:
        room_id = "!bad:ex"
        display_name = "BadCount"
        joined_count = "not-an-int"

    missing = mod.room_info_from_nio(Missing())
    assert missing.display_name == "!missing:ex"
    assert missing.joined_count == 0
    assert missing.encrypted is False
    assert mod.room_info_from_nio(NoneCount()).joined_count == 0
    assert mod.room_info_from_nio(BadCount()).joined_count == 0
