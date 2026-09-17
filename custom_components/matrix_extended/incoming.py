"""Pure helpers for inbound Matrix authorization and relations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class IncomingPolicy:
    """Allow only explicitly configured Matrix users and rooms."""

    __slots__ = ("allowed_users", "allowed_rooms")

    def __init__(
        self,
        *,
        allowed_users: Iterable[str],
        allowed_rooms: Iterable[str],
    ) -> None:
        self.allowed_users = frozenset(str(value) for value in allowed_users if value)
        self.allowed_rooms = frozenset(str(value) for value in allowed_rooms if value)

    def allows(self, sender: str, room_id: str) -> bool:
        """Return True only when both allowlists explicitly match."""
        return bool(
            self.allowed_users
            and self.allowed_rooms
            and sender in self.allowed_users
            and room_id in self.allowed_rooms
        )

    def should_process(
        self,
        *,
        sender: str,
        room_id: str,
        transaction_id: str | None,
    ) -> bool:
        """Reject echoes from this Matrix device and enforce allowlists."""
        if transaction_id:
            return False
        return self.allows(sender, room_id)


def redaction_target(event: Any) -> str | None:
    """Return the legacy matrix-nio redaction target when exposed directly."""
    direct = getattr(event, "redacts", None)
    return direct if isinstance(direct, str) and direct else None


def extract_relations(source: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Extract rich-reply parent and thread root IDs from event source."""
    content = source.get("content")
    if not isinstance(content, Mapping):
        return None, None
    relates = content.get("m.relates_to")
    if not isinstance(relates, Mapping):
        return None, None

    reply_to = None
    reply = relates.get("m.in_reply_to")
    if isinstance(reply, Mapping):
        candidate = reply.get("event_id")
        if isinstance(candidate, str):
            reply_to = candidate

    thread_id = None
    if relates.get("rel_type") == "m.thread":
        candidate = relates.get("event_id")
        if isinstance(candidate, str):
            thread_id = candidate
    return reply_to, thread_id


def extract_replacement(
    source: Mapping[str, Any],
) -> tuple[str | None, Mapping[str, Any] | None]:
    """Extract the replaced event ID and replacement content for m.replace."""
    content = source.get("content")
    if not isinstance(content, Mapping):
        return None, None
    relates = content.get("m.relates_to")
    if not isinstance(relates, Mapping) or relates.get("rel_type") != "m.replace":
        return None, None
    event_id = relates.get("event_id")
    new_content = content.get("m.new_content")
    if not isinstance(event_id, str) or not isinstance(new_content, Mapping):
        return None, None
    return event_id, new_content


def safe_filename(filename: str | None) -> str:
    """Return a path-safe filename without allowing directory traversal."""
    value = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if value in {"", ".", ".."}:
        return "matrix-media.bin"
    return value[:255]
