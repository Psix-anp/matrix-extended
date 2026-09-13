"""Pure helpers for Matrix delivery lifecycle reporting."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_DELIVERY_STATUSES = {"sent", "queued", "failed", "dropped"}
_DELIVERY_KINDS = {"text", "media"}


def delivery_event_record(
    *,
    room_id: str,
    event_id: str,
    kind: str,
    media_index: int | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe record describing one delivered Matrix event."""
    if kind not in _DELIVERY_KINDS:
        raise ValueError("delivery event kind must be text or media")
    if not room_id or not event_id:
        raise ValueError("delivery event requires room_id and event_id")
    if kind == "text" and media_index is not None:
        raise ValueError("media_index is only valid for media delivery events")
    if kind == "media":
        if not isinstance(media_index, int) or media_index < 0:
            raise ValueError("media_index must be a non-negative integer for media events")

    result: dict[str, Any] = {
        "room_id": room_id,
        "event_id": event_id,
        "kind": kind,
    }
    if media_index is not None:
        result["media_index"] = media_index
    return result


def delivery_lifecycle_payload(
    *,
    account_id: str,
    delivery_id: str,
    status: str,
    events: Iterable[Mapping[str, Any]] = (),
    error: str | None = None,
) -> dict[str, Any]:
    """Build the Home Assistant delivery lifecycle payload."""
    if status not in _DELIVERY_STATUSES:
        raise ValueError("delivery status must be sent, queued, failed, or dropped")
    if not account_id or not delivery_id:
        raise ValueError("delivery lifecycle requires account_id and delivery_id")
    return {
        "account_id": account_id,
        "delivery_id": delivery_id,
        "status": status,
        "events": [dict(event) for event in events],
        "error": error,
    }
