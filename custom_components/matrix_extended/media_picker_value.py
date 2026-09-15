"""Pure normalization helpers for Home Assistant media selector output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MEDIA_TYPES = {"auto", "image", "video", "audio", "file"}


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


def send_media_source_to_media_item(
    *,
    media_picker: Mapping[str, Any] | None = None,
    url: str | None = None,
    entity_id: str | None = None,
    media_type: str = "auto",
    filename: str | None = None,
    caption: str | None = None,
    voice: bool = False,
) -> dict[str, Any]:
    """Normalize one send_media source to the existing media resolver shape."""
    url_value = url.strip() if isinstance(url, str) else ""
    entity_value = entity_id.strip() if isinstance(entity_id, str) else ""
    sources = [
        media_picker is not None,
        bool(url_value),
        bool(entity_value),
    ]
    if sum(sources) != 1:
        raise ValueError(
            "send_media requires exactly one source: media_picker, url, or entity_id"
        )
    if media_type not in _MEDIA_TYPES:
        raise ValueError(f"unsupported media type: {media_type}")

    if media_picker is not None:
        item = media_picker_to_media_item(media_picker)
    elif url_value:
        item = {"url": url_value, "type": "auto"}
    else:
        item = {"entity_id": entity_value, "type": "auto"}

    item["type"] = media_type
    if filename:
        item["filename"] = filename
    if caption:
        item["caption"] = caption
    if voice:
        item["voice"] = True
    return item
