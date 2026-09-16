#!/usr/bin/env python3
"""Real-stack Native Matrix Control E2E helpers and driver."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

PANEL_METADATA_KEY = "io.psix.matrix_extended.panel"
PANEL_SCHEMA = 1


def _content(event: Mapping[str, Any]) -> Mapping[str, Any]:
    content = event.get("content")
    return content if isinstance(content, Mapping) else {}


def find_panel_root(
    events: Iterable[Mapping[str, Any]],
    *,
    panel_id: str,
    sender: str,
) -> Mapping[str, Any]:
    """Find one decrypted panel root from the expected Matrix sender."""
    for event in events:
        if event.get("type") != "m.room.message" or event.get("sender") != sender:
            continue
        marker = _content(event).get(PANEL_METADATA_KEY)
        if (
            isinstance(marker, Mapping)
            and marker.get("schema") == PANEL_SCHEMA
            and marker.get("panel_id") == panel_id
        ):
            return event
    raise LookupError(f"no panel root for {panel_id} from {sender}")


def is_panel_edit(event: Mapping[str, Any], root_event_id: str) -> bool:
    """Return whether one decrypted event edits the original panel root."""
    if event.get("type") != "m.room.message":
        return False
    relation = _content(event).get("m.relates_to")
    return (
        isinstance(relation, Mapping)
        and relation.get("rel_type") == "m.replace"
        and relation.get("event_id") == root_event_id
    )


def find_confirmation_reply(
    events: Iterable[Mapping[str, Any]],
    *,
    root_event_id: str,
    action_label: str,
    sender: str,
) -> Mapping[str, Any]:
    """Find the same-root dangerous-action confirmation reply."""
    expected = f"⚠️ Confirm: {action_label}"
    for event in events:
        if event.get("type") != "m.room.message" or event.get("sender") != sender:
            continue
        content = _content(event)
        if content.get("body") != expected:
            continue
        relation = content.get("m.relates_to")
        if not isinstance(relation, Mapping):
            continue
        reply = relation.get("m.in_reply_to")
        if isinstance(reply, Mapping) and reply.get("event_id") == root_event_id:
            return event
    raise LookupError(
        f"no confirmation reply for {action_label} bound to {root_event_id}"
    )


def main() -> int:
    """Runtime modes are added after the pure helper contract is green."""
    raise SystemExit("matrix-control-e2e runtime driver is not implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
