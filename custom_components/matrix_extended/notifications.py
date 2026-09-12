"""Persistent notification-key registry core for Matrix Extended."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class NotificationKeyRegistry:
    """Map a stable notification key to the original event in each Matrix room."""

    __slots__ = ("_items",)

    def __init__(self, stored: Mapping[str, Any] | None = None) -> None:
        self._items: dict[str, dict[str, str]] = {}
        if isinstance(stored, Mapping):
            for raw_key, raw_rooms in stored.items():
                key = str(raw_key).strip()
                if not key or not isinstance(raw_rooms, Mapping):
                    continue
                rooms: dict[str, str] = {}
                for raw_room, raw_event in raw_rooms.items():
                    room_id = str(raw_room).strip()
                    event_id = str(raw_event).strip()
                    if room_id and event_id:
                        rooms[room_id] = event_id
                if rooms:
                    self._items[key] = rooms

    @staticmethod
    def _key(value: str) -> str:
        key = str(value).strip()
        if not key:
            raise ValueError("notification_key cannot be blank")
        if len(key) > 128:
            raise ValueError("notification_key cannot exceed 128 characters")
        return key

    def get(self, key: str, room_id: str) -> str | None:
        """Return the original Matrix event ID for key+room, if known."""
        clean_key = self._key(key)
        return self._items.get(clean_key, {}).get(str(room_id))

    def set(self, key: str, room_id: str, event_id: str) -> None:
        """Store or replace the event mapping for key+room."""
        clean_key = self._key(key)
        room = str(room_id).strip()
        event = str(event_id).strip()
        if not room or not event:
            raise ValueError("notification_key mappings require room_id and event_id")
        self._items.setdefault(clean_key, {})[room] = event

    def dump(self) -> dict[str, dict[str, str]]:
        """Return a JSON-safe copy for Home Assistant Store."""
        return {key: dict(rooms) for key, rooms in self._items.items()}
