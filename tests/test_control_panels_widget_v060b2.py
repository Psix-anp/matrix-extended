from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
PKG = "matrix_extended_widget_panels_v060b2_testpkg"
package = types.ModuleType(PKG)
package.__path__ = [str(COMP)]
sys.modules[PKG] = package
panels = importlib.import_module(f"{PKG}.control_panels")

dump_panel_yaml = panels.dump_panel_yaml
load_panel_yaml = panels.load_panel_yaml
normalize_control_panels = panels.normalize_control_panels

OWNER = "@owner:matrix.test"
ROOM = "!room:matrix.test"


def parse(raw):
    return next(
        iter(
            normalize_control_panels(
                [raw],
                account_allowed_users={OWNER},
                account_allowed_room_ids={ROOM},
            ).values()
        )
    )


def base_entity(**extra):
    value = {"entity_id": "light.living", "label": "Light"}
    value.update(extra)
    return value


def base_panel(entity=None, **extra):
    value = {
        "panel_id": "living",
        "room_id": ROOM,
        "title": "Living",
        "enabled": True,
        "entities": [entity or base_entity()],
        "actions": [],
        "allowed_users": [OWNER],
        "debounce": 1.5,
    }
    value.update(extra)
    return value


def test_b1_panel_parses_with_widget_defaults_disabled():
    panel = parse(base_panel())
    assert panel.widget_enabled is False
    assert panel.widget_url is None
    assert panel.entities[0].widget_controls == ()
    assert panel.entities[0].confirm_controls == ()


def test_widget_fields_round_trip_yaml():
    panel = parse(
        base_panel(
            base_entity(
                widget_controls=["toggle", "brightness"],
                confirm_controls=["brightness"],
            ),
            widget_enabled=True,
            widget_url="https://widgets.example/matrix",
        )
    )
    restored = load_panel_yaml(
        dump_panel_yaml(panel),
        account_allowed_users={OWNER},
        account_allowed_room_ids={ROOM},
    )
    assert restored == panel


def test_unknown_or_domain_incompatible_controls_fail_closed():
    with pytest.raises(ValueError, match="widget control"):
        parse(base_panel(base_entity(widget_controls=["explode"])))
    with pytest.raises(ValueError, match="widget control"):
        parse(
            base_panel(
                {
                    "entity_id": "sensor.temp",
                    "label": "Temp",
                    "widget_controls": ["toggle"],
                }
            )
        )


def test_confirm_controls_must_be_enabled():
    with pytest.raises(ValueError, match="confirm_controls"):
        parse(
            base_panel(
                base_entity(
                    widget_controls=["toggle"],
                    confirm_controls=["brightness"],
                )
            )
        )


def test_widget_url_requires_https_except_localhost():
    with pytest.raises(ValueError, match="widget_url"):
        parse(
            base_panel(
                widget_enabled=True,
                widget_url="http://widgets.example/panel",
            )
        )
    assert parse(
        base_panel(widget_enabled=True, widget_url="http://localhost:5173")
    ).widget_enabled
