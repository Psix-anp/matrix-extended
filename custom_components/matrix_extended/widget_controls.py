"""Bounded Home Assistant entity projections and Widget control intents."""

from __future__ import annotations

import math
from typing import Any

from .control_panels import PanelEntity
from .safe_actions import SafeActionDefinition, ServiceActionHandler

_COVER_FEATURES = {"open": 1, "close": 2, "position": 4, "stop": 8}
_MEDIA_FEATURES = {
    "play_pause": 1 | 16384,
    "volume": 4,
    "mute": 8,
    "previous": 16,
    "next": 32,
}


def _attrs(state: Any) -> dict[str, Any]:
    raw = getattr(state, "attributes", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _domain(entity: PanelEntity) -> str:
    return entity.entity_id.split(".", 1)[0]


def _available(state: Any) -> bool:
    return state is not None and str(getattr(state, "state", "unknown")) not in {
        "unavailable",
        "unknown",
    }


def _effective_controls(entity: PanelEntity, state: Any) -> list[str]:
    if not _available(state):
        return []
    domain = _domain(entity)
    attrs = _attrs(state)
    supported = int(attrs.get("supported_features", 0) or 0)
    result: list[str] = []
    for control in entity.widget_controls:
        ok = False
        if domain in {"light", "switch"} and control == "toggle":
            ok = True
        elif domain == "light" and control == "brightness":
            modes = set(attrs.get("supported_color_modes") or [])
            ok = attrs.get("brightness") is not None or bool(modes - {"onoff"})
        elif domain == "cover" and control in _COVER_FEATURES:
            ok = bool(supported & _COVER_FEATURES[control])
        elif domain == "climate" and control == "temperature":
            ok = bool(supported & 1)
        elif domain == "climate" and control == "hvac_mode":
            ok = bool(attrs.get("hvac_modes"))
        elif domain == "media_player" and control in _MEDIA_FEATURES:
            ok = bool(supported & _MEDIA_FEATURES[control])
        if ok:
            result.append(control)
    return result


def project_entity(entity: PanelEntity, state: Any) -> dict[str, Any]:
    """Project one HA state into a bounded Widget-safe representation."""
    domain = _domain(entity)
    attrs = _attrs(state)
    available = _available(state)
    projected: dict[str, Any] = {}
    if domain == "light" and attrs.get("brightness") is not None:
        projected["brightness_pct"] = round(int(attrs["brightness"]) * 100 / 255)
    elif domain == "cover" and attrs.get("current_position") is not None:
        projected["position"] = int(attrs["current_position"])
    elif domain == "climate":
        for source, target in (
            ("current_temperature", "current_temperature"),
            ("temperature", "target_temperature"),
            ("hvac_modes", "hvac_modes"),
        ):
            if attrs.get(source) is not None:
                projected[target] = attrs[source]
    elif domain in {"sensor", "binary_sensor"}:
        for key in ("unit_of_measurement", "device_class"):
            if attrs.get(key) is not None:
                projected[key] = attrs[key]
    elif domain == "media_player":
        if attrs.get("volume_level") is not None:
            projected["volume_pct"] = round(float(attrs["volume_level"]) * 100)
        for source, target in (
            ("is_volume_muted", "muted"),
            ("media_title", "title"),
            ("media_artist", "artist"),
        ):
            if attrs.get(source) is not None:
                projected[target] = attrs[source]
    return {
        "entity_id": entity.entity_id,
        "label": entity.label,
        "domain": domain,
        "state": str(getattr(state, "state", "unknown")),
        "available": available,
        "attributes": projected,
        "controls": _effective_controls(entity, state),
    }


def _percent(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = int(value)
    if number != value or not 0 <= number <= 100:
        raise ValueError(f"{name} must be an integer between 0 and 100")
    return number


def _temperature(value: Any, attrs: dict[str, Any]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("temperature must be numeric")
    number = float(value)
    low = float(attrs.get("min_temp", -273.15))
    high = float(attrs.get("max_temp", 1000.0))
    if not low <= number <= high:
        raise ValueError("temperature is outside entity range")
    step = float(attrs.get("target_temp_step", 1.0) or 1.0)
    quotient = (number - low) / step
    if not math.isclose(quotient, round(quotient), abs_tol=1e-7):
        raise ValueError("temperature does not match target step")
    return number


def build_control_action(
    entity: PanelEntity, state: Any, control: str, value: Any
) -> SafeActionDefinition:
    """Build a local SafeActionDefinition from one validated Widget intent."""
    if control not in entity.widget_controls:
        raise ValueError("control is not enabled for this entity")
    if control not in _effective_controls(entity, state):
        raise ValueError("control is not supported by the current entity state")
    domain = _domain(entity)
    attrs = _attrs(state)
    service: str
    data: dict[str, Any] = {}

    if domain == "light" and control == "toggle":
        service = "light.toggle"
    elif domain == "light" and control == "brightness":
        service = "light.turn_on"
        data = {"brightness_pct": _percent(value, name="brightness")}
    elif domain == "switch" and control == "toggle":
        service = "switch.toggle"
    elif domain == "cover" and control in {"open", "close", "stop"}:
        service = f"cover.{ {'open':'open_cover','close':'close_cover','stop':'stop_cover'}[control] }"
    elif domain == "cover" and control == "position":
        service = "cover.set_cover_position"
        data = {"position": _percent(value, name="position")}
    elif domain == "climate" and control == "temperature":
        service = "climate.set_temperature"
        data = {"temperature": _temperature(value, attrs)}
    elif domain == "climate" and control == "hvac_mode":
        if not isinstance(value, str) or value not in (attrs.get("hvac_modes") or []):
            raise ValueError("hvac_mode is not supported")
        service = "climate.set_hvac_mode"
        data = {"hvac_mode": value}
    elif domain == "media_player" and control == "play_pause":
        service = "media_player.media_play_pause"
    elif domain == "media_player" and control == "previous":
        service = "media_player.media_previous_track"
    elif domain == "media_player" and control == "next":
        service = "media_player.media_next_track"
    elif domain == "media_player" and control == "mute":
        if not isinstance(value, bool):
            raise ValueError("mute value must be boolean")
        service = "media_player.volume_mute"
        data = {"is_volume_muted": value}
    elif domain == "media_player" and control == "volume":
        service = "media_player.volume_set"
        data = {"volume_level": _percent(value, name="volume") / 100}
    else:
        raise ValueError("control is not supported for this entity domain")

    return SafeActionDefinition(
        id=f"widget:{entity.entity_id}:{control}",
        handler=ServiceActionHandler(
            service=service,
            target={"entity_id": entity.entity_id},
            data=data,
        ),
        confirmation_required=control in entity.confirm_controls,
    )
