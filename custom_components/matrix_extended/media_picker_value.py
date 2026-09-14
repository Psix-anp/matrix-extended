"""Pure normalization helpers for Home Assistant media selector output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def media_picker_to_media_item(
    value: Mapping[str, Any],
    *,
    caption: str | None = None,
    voice: bool = False,
) -> dict[str, Any]:
    """Convert native HA media-selector output to the existing media resolver shape."""
    media_content_id = value.get("media_content_id")
    if not isinstance(media_content_id, str) or not media_content_id.strip():
        raise ValueError("media picker result has no media_content_id")
    item: dict[str, Any] = {
        "media_source": media_content_id.strip(),
        "type": "auto",
    }
    if caption:
        item["caption"] = caption
    if voice:
        item["voice"] = True
    return item
