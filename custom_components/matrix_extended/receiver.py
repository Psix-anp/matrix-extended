"""Inbound Matrix event bridge for Matrix Extended."""

from __future__ import annotations

from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

from nio import (
    ReactionEvent,
    RedactionEvent,
    RoomEncryptedAudio,
    RoomEncryptedFile,
    RoomEncryptedImage,
    RoomEncryptedVideo,
    RoomMessageAudio,
    RoomMessageEmote,
    RoomMessageFile,
    RoomMessageImage,
    RoomMessageNotice,
    RoomMessageText,
    RoomMessageUnknown,
    RoomMessageVideo,
)

from homeassistant.core import HomeAssistant

from .client import MatrixAccount, MatrixExtendedError
from .const import (
    DEFAULT_INCOMING_MEDIA_MAX_MB,
    DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
    EVENT_EDIT,
    EVENT_LOCATION,
    EVENT_MEDIA,
    EVENT_MESSAGE,
    EVENT_REACTION,
    EVENT_REDACTION,
    EVENT_REPLY,
    MAX_INCOMING_MEDIA_BYTES,
)
from .incoming import extract_relations, extract_replacement, safe_filename
from .retention import cleanup_media_directory

_TEXT_EVENTS = (RoomMessageText, RoomMessageNotice, RoomMessageEmote)
_MEDIA_EVENTS = (
    RoomMessageImage,
    RoomMessageAudio,
    RoomMessageVideo,
    RoomMessageFile,
    RoomEncryptedImage,
    RoomEncryptedAudio,
    RoomEncryptedVideo,
    RoomEncryptedFile,
)


def _msgtype(content: Any) -> str | None:
    if not isinstance(content, dict):
        return None
    value = content.get("msgtype")
    if not isinstance(value, str):
        return None
    return value.removeprefix("m.")


def _parse_geo_uri(value: Any) -> tuple[float, float] | None:
    """Parse the stable Matrix geo URI subset used by m.location."""
    if not isinstance(value, str) or not value.startswith("geo:"):
        return None
    coordinates = value[4:].split(";", 1)[0].split(",")
    if len(coordinates) < 2:
        return None
    try:
        latitude = float(coordinates[0])
        longitude = float(coordinates[1])
    except ValueError:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


class MatrixInboundReceiver:
    """Translate authorized matrix-nio callbacks into Home Assistant events."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry_id: str,
        account: MatrixAccount,
        incoming_dir: str,
        download_media: bool,
        media_retention_days: int = DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
        media_max_bytes: int = DEFAULT_INCOMING_MEDIA_MAX_MB * 1024 * 1024,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._account = account
        self._incoming_dir = Path(incoming_dir)
        self._download_media = download_media
        self._media_retention_days = int(media_retention_days)
        self._media_max_bytes = int(media_max_bytes)

    def register(self) -> None:
        """Register all supported callbacks before starting live sync."""
        self._account.client.add_event_callback(self.async_handle_text, _TEXT_EVENTS)
        self._account.client.add_event_callback(self.async_handle_reaction, ReactionEvent)
        self._account.client.add_event_callback(self.async_handle_media, _MEDIA_EVENTS)
        self._account.client.add_event_callback(self.async_handle_redaction, RedactionEvent)
        # matrix-nio 0.26 maps unsupported m.room.message msgtypes such as
        # stable m.location to RoomMessageUnknown.
        self._account.client.add_event_callback(
            self.async_handle_location, RoomMessageUnknown
        )

    def _allowed(self, room: Any, event: Any) -> bool:
        policy = self._account.incoming_policy
        return bool(
            policy
            and policy.should_process(
                sender=event.sender,
                room_id=room.room_id,
                transaction_id=getattr(event, "transaction_id", None),
            )
        )

    def _mark_receive(self, event_type: str, payload: dict[str, Any]) -> None:
        """Record rich inbound metadata while retaining the legacy timestamp API."""
        rich_marker = getattr(self._account.status, "mark_receive_event", None)
        if callable(rich_marker):
            rich_marker(event_type, payload)
            return
        self._account.status.mark_receive()

    def _base_payload(self, room: Any, event: Any) -> dict[str, Any]:
        reply_to, thread_id = extract_relations(event.source)
        sender_display_name = None
        user_name = getattr(room, "user_name", None)
        if callable(user_name):
            try:
                sender_display_name = user_name(event.sender)
            except (KeyError, TypeError, ValueError):
                sender_display_name = None
        content = event.source.get("content", {}) if isinstance(event.source, dict) else {}
        return {
            "account_id": self._entry_id,
            "room_id": room.room_id,
            "room_name": getattr(room, "display_name", None),
            "canonical_alias": getattr(room, "canonical_alias", None),
            "sender": event.sender,
            "sender_display_name": sender_display_name,
            "event_id": event.event_id,
            "timestamp": event.server_timestamp,
            "encrypted": bool(getattr(event, "decrypted", False)),
            "verified": bool(getattr(event, "verified", False)),
            "reply_to": reply_to,
            "thread_id": thread_id,
            "msgtype": _msgtype(content),
        }

    async def async_handle_text(self, room: Any, event: Any) -> None:
        """Forward authorized text/notices/emotes, replies, and edits to HA."""
        if not self._allowed(room, event):
            return
        payload = self._base_payload(room, event)
        replaces, new_content = extract_replacement(event.source)
        if replaces and new_content is not None:
            payload.update(
                {
                    "replaces": replaces,
                    "message": str(new_content.get("body", "")),
                    "formatted_body": new_content.get("formatted_body"),
                    "msgtype": _msgtype(dict(new_content)) or "other",
                }
            )
            event_type = EVENT_EDIT
            event_kind = "edit"
        else:
            payload.update(
                {
                    "message": getattr(event, "body", ""),
                    "formatted_body": getattr(event, "formatted_body", None),
                }
            )
            is_reply = bool(payload["reply_to"])
            event_type = EVENT_REPLY if is_reply else EVENT_MESSAGE
            event_kind = "reply" if is_reply else "message"
        self._mark_receive(event_kind, payload)
        self._hass.bus.async_fire(event_type, payload)

    async def async_handle_reaction(self, room: Any, event: Any) -> None:
        """Fire reaction events and execute only pre-registered actions."""
        if not self._allowed(room, event):
            return
        payload = self._base_payload(room, event)
        payload.update(
            {
                "reaction": event.key,
                "reacts_to": event.reacts_to,
                "action_executed": False,
            }
        )
        registry = self._account.action_registry
        action = (
            registry.consume(
                room_id=room.room_id,
                event_id=event.reacts_to,
                reaction=event.key,
                sender=event.sender,
            )
            if registry
            else None
        )
        if action is not None:
            await registry.async_save()
            domain, service = action.service.split(".", 1)
            await self._hass.services.async_call(
                domain,
                service,
                action.data,
                blocking=False,
                target=action.target or None,
            )
            payload["action_executed"] = True
            payload["action_service"] = action.service
        self._mark_receive("reaction", payload)
        self._hass.bus.async_fire(EVENT_REACTION, payload)

    async def async_handle_media(self, room: Any, event: Any) -> None:
        """Download/decrypt authorized media and fire a Matrix media event."""
        if not self._allowed(room, event):
            return
        payload = self._base_payload(room, event)
        content = event.source.get("content", {})
        info = content.get("info") if isinstance(content.get("info"), dict) else {}
        encrypted_file = content.get("file") if isinstance(content.get("file"), dict) else None
        mxc_uri = encrypted_file.get("url") if encrypted_file else content.get("url")
        msgtype = str(content.get("msgtype", "m.file"))
        media_type = msgtype.removeprefix("m.")
        filename = safe_filename(content.get("filename") or getattr(event, "body", None))
        payload.update(
            {
                "msgtype": media_type,
                "media_type": media_type,
                "voice": "org.matrix.msc3245.voice" in content,
                "filename": filename,
                "content_type": info.get("mimetype") or getattr(event, "mimetype", None),
                "size": info.get("size"),
                "width": info.get("w"),
                "height": info.get("h"),
                "duration_ms": info.get("duration"),
                "mxc_uri": mxc_uri,
                "caption": getattr(event, "body", None),
                "local_path": None,
                "download_error": None,
            }
        )
        if self._download_media and isinstance(mxc_uri, str):
            try:
                data, response_type, response_filename = await self._account.client.async_download_media(
                    mxc_uri, encrypted_file=encrypted_file
                )
                if len(data) > MAX_INCOMING_MEDIA_BYTES:
                    raise ValueError(
                        f"incoming media is too large ({len(data)} bytes); "
                        f"limit is {MAX_INCOMING_MEDIA_BYTES}"
                    )
                if len(data) > self._media_max_bytes:
                    raise ValueError(
                        f"incoming media exceeds configured storage limit "
                        f"({len(data)} > {self._media_max_bytes} bytes)"
                    )
                if response_filename and filename == "matrix-media.bin":
                    filename = safe_filename(response_filename)
                    payload["filename"] = filename
                if payload["content_type"] is None:
                    payload["content_type"] = response_type
                prefix = sha256(event.event_id.encode()).hexdigest()[:12]
                destination = self._incoming_dir / f"{prefix}-{filename}"
                await self._hass.async_add_executor_job(destination.write_bytes, data)
                await self._hass.async_add_executor_job(
                    partial(
                        cleanup_media_directory,
                        self._incoming_dir,
                        retention_days=self._media_retention_days,
                        max_bytes=self._media_max_bytes,
                    )
                )
                payload["local_path"] = str(destination)
            except (MatrixExtendedError, OSError, ValueError, KeyError) as err:
                payload["download_error"] = str(err)
        self._mark_receive("media", payload)
        self._hass.bus.async_fire(EVENT_MEDIA, payload)

    async def async_handle_location(self, room: Any, event: Any) -> None:
        """Forward stable m.location events represented as RoomMessageUnknown."""
        source = event.source if isinstance(event.source, dict) else {}
        content = source.get("content", {})
        if not isinstance(content, dict) or content.get("msgtype") != "m.location":
            return
        if not self._allowed(room, event):
            return
        parsed = _parse_geo_uri(content.get("geo_uri"))
        if parsed is None:
            return
        latitude, longitude = parsed
        payload = self._base_payload(room, event)
        payload.update(
            {
                "msgtype": "location",
                "latitude": latitude,
                "longitude": longitude,
                "geo_uri": content.get("geo_uri"),
                "description": str(content.get("body") or "Location"),
            }
        )
        self._mark_receive("location", payload)
        self._hass.bus.async_fire(EVENT_LOCATION, payload)

    async def async_handle_redaction(self, room: Any, event: Any) -> None:
        """Forward authorized m.room.redaction events into Home Assistant."""
        if not self._allowed(room, event):
            return
        payload = self._base_payload(room, event)
        payload.update(
            {
                "redacts": getattr(event, "redacts", None),
                "reason": getattr(event, "reason", None),
            }
        )
        self._mark_receive("redaction", payload)
        self._hass.bus.async_fire(EVENT_REDACTION, payload)

    async def async_listener_error(self, error: Exception) -> None:
        """Expose background sync failures without crashing the integration."""
        self._account.status.mark_error(f"Matrix sync: {error}")
