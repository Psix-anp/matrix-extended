"""Versioned bounded protocol for Matrix Extended native widgets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

WIDGET_EVENT_TYPE = "io.psix.matrix_extended.widget.v1"
WIDGET_SCHEMA = 1

_MAX_PANEL_ID = 128
_MAX_ROOM_ID = 512
_MAX_ACTION_ID = 128
_MAX_ENTITY_ID = 255
_MAX_CONTROL = 64
_FORBIDDEN_KEYS = frozenset({"service", "target", "data", "template", "yaml"})


@dataclass(slots=True, frozen=True)
class WidgetRequest:
    op: str
    room_id: str
    panel_id: str
    generation: int
    request_id: str | None = None


@dataclass(slots=True, frozen=True)
class WidgetSubscribeRequest(WidgetRequest):
    pass


@dataclass(slots=True, frozen=True)
class WidgetHeartbeatRequest(WidgetRequest):
    pass


@dataclass(slots=True, frozen=True)
class WidgetActionRequest(WidgetRequest):
    kind: str = ""
    action_id: str | None = None
    entity_id: str | None = None
    control: str | None = None
    value: Any = None


@dataclass(slots=True, frozen=True)
class WidgetConfirmRequest(WidgetRequest):
    confirmation_id: str = ""


def _text(value: Any, *, name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > max_length:
        raise ValueError(f"{name} is too long")
    return text


def _uuid(value: Any, *, name: str) -> str:
    text = _text(value, name=name, max_length=64)
    try:
        parsed = UUID(text)
    except (ValueError, AttributeError) as err:
        raise ValueError(f"{name} must be a UUID") from err
    return str(parsed)


def _generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("generation must be an integer")
    if value < 0:
        raise ValueError("generation must not be negative")
    return value


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden(item) for item in value)
    return False


def _base(raw: Mapping[str, Any]) -> tuple[str, str, int]:
    if raw.get("schema") != WIDGET_SCHEMA:
        raise ValueError("unsupported widget schema")
    room_id = _text(raw.get("room_id"), name="room_id", max_length=_MAX_ROOM_ID)
    if not room_id.startswith("!") or ":" not in room_id[1:]:
        raise ValueError("room_id must be a resolved Matrix room ID")
    panel_id = _text(raw.get("panel_id"), name="panel_id", max_length=_MAX_PANEL_ID)
    generation = _generation(raw.get("generation"))
    return room_id, panel_id, generation


def parse_widget_request(raw: Mapping[str, Any]) -> WidgetRequest:
    """Validate one Widget -> Matrix Extended protocol message."""
    if not isinstance(raw, Mapping):
        raise ValueError("widget request must be an object")
    op = _text(raw.get("op"), name="op", max_length=32)
    if op not in {"subscribe", "heartbeat", "action", "confirm", "cancel"}:
        raise ValueError("unsupported widget op")
    room_id, panel_id, generation = _base(raw)

    if op == "subscribe":
        return WidgetSubscribeRequest(op, room_id, panel_id, generation)
    if op == "heartbeat":
        return WidgetHeartbeatRequest(op, room_id, panel_id, generation)

    request_id = _uuid(raw.get("request_id"), name="request_id")

    if op in {"confirm", "cancel"}:
        confirmation_id = _uuid(raw.get("confirmation_id"), name="confirmation_id")
        return WidgetConfirmRequest(
            op, room_id, panel_id, generation, request_id, confirmation_id
        )

    if _contains_forbidden(raw):
        raise ValueError("widget action contains forbidden execution keys")

    kind = _text(raw.get("kind"), name="kind", max_length=32)
    if kind == "panel_action":
        action_id = _text(
            raw.get("action_id"), name="action_id", max_length=_MAX_ACTION_ID
        )
        return WidgetActionRequest(
            op,
            room_id,
            panel_id,
            generation,
            request_id,
            kind,
            action_id=action_id,
        )
    if kind == "entity_control":
        entity_id = _text(
            raw.get("entity_id"), name="entity_id", max_length=_MAX_ENTITY_ID
        )
        if "." not in entity_id:
            raise ValueError("entity_id must use domain.object format")
        control = _text(raw.get("control"), name="control", max_length=_MAX_CONTROL)
        return WidgetActionRequest(
            op,
            room_id,
            panel_id,
            generation,
            request_id,
            kind,
            entity_id=entity_id,
            control=control,
            value=raw.get("value"),
        )
    raise ValueError("unsupported widget action kind")


def build_widget_message(
    *,
    op: str,
    room_id: str,
    panel_id: str,
    generation: int,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build one JSON-safe Matrix Extended -> Widget protocol envelope."""
    content: dict[str, Any] = {
        "schema": WIDGET_SCHEMA,
        "op": _text(op, name="op", max_length=32),
        "room_id": _text(room_id, name="room_id", max_length=_MAX_ROOM_ID),
        "panel_id": _text(panel_id, name="panel_id", max_length=_MAX_PANEL_ID),
        "generation": _generation(generation),
    }
    if request_id is not None:
        content["request_id"] = _uuid(request_id, name="request_id")
    for key, value in fields.items():
        if value is not None:
            content[str(key)] = value
    return content
