"""Room metadata helpers for Matrix Extended."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


class MatrixRoomInfo:
    """Stable room metadata exposed to Home Assistant entities."""

    __slots__ = ("room_id", "display_name", "canonical_alias", "encrypted", "joined_count")

    def __init__(
        self,
        room_id: str,
        display_name: str,
        canonical_alias: str | None,
        encrypted: bool,
        joined_count: int,
    ) -> None:
        self.room_id = room_id
        self.display_name = display_name
        self.canonical_alias = canonical_alias
        self.encrypted = encrypted
        self.joined_count = joined_count

    @property
    def machine_name(self) -> str:
        """Return the best Matrix target string for this room."""
        return self.canonical_alias or self.room_id


def room_info_from_nio(room: Any) -> MatrixRoomInfo:
    """Convert a matrix-nio MatrixRoom into stable serializable metadata."""
    room_id = str(room.room_id)
    display_name = str(getattr(room, "display_name", "") or "").strip() or room_id
    alias = getattr(room, "canonical_alias", None)
    canonical_alias = str(alias) if alias else None
    try:
        joined_count = int(getattr(room, "joined_count", 0) or 0)
    except (TypeError, ValueError):
        joined_count = 0
    return MatrixRoomInfo(
        room_id=room_id,
        display_name=display_name,
        canonical_alias=canonical_alias,
        encrypted=bool(getattr(room, "encrypted", False)),
        joined_count=joined_count,
    )


def build_room_labels(rooms: Iterable[MatrixRoomInfo]) -> dict[str, str]:
    """Build unique, human-readable HA select labels mapped to room IDs."""
    values = list(rooms)
    counts = Counter(room.display_name for room in values)
    result: dict[str, str] = {}
    for room in sorted(values, key=lambda item: (item.display_name.casefold(), item.room_id)):
        if counts[room.display_name] == 1:
            label = room.display_name
        else:
            label = f"{room.display_name} · {room.canonical_alias or room.room_id}"
        result[label] = room.room_id
    return result
