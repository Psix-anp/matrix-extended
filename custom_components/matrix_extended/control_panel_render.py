"""Deterministic Home Assistant state renderer for Matrix control panels."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from typing import Any

from .control_panels import ControlPanelDefinition


@dataclass(slots=True, frozen=True)
class RenderedPanel:
    """Plain/HTML panel output plus a stable content digest."""

    body: str
    formatted_body: str
    digest: str


def _attributes(state: Any) -> Mapping[str, Any]:
    attrs = getattr(state, "attributes", None)
    return attrs if isinstance(attrs, Mapping) else {}


def _state_value(state: Any) -> str:
    if state is None:
        return "unavailable"
    value = getattr(state, "state", state)
    return str(value)


def _friendly_state(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _unit_value(value: Any, unit: Any) -> str:
    text = str(value)
    unit_text = str(unit or "").strip()
    return f"{text} {unit_text}" if unit_text else text


def _render_entity(entity_id: str, state: Any) -> str:
    raw = _state_value(state)
    if state is None:
        return raw
    domain = entity_id.split(".", 1)[0]
    attrs = _attributes(state)

    if domain == "light" and raw in {"on", "off"}:
        return "On" if raw == "on" else "Off"

    if domain == "cover":
        known = {
            "open": "Open",
            "opening": "Opening",
            "closed": "Closed",
            "closing": "Closing",
        }
        return known.get(raw, _friendly_state(raw))

    if domain == "alarm_control_panel":
        return _friendly_state(raw)

    if domain == "climate":
        mode = _friendly_state(raw)
        unit = attrs.get("temperature_unit") or attrs.get("unit_of_measurement") or "°C"
        current = attrs.get("current_temperature")
        target = attrs.get("temperature")
        if current is not None and target is not None:
            return f"{mode} · {_unit_value(current, unit)} → {_unit_value(target, unit)}"
        if current is not None:
            return f"{mode} · {_unit_value(current, unit)}"
        if target is not None:
            return f"{mode} · target {_unit_value(target, unit)}"
        return mode

    if domain == "sensor":
        return _unit_value(raw, attrs.get("unit_of_measurement"))

    return raw


def render_control_panel(
    panel: ControlPanelDefinition,
    states: Mapping[str, Any],
) -> RenderedPanel:
    """Render a panel without wall-clock data so unchanged state stays identical."""
    plain_lines = [panel.title, ""]
    html_lines = [f"<strong>{escape(panel.title)}</strong>", ""]

    for entity in panel.entities:
        value = _render_entity(entity.entity_id, states.get(entity.entity_id))
        plain_lines.append(f"{entity.label}: {value}")
        html_lines.append(
            f"<strong>{escape(entity.label)}:</strong> {escape(value)}"
        )

    if panel.actions:
        plain_lines.extend(
            [
                "",
                "Control:",
                " · ".join(
                    f"{action.reaction} {action.label}" for action in panel.actions
                ),
            ]
        )
        html_lines.extend(
            [
                "",
                "<strong>Control:</strong>",
                " · ".join(
                    f"{escape(action.reaction)} {escape(action.label)}"
                    for action in panel.actions
                ),
            ]
        )

    body = "\n".join(plain_lines)
    formatted_body = "<br>".join(html_lines)
    digest = sha256(
        (body + "\x00" + formatted_body).encode("utf-8")
    ).hexdigest()
    return RenderedPanel(
        body=body,
        formatted_body=formatted_body,
        digest=digest,
    )
