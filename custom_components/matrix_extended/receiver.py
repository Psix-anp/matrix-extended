"""Inbound Matrix event bridge for Matrix Extended."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from nio import (
    ReactionEvent,
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
    RoomMessageVideo,
)

from homeassistant.core import HomeAssistant

from .client import MatrixAccount, MatrixExtendedError
from .const import (
    EVENT_MEDIA,
    EVENT_MESSAGE,
    EVENT_REACTION,
    EVENT_REPLY,
    MAX_INCOMING_MEDIA_BYTES,
)
from .incoming import extract_relations, safe_filename

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
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._account = account
        self._incoming_dir = Path(incoming_dir)
        self._download_media = download_media

    def register(self) -> None:
        """Register all supported callbacks before starting live sync."""
        self._account.client.add_event_callback(self.async_handle_text, _TEXT_EVENTS)
        self._account.client.add_event_callback(self.async_handle_reaction, ReactionEvent)
        self._account.client.add_event_callback(self.async_handle_media, _MEDIA_EVENTS)

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

    def _base_payload(self, room: Any, event: Any) -> dict[str, Any]:
        reply_to, thread_id = extract_relations(event.source)
        return {
            "account_id": self._entry_id,
            "room_id": room.room_id,
            "sender": event.sender,
            "event_id": event.event_id,
            "timestamp": event.server_timestamp,
            "encrypted": bool(getattr(event, "decrypted", False)),
            "verified": bool(getattr(event, "verified", False)),
            "reply_to": reply_to,
            "thread_id": thread_id,
        }

    async def async_handle_text(self, room: Any, event: Any) -> None:
        """Forward authorized text/notices/emotes into the HA event bus."""
        if not self._allowed(room, event):
            return
        payload = self._base_payload(room, event)
        payload.update(
            {
                "message": getattr(event, "body", ""),
                "formatted_body": getattr(event, "formatted_body", None),
            }
        )
        event_type = EVENT_REPLY if payload["reply_to"] else EVENT_MESSAGE
        self._account.status.mark_receive()
        self._hass.bus.async_fire(event_type, payload)

    async def async_handle_reaction(self, room: Any, event: Any) -> None:
        """Fire reaction events and execute only pre-registered one-shot actions."""
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
        self._account.status.mark_receive()
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
                "media_type": media_type,
                "filename": filename,
                "content_type": info.get("mimetype") or getattr(event, "mimetype", None),
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
                if response_filename and filename == "matrix-media.bin":
                    filename = safe_filename(response_filename)
                    payload["filename"] = filename
                if payload["content_type"] is None:
                    payload["content_type"] = response_type
                prefix = sha256(event.event_id.encode()).hexdigest()[:12]
                destination = self._incoming_dir / f"{prefix}-{filename}"
                await self._hass.async_add_executor_job(destination.write_bytes, data)
                payload["local_path"] = str(destination)
            except (MatrixExtendedError, OSError, ValueError, KeyError) as err:
                payload["download_error"] = str(err)
        self._account.status.mark_receive()
        self._hass.bus.async_fire(EVENT_MEDIA, payload)

    async def async_listener_error(self, error: Exception) -> None:
        """Expose background sync failures without crashing the integration."""
        self._account.status.mark_error(f"Matrix sync: {error}")
