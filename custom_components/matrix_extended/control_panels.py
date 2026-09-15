"""Validated configuration model for Matrix Extended control panels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

from .safe_actions import SafeActionDefinition, dump_action_handler, parse_service_handler

DEFAULT_PANEL_DEBOUNCE = 1.5
MIN_PANEL_DEBOUNCE = 0.25
MAX_PANEL_DEBOUNCE = 10.0


@dataclass(slots=True, frozen=True)
class PanelEntity:
    """One Home Assistant entity rendered on a control panel."""

    entity_id: str
    label: str


@dataclass(slots=True, frozen=True)
class PanelAction:
    """One reaction-addressable control action."""

    id: str
    reaction: str
    label: str
    action: SafeActionDefinition


@dataclass(slots=True, frozen=True)
class ControlPanelDefinition:
    """Validated persistent control panel definition."""

    panel_id: str
    room_id: str
    title: str
    enabled: bool
    entities: tuple[PanelEntity, ...]
    actions: tuple[PanelAction, ...]
    allowed_users: tuple[str, ...]
    debounce: float = DEFAULT_PANEL_DEBOUNCE


def _sequence(value: Any, *, name: str) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a list")
    return value


def _required_text(value: Any, *, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def _bool(value: Any, *, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _parse_users(value: Any, *, account_allowed_users: set[str]) -> tuple[str, ...]:
    users: list[str] = []
    seen: set[str] = set()
    for raw in _sequence(value, name="allowed_users"):
        user = _required_text(raw, name="allowed user")
        if not user.startswith("@") or ":" not in user[1:]:
            raise ValueError("allowed_users must contain valid Matrix user IDs")
        if user not in account_allowed_users:
            raise ValueError("panel allowed_users contains user outside account allowed_users")
        if user not in seen:
            seen.add(user)
            users.append(user)
    return tuple(users)


def _parse_entities(value: Any) -> tuple[PanelEntity, ...]:
    entities: list[PanelEntity] = []
    seen: set[str] = set()
    for raw in _sequence(value, name="entities"):
        if not isinstance(raw, Mapping):
            raise ValueError("panel entity must be an object")
        entity_id = _required_text(raw.get("entity_id"), name="entity_id")
        if "." not in entity_id or entity_id.startswith(".") or entity_id.endswith("."):
            raise ValueError("entity_id must use domain.object format")
        if entity_id in seen:
            raise ValueError(f"duplicate entity: {entity_id}")
        seen.add(entity_id)
        label = str(raw.get("label") or entity_id).strip() or entity_id
        entities.append(PanelEntity(entity_id=entity_id, label=label))
    return tuple(entities)


def _parse_actions(value: Any) -> tuple[PanelAction, ...]:
    actions: list[PanelAction] = []
    seen_ids: set[str] = set()
    seen_reactions: set[str] = set()
    for raw in _sequence(value, name="actions"):
        if not isinstance(raw, Mapping):
            raise ValueError("panel action must be an object")
        action_id = _required_text(raw.get("id"), name="action id")
        reaction = _required_text(raw.get("reaction"), name="reaction")
        if action_id in seen_ids:
            raise ValueError(f"duplicate action id: {action_id}")
        if reaction in seen_reactions:
            raise ValueError(f"duplicate reaction: {reaction}")
        seen_ids.add(action_id)
        seen_reactions.add(reaction)
        label = str(raw.get("label") or action_id).strip() or action_id
        confirmation_required = _bool(
            raw.get("confirmation_required"),
            name="confirmation_required",
            default=False,
        )
        handler = parse_service_handler(raw)
        definition = SafeActionDefinition(
            id=action_id,
            handler=handler,
            confirmation_required=confirmation_required,
        )
        actions.append(
            PanelAction(
                id=action_id,
                reaction=reaction,
                label=label,
                action=definition,
            )
        )
    return tuple(actions)


def _parse_panel(
    raw: Mapping[str, Any],
    *,
    account_allowed_users: set[str],
    account_allowed_room_ids: set[str],
) -> ControlPanelDefinition:
    panel_id = _required_text(raw.get("panel_id"), name="panel_id")
    room_id = _required_text(raw.get("room_id"), name="room_id")
    if not room_id.startswith("!") or ":" not in room_id[1:]:
        raise ValueError("panel room must be a resolved room ID starting with '!'")
    if room_id not in account_allowed_room_ids:
        raise ValueError("panel room is outside account allowed_rooms")

    try:
        debounce = float(raw.get("debounce", DEFAULT_PANEL_DEBOUNCE))
    except (TypeError, ValueError) as err:
        raise ValueError("debounce must be numeric") from err
    if not MIN_PANEL_DEBOUNCE <= debounce <= MAX_PANEL_DEBOUNCE:
        raise ValueError(
            f"debounce must be between {MIN_PANEL_DEBOUNCE} and {MAX_PANEL_DEBOUNCE} seconds"
        )

    return ControlPanelDefinition(
        panel_id=panel_id,
        room_id=room_id,
        title=str(raw.get("title") or panel_id).strip() or panel_id,
        enabled=_bool(raw.get("enabled"), name="enabled", default=True),
        entities=_parse_entities(raw.get("entities", [])),
        actions=_parse_actions(raw.get("actions", [])),
        allowed_users=_parse_users(
            raw.get("allowed_users", []),
            account_allowed_users=account_allowed_users,
        ),
        debounce=debounce,
    )


def normalize_control_panels(
    raw: Any,
    *,
    account_allowed_users: set[str],
    account_allowed_room_ids: set[str],
) -> dict[str, ControlPanelDefinition]:
    """Validate panel configuration and return it keyed by stable panel ID."""
    panels: dict[str, ControlPanelDefinition] = {}
    rooms: set[str] = set()
    for item in _sequence(raw, name="control_panels"):
        if not isinstance(item, Mapping):
            raise ValueError("control panel must be an object")
        panel = _parse_panel(
            item,
            account_allowed_users=set(account_allowed_users),
            account_allowed_room_ids=set(account_allowed_room_ids),
        )
        if panel.panel_id in panels:
            raise ValueError(f"duplicate panel_id: {panel.panel_id}")
        if panel.room_id in rooms:
            raise ValueError("only one control panel per room is supported")
        panels[panel.panel_id] = panel
        rooms.add(panel.room_id)
    return panels


def _dump_panel(panel: ControlPanelDefinition) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for item in panel.actions:
        handler = dump_action_handler(item.action.handler)
        if handler.get("type") != "service":
            raise ValueError("0.6.0b1 control panels support service actions only")
        actions.append(
            {
                "id": item.id,
                "reaction": item.reaction,
                "label": item.label,
                "service": handler["service"],
                "target": dict(handler["target"]),
                "data": dict(handler["data"]),
                "confirmation_required": item.action.confirmation_required,
            }
        )
    return {
        "panel_id": panel.panel_id,
        "room_id": panel.room_id,
        "title": panel.title,
        "enabled": panel.enabled,
        "entities": [
            {"entity_id": item.entity_id, "label": item.label}
            for item in panel.entities
        ],
        "actions": actions,
        "allowed_users": list(panel.allowed_users),
        "debounce": panel.debounce,
    }


def dump_panel_yaml(panel: ControlPanelDefinition) -> str:
    """Export one validated panel as safe single-document YAML."""
    return yaml.safe_dump(
        _dump_panel(panel),
        allow_unicode=True,
        sort_keys=False,
    )


def load_panel_yaml(
    text: str,
    *,
    account_allowed_users: set[str],
    account_allowed_room_ids: set[str],
) -> ControlPanelDefinition:
    """Load and validate exactly one control panel from YAML."""
    try:
        documents = list(yaml.safe_load_all(str(text)))
    except yaml.YAMLError as err:
        raise ValueError(f"invalid panel YAML: {err}") from err
    if len(documents) != 1:
        raise ValueError("panel YAML must contain exactly one document")
    raw = documents[0]
    if not isinstance(raw, Mapping):
        raise ValueError("panel YAML root must be an object")
    panels = normalize_control_panels(
        [raw],
        account_allowed_users=account_allowed_users,
        account_allowed_room_ids=account_allowed_room_ids,
    )
    return next(iter(panels.values()))
