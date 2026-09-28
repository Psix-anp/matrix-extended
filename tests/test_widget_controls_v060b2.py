from __future__ import annotations

from dataclasses import dataclass

import pytest

from custom_components.matrix_extended.control_panels import PanelEntity
from custom_components.matrix_extended.widget_controls import (
    build_control_action,
    project_entity,
)


@dataclass
class State:
    state: str
    attributes: dict


def entity(entity_id, controls, confirms=()):
    return PanelEntity(
        entity_id=entity_id,
        label=entity_id,
        widget_controls=tuple(controls),
        confirm_controls=tuple(confirms),
    )


def test_light_projection_and_brightness_action():
    projected = project_entity(
        entity("light.living", ["toggle", "brightness"]),
        State("on", {"brightness": 128, "supported_color_modes": ["brightness"]}),
    )
    assert projected["controls"] == ["toggle", "brightness"]
    assert projected["attributes"]["brightness_pct"] == 50
    action = build_control_action(
        entity("light.living", ["toggle", "brightness"], ["brightness"]),
        State("on", {"supported_color_modes": ["brightness"]}),
        "brightness",
        65,
    )
    assert action.handler.service == "light.turn_on"
    assert action.handler.data == {"brightness_pct": 65}
    assert action.confirmation_required is True


def test_unavailable_entity_has_no_controls():
    projected = project_entity(
        entity("switch.pump", ["toggle"]), State("unavailable", {})
    )
    assert projected["available"] is False
    assert projected["controls"] == []


def test_cover_controls_follow_feature_bits():
    item = entity("cover.curtain", ["open", "close", "stop", "position"])
    projected = project_entity(
        item,
        State(
            "open",
            {"supported_features": 1 | 2 | 4 | 8, "current_position": 70},
        ),
    )
    assert projected["controls"] == ["open", "close", "stop", "position"]
    assert projected["attributes"]["position"] == 70
    action = build_control_action(
        item, State("open", {"supported_features": 15}), "position", 25
    )
    assert action.handler.service == "cover.set_cover_position"
    assert action.handler.data == {"position": 25}


def test_climate_temperature_validates_range_and_step():
    item = entity("climate.room", ["temperature", "hvac_mode"])
    state = State(
        "heat",
        {
            "supported_features": 1,
            "min_temp": 16,
            "max_temp": 30,
            "target_temp_step": 0.5,
            "temperature": 22,
            "hvac_modes": ["off", "heat"],
        },
    )
    action = build_control_action(item, state, "temperature", 21.5)
    assert action.handler.service == "climate.set_temperature"
    assert action.handler.data == {"temperature": 21.5}
    with pytest.raises(ValueError, match="step"):
        build_control_action(item, state, "temperature", 21.3)
    with pytest.raises(ValueError, match="hvac_mode"):
        build_control_action(item, state, "hvac_mode", "cool")


def test_sensors_are_read_only():
    projected = project_entity(
        entity("sensor.temp", []),
        State("22.1", {"unit_of_measurement": "°C"}),
    )
    assert projected["controls"] == []
    with pytest.raises(ValueError, match="control"):
        build_control_action(entity("sensor.temp", []), State("22", {}), "toggle", None)


def test_media_player_controls_follow_supported_features():
    # PAUSE=1, VOLUME_SET=4, VOLUME_MUTE=8, PREVIOUS=16, NEXT=32, PLAY=16384
    item = entity(
        "media_player.living",
        ["play_pause", "previous", "next", "mute", "volume"],
    )
    state = State(
        "playing",
        {
            "supported_features": 1 | 4 | 8 | 16 | 32 | 16384,
            "volume_level": 0.42,
            "is_volume_muted": False,
            "media_title": "Track",
        },
    )
    projected = project_entity(item, state)
    assert projected["controls"] == [
        "play_pause",
        "previous",
        "next",
        "mute",
        "volume",
    ]
    assert projected["attributes"]["volume_pct"] == 42
    action = build_control_action(item, state, "volume", 55)
    assert action.handler.service == "media_player.volume_set"
    assert action.handler.data == {"volume_level": 0.55}


def test_lock_and_alarm_generic_controls_fail_closed():
    for domain in ("lock", "alarm_control_panel"):
        item = PanelEntity(
            entity_id=f"{domain}.x",
            label="x",
            widget_controls=(),
            confirm_controls=(),
        )
        with pytest.raises(ValueError, match="control"):
            build_control_action(item, State("on", {}), "toggle", None)
