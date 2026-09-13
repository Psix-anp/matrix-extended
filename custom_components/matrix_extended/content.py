"""Pure helpers for Matrix event content."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

MediaType = Literal["image", "video", "audio", "file"]
SOURCE_KEYS = ("path", "url", "entity_id", "media_source")


def _thread_relation(thread_id: str | None) -> dict[str, Any]:
    if not thread_id:
        return {}
    return {"m.relates_to": {"event_id": thread_id, "rel_type": "m.thread"}}


def build_text_content(
    body: str,
    *,
    formatted_body: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build m.text content, optionally with HTML and a thread relation."""
    content: dict[str, Any] = {"msgtype": "m.text", "body": body}
    if formatted_body is not None:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = formatted_body
    content.update(_thread_relation(thread_id))
    return content


def _relation(
    *,
    reply_to: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    relation: dict[str, Any] = {}
    if thread_id:
        relation.update({"event_id": thread_id, "rel_type": "m.thread"})
    if reply_to:
        relation["m.in_reply_to"] = {"event_id": reply_to}
    return {"m.relates_to": relation} if relation else {}


def build_reply_content(
    body: str,
    *,
    reply_to: str,
    formatted_body: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build a text reply, optionally inside a Matrix thread."""
    content: dict[str, Any] = {"msgtype": "m.text", "body": body}
    if formatted_body is not None:
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = formatted_body
    content.update(_relation(reply_to=reply_to, thread_id=thread_id))
    return content


def build_edit_content(
    body: str,
    *,
    event_id: str,
    formatted_body: str | None = None,
) -> dict[str, Any]:
    """Build an m.replace edit for a text message."""
    new_content: dict[str, Any] = {"msgtype": "m.text", "body": body}
    content: dict[str, Any] = {
        "msgtype": "m.text",
        "body": f"* {body}",
        "m.new_content": new_content,
        "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
    }
    if formatted_body is not None:
        new_content["format"] = "org.matrix.custom.html"
        new_content["formatted_body"] = formatted_body
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = f"* {formatted_body}"
    return content


def build_reaction_content(event_id: str, key: str) -> dict[str, Any]:
    """Build a Matrix m.reaction annotation event."""
    if not key:
        raise ValueError("reaction key must not be empty")
    return {
        "m.relates_to": {
            "rel_type": "m.annotation",
            "event_id": event_id,
            "key": key,
        }
    }


def infer_media_type(content_type: str | None) -> MediaType:
    """Infer a Matrix media msgtype from a MIME type."""
    if content_type:
        top_level = content_type.split("/", 1)[0].lower()
        if top_level in {"image", "video", "audio"}:
            return cast(MediaType, top_level)
    return "file"


def validate_media_size(size: int, max_bytes: int) -> int:
    """Validate a resolved attachment size."""
    if size < 0:
        raise ValueError("media size cannot be negative")
    if size > max_bytes:
        raise ValueError(
            f"attachment is too large ({size} bytes); limit is {max_bytes}"
        )
    return size


def validate_media_item_shape(item: Mapping[str, Any]) -> dict[str, Any]:
    """Validate that a media item has exactly one supported source."""
    if not isinstance(item, Mapping):
        raise ValueError("media item must be an object")
    sources = [key for key in SOURCE_KEYS if item.get(key) not in (None, "")]
    if len(sources) != 1:
        raise ValueError(
            "media item must contain exactly one source: path, url, entity_id, or media_source"
        )
    return dict(item)


def build_media_content(
    *,
    media_type: MediaType,
    mxc_uri: str | None = None,
    encrypted_file: Mapping[str, Any] | None = None,
    filename: str,
    content_type: str,
    size: int,
    caption: str | None = None,
    formatted_caption: str | None = None,
    width: int | None = None,
    height: int | None = None,
    duration_ms: int | None = None,
    voice: bool = False,
    waveform: Sequence[int] | None = None,
    thumbnail_mxc_uri: str | None = None,
    thumbnail_encrypted_file: Mapping[str, Any] | None = None,
    thumbnail_info: Mapping[str, Any] | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Build Matrix media content according to Client-Server API v1.10+."""
    if media_type not in {"image", "video", "audio", "file"}:
        raise ValueError(f"unsupported media type: {media_type}")
    if size < 0:
        raise ValueError("size cannot be negative")
    if voice and media_type != "audio":
        raise ValueError("voice metadata is only valid for m.audio")
    if waveform is not None and not voice:
        raise ValueError("waveform requires voice=true")
    if waveform is not None and any(sample < 0 or sample > 1024 for sample in waveform):
        raise ValueError("voice waveform values must be between 0 and 1024")
    if (mxc_uri is None) == (encrypted_file is None):
        raise ValueError("media content requires exactly one plain or encrypted source")
    if thumbnail_mxc_uri is not None and thumbnail_encrypted_file is not None:
        raise ValueError("thumbnail requires exactly one plain or encrypted source")
    if media_type == "audio" and (
        thumbnail_mxc_uri is not None or thumbnail_encrypted_file is not None
    ):
        raise ValueError("thumbnail metadata is not supported for m.audio")

    body = caption if caption is not None else filename
    content: dict[str, Any] = {
        "msgtype": f"m.{media_type}",
        "body": body,
        "info": {
            "mimetype": content_type,
            "size": size,
        },
    }
    if encrypted_file is not None:
        content["file"] = dict(encrypted_file)
    else:
        content["url"] = mxc_uri

    if caption is not None and caption != filename:
        content["filename"] = filename
    if formatted_caption is not None:
        content["filename"] = filename
        content["format"] = "org.matrix.custom.html"
        content["formatted_body"] = formatted_caption

    info = content["info"]
    if media_type in {"image", "video"}:
        if width is not None:
            info["w"] = width
        if height is not None:
            info["h"] = height
    if media_type in {"video", "audio"} and duration_ms is not None:
        info["duration"] = duration_ms

    if voice:
        content["org.matrix.msc3245.voice"] = {}
        audio_meta: dict[str, Any] = {}
        if duration_ms is not None:
            audio_meta["duration"] = duration_ms
        if waveform is not None:
            audio_meta["waveform"] = list(waveform)
        if audio_meta:
            content["org.matrix.msc1767.audio"] = audio_meta

    if thumbnail_encrypted_file is not None:
        info["thumbnail_file"] = dict(thumbnail_encrypted_file)
    elif thumbnail_mxc_uri is not None:
        info["thumbnail_url"] = thumbnail_mxc_uri
    if (thumbnail_mxc_uri is not None or thumbnail_encrypted_file is not None) and thumbnail_info is not None:
        info["thumbnail_info"] = dict(thumbnail_info)

    content.update(_thread_relation(thread_id))
    return content
