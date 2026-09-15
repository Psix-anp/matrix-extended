from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
MODULE = COMP / "control_panels.py"

OWNER = "@owner:matrix.test"
ROOM = "!room:matrix.test"


def load_module():
    assert MODULE.exists(), "control_panels.py is not implemented yet"
    pkg_name = "matrix_extended_control_panels_v060_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package
    spec = importlib.util.spec_from_file_location(f"{pkg_name}.control_panels", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def panel_raw(**overrides):
    panel = {
        "panel_id": "garage",
        "room_id": ROOM,
        "title": "🏠 Garage",
        "enabled": True,
        "entities": [
            {"entity_id": "cover.garage", "label": "Gate"},
            {"entity_id": "sensor.garage_temperature", "label": "Temperature"},
        ],
        "actions": [
            {
                "id": "garage.open",
                "reaction": "🔼",
                "label": "Open",
                "service": "cover.open_cover",
                "target": {"entity_id": "cover.garage"},
                "data": {},
                "confirmation_required": True,
            },
            {
                "id": "garage.close",
                "reaction": "🔽",
                "label": "Close",
                "service": "cover.close_cover",
                "target": {"entity_id": "cover.garage"},
                "data": {},
                "confirmation_required": False,
            },
        ],
        "allowed_users": [OWNER],
    }
    panel.update(overrides)
    return panel


def normalize(mod, raw):
    return mod.normalize_control_panels(
        raw,
        account_allowed_users={OWNER},
        account_allowed_room_ids={ROOM, "!other:matrix.test"},
    )


def test_normalize_builds_typed_panel_with_default_debounce() -> None:
    mod = load_module()
    panels = normalize(mod, [panel_raw()])

    panel = panels["garage"]
    assert panel.panel_id == "garage"
    assert panel.room_id == ROOM
    assert panel.title == "🏠 Garage"
    assert panel.enabled is True
    assert panel.debounce == 1.5
    assert panel.allowed_users == (OWNER,)
    assert panel.entities[0] == mod.PanelEntity("cover.garage", "Gate")
    assert panel.actions[0].id == "garage.open"
    assert panel.actions[0].reaction == "🔼"
    assert panel.actions[0].action.id == "garage.open"
    assert panel.actions[0].action.handler.service == "cover.open_cover"
    assert panel.actions[0].action.confirmation_required is True


def test_rejects_duplicate_room() -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="one control panel per room"):
        normalize(
            mod,
            [panel_raw(), panel_raw(panel_id="second", room_id=ROOM)],
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        (
            "actions",
            [
                panel_raw()["actions"][0],
                {**panel_raw()["actions"][1], "id": "garage.open"},
            ],
            "duplicate action id",
        ),
        (
            "actions",
            [
                panel_raw()["actions"][0],
                {**panel_raw()["actions"][1], "reaction": "🔼"},
            ],
            "duplicate reaction",
        ),
        (
            "entities",
            [
                panel_raw()["entities"][0],
                {"entity_id": "cover.garage", "label": "Duplicate"},
            ],
            "duplicate entity",
        ),
    ],
)
def test_rejects_duplicate_panel_members(field, replacement, message) -> None:
    mod = load_module()
    with pytest.raises(ValueError, match=message):
        normalize(mod, [panel_raw(**{field: replacement})])


def test_panel_users_may_only_narrow_account_allowlist() -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="outside account allowed_users"):
        normalize(mod, [panel_raw(allowed_users=["@intruder:matrix.test"])])


def test_panel_room_must_be_resolved_allowed_room_id() -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="outside account allowed_rooms"):
        normalize(mod, [panel_raw(room_id="!denied:matrix.test")])

    with pytest.raises(ValueError, match="resolved room ID"):
        normalize(mod, [panel_raw(room_id="#garage:matrix.test")])


@pytest.mark.parametrize("debounce", [0.24, 10.01, 0, -1])
def test_debounce_is_bounded(debounce) -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="debounce"):
        normalize(mod, [panel_raw(debounce=debounce)])


def test_yaml_round_trip_is_stable() -> None:
    mod = load_module()
    panel = normalize(mod, [panel_raw(debounce=2.0)])["garage"]

    text = mod.dump_panel_yaml(panel)
    loaded = mod.load_panel_yaml(
        text,
        account_allowed_users={OWNER},
        account_allowed_room_ids={ROOM},
    )

    assert loaded == panel
    assert "garage.open" in text
    assert "cover.open_cover" in text


@pytest.mark.parametrize(
    "text",
    [
        "---\npanel_id: one\n---\npanel_id: two\n",
        "- not\n- a\n- mapping\n",
        "null\n",
    ],
)
def test_yaml_rejects_multidoc_or_non_mapping_root(text) -> None:
    mod = load_module()
    with pytest.raises(ValueError):
        mod.load_panel_yaml(
            text,
            account_allowed_users={OWNER},
            account_allowed_room_ids={ROOM},
        )
