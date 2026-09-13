"""Persistent deterministic safe-command registry for Matrix Extended."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ServiceCommandHandler:
    """Pre-registered Home Assistant service command."""

    service: str
    target: dict[str, Any]
    data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class CameraSnapshotCommandHandler:
    """Pre-registered Home Assistant camera snapshot command."""

    entity_id: str
    caption: str


@dataclass(slots=True, frozen=True)
class RegisteredCommand:
    """Validated command definition stored by Matrix Extended."""

    id: str
    trigger: str
    aliases: tuple[str, ...]
    description: str
    enabled: bool
    allowed_users: tuple[str, ...]
    allowed_rooms: tuple[str, ...]
    progress: bool
    handler: ServiceCommandHandler | CameraSnapshotCommandHandler


def normalize_command_phrase(value: str) -> str:
    """Normalize a command phrase for exact deterministic matching."""
    normalized = str(value).strip()
    if normalized.startswith("!"):
        normalized = normalized[1:]
    return " ".join(normalized.split()).casefold()


def _matrix_user_ids(value: Any) -> tuple[str, ...]:
    if value in (None, []):
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("allowed_users must be a list of Matrix user IDs")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        user_id = str(raw).strip()
        if not user_id.startswith("@") or ":" not in user_id[1:]:
            raise ValueError("allowed_users must contain valid Matrix user IDs")
        if user_id not in seen:
            seen.add(user_id)
            result.append(user_id)
    return tuple(result)


def _matrix_rooms(value: Any) -> tuple[str, ...]:
    if value in (None, []):
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("allowed_rooms must be a list of Matrix room IDs or aliases")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        room = str(raw).strip()
        if not room or room[0] not in {"!", "#"} or ":" not in room[1:]:
            raise ValueError("allowed_rooms must contain valid Matrix room IDs or aliases")
        if room not in seen:
            seen.add(room)
            result.append(room)
    return tuple(result)


def _mapping(value: Any, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return dict(value)


def _bool(value: Any, *, name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _parse_handler(value: Any) -> ServiceCommandHandler | CameraSnapshotCommandHandler:
    if not isinstance(value, Mapping):
        raise ValueError("handler must be an object")
    handler_type = str(value.get("type", "")).strip()
    if handler_type == "service":
        service = str(value.get("service", "")).strip()
        if service.count(".") != 1 or any(not part for part in service.split(".", 1)):
            raise ValueError("service must use domain.service format")
        return ServiceCommandHandler(
            service=service,
            target=_mapping(value.get("target"), name="target"),
            data=_mapping(value.get("data"), name="data"),
        )
    if handler_type == "camera_snapshot":
        entity_id = str(value.get("entity_id", "")).strip()
        if not entity_id.startswith("camera.") or len(entity_id) <= len("camera."):
            raise ValueError("camera_snapshot entity_id must be a camera.* entity")
        caption = str(value.get("caption", "Camera snapshot")).strip() or "Camera snapshot"
        return CameraSnapshotCommandHandler(entity_id=entity_id, caption=caption)
    raise ValueError("handler type must be service or camera_snapshot")


def _command_definition(value: Mapping[str, Any]) -> RegisteredCommand:
    command_id = str(value.get("id", "")).strip()
    if not command_id:
        raise ValueError("command id must not be empty")

    trigger = normalize_command_phrase(str(value.get("trigger", "")))
    if not trigger:
        raise ValueError("command trigger must not be empty")

    raw_aliases = value.get("aliases", [])
    if isinstance(raw_aliases, (str, bytes)) or not isinstance(raw_aliases, Sequence):
        raise ValueError("aliases must be a list")
    aliases: list[str] = []
    seen = {trigger}
    for raw in raw_aliases:
        alias = normalize_command_phrase(str(raw))
        if not alias:
            raise ValueError("command alias must not be empty")
        if alias in seen:
            raise ValueError(f"duplicate command phrase: {alias}")
        seen.add(alias)
        aliases.append(alias)

    return RegisteredCommand(
        id=command_id,
        trigger=trigger,
        aliases=tuple(aliases),
        description=str(value.get("description", "")).strip(),
        enabled=_bool(value.get("enabled"), name="enabled", default=True),
        allowed_users=_matrix_user_ids(value.get("allowed_users")),
        allowed_rooms=_matrix_rooms(value.get("allowed_rooms")),
        progress=_bool(value.get("progress"), name="progress", default=True),
        handler=_parse_handler(value.get("handler")),
    )


def _handler_dump(handler: ServiceCommandHandler | CameraSnapshotCommandHandler) -> dict[str, Any]:
    if isinstance(handler, ServiceCommandHandler):
        return {
            "type": "service",
            "service": handler.service,
            "target": dict(handler.target),
            "data": dict(handler.data),
        }
    return {
        "type": "camera_snapshot",
        "entity_id": handler.entity_id,
        "caption": handler.caption,
    }


def _command_dump(command: RegisteredCommand) -> dict[str, Any]:
    return {
        "id": command.id,
        "trigger": command.trigger,
        "aliases": list(command.aliases),
        "description": command.description,
        "enabled": command.enabled,
        "allowed_users": list(command.allowed_users),
        "allowed_rooms": list(command.allowed_rooms),
        "progress": command.progress,
        "handler": _handler_dump(command.handler),
    }


class CommandRegistry:
    """Persistent exact-match registry for explicit Matrix commands."""

    def __init__(self, stored: Mapping[str, Any] | None = None, *, store: Any = None) -> None:
        self._items: dict[str, RegisteredCommand] = {}
        self._phrases: dict[str, str] = {}
        self._store = store
        if isinstance(stored, Mapping):
            raw_commands = stored.get("commands", [])
            if isinstance(raw_commands, Sequence) and not isinstance(raw_commands, (str, bytes)):
                for raw in raw_commands:
                    if not isinstance(raw, Mapping):
                        continue
                    try:
                        self.register(raw)
                    except ValueError:
                        continue

    @property
    def count(self) -> int:
        return len(self._items)

    def register(self, definition: Mapping[str, Any]) -> RegisteredCommand:
        if not isinstance(definition, Mapping):
            raise ValueError("command definition must be an object")
        command = _command_definition(definition)
        phrases = (command.trigger, *command.aliases)

        for phrase in phrases:
            existing_id = self._phrases.get(phrase)
            if existing_id is not None and existing_id != command.id:
                raise ValueError(f"duplicate command phrase: {phrase}")

        old = self._items.get(command.id)
        if old is not None:
            for phrase in (old.trigger, *old.aliases):
                if self._phrases.get(phrase) == command.id:
                    self._phrases.pop(phrase, None)

        self._items[command.id] = command
        for phrase in phrases:
            self._phrases[phrase] = command.id
        return command

    def unregister(self, command_id: str) -> bool:
        command = self._items.pop(str(command_id).strip(), None)
        if command is None:
            return False
        for phrase in (command.trigger, *command.aliases):
            if self._phrases.get(phrase) == command.id:
                self._phrases.pop(phrase, None)
        return True

    def match(
        self,
        body: str,
        *,
        sender: str | None,
        room_id: str,
    ) -> RegisteredCommand | None:
        raw = str(body)
        if not raw.lstrip().startswith("!"):
            return None
        normalized = normalize_command_phrase(raw)
        command_id = self._phrases.get(normalized)
        command = self._items.get(command_id) if command_id else None
        if command is None or not command.enabled:
            return None
        if command.allowed_users and sender not in command.allowed_users:
            return None
        if command.allowed_rooms and room_id not in command.allowed_rooms:
            return None
        return command

    def dump(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "commands": [
                _command_dump(command)
                for command in self._items.values()
            ]
        }

    async def async_save(self) -> None:
        if self._store is not None:
            await self._store.async_save(self.dump())
