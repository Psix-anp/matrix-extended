"""Opt-in automatic native Matrix voice -> Home Assistant Assist bridge."""

from __future__ import annotations

from dataclasses import dataclass
import mimetypes
import re
from typing import Any, Mapping

from .const import (
    CONF_VOICE_ASSIST_ALLOWED_ROOMS,
    CONF_VOICE_ASSIST_ALLOWED_USERS,
    CONF_VOICE_ASSIST_CONVERSATION_AGENT,
    CONF_VOICE_ASSIST_ENABLED,
    CONF_VOICE_ASSIST_LANGUAGE,
    CONF_VOICE_ASSIST_REPLY_MODE,
    CONF_VOICE_ASSIST_STT_ENTITY,
    CONF_VOICE_ASSIST_TTS_ENTITY,
    EVENT_VOICE_ASSIST,
)
from .content import build_media_content, build_reply_content

_SECRET_RE = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:token|password|secret)[a-z0-9_-]*)\s*[:=]\s*[^\s,;]+"
)
_MAX_ERROR_CHARS = 200
_REPLY_MODES = {"text", "voice", "both"}


def _list(value: Any) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return tuple(str(item).strip() for item in values if str(item).strip())


def _safe_error(error: Exception) -> str:
    summary = " ".join(str(error).split()) or error.__class__.__name__
    summary = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", summary)
    return summary[:_MAX_ERROR_CHARS]


@dataclass(slots=True, frozen=True)
class VoiceAssistSettings:
    """Per-entry automatic voice Assist policy."""

    enabled: bool = False
    stt_entity: str | None = None
    language: str | None = None
    conversation_agent: str | None = None
    reply_mode: str = "text"
    tts_entity: str | None = None
    allowed_users: tuple[str, ...] = ()
    allowed_rooms: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "VoiceAssistSettings":
        data = value or {}
        reply_mode = str(data.get(CONF_VOICE_ASSIST_REPLY_MODE) or "text")
        if reply_mode not in _REPLY_MODES:
            reply_mode = "text"
        return cls(
            enabled=bool(data.get(CONF_VOICE_ASSIST_ENABLED, False)),
            stt_entity=str(data[CONF_VOICE_ASSIST_STT_ENTITY]).strip()
            if data.get(CONF_VOICE_ASSIST_STT_ENTITY)
            else None,
            language=str(data[CONF_VOICE_ASSIST_LANGUAGE]).strip()
            if data.get(CONF_VOICE_ASSIST_LANGUAGE)
            else None,
            conversation_agent=str(data[CONF_VOICE_ASSIST_CONVERSATION_AGENT]).strip()
            if data.get(CONF_VOICE_ASSIST_CONVERSATION_AGENT)
            else None,
            reply_mode=reply_mode,
            tts_entity=str(data[CONF_VOICE_ASSIST_TTS_ENTITY]).strip()
            if data.get(CONF_VOICE_ASSIST_TTS_ENTITY)
            else None,
            allowed_users=_list(data.get(CONF_VOICE_ASSIST_ALLOWED_USERS)),
            allowed_rooms=_list(data.get(CONF_VOICE_ASSIST_ALLOWED_ROOMS)),
        )

    def allows(self, *, sender: str, room_id: str, media_payload: Mapping[str, Any]) -> bool:
        """Fail closed unless this is an eligible downloaded native voice event."""
        if not self.enabled:
            return False
        if not bool(media_payload.get("voice")):
            return False
        local_path = media_payload.get("local_path")
        if not local_path or media_payload.get("download_error"):
            return False
        if self.allowed_users and sender not in self.allowed_users:
            return False
        if self.allowed_rooms and room_id not in self.allowed_rooms:
            return False
        return True


def settings_for_entry(hass: Any, entry_id: str) -> VoiceAssistSettings:
    """Read merged config-entry data/options without making receiver setup brittle in tests."""
    config_entries = getattr(hass, "config_entries", None)
    getter = getattr(config_entries, "async_get_entry", None)
    if not callable(getter):
        return VoiceAssistSettings()
    entry = getter(entry_id)
    if entry is None:
        return VoiceAssistSettings()
    merged = dict(getattr(entry, "data", {}) or {})
    merged.update(dict(getattr(entry, "options", {}) or {}))
    return VoiceAssistSettings.from_mapping(merged)


def _assist_speech(assist: Mapping[str, Any] | None) -> str:
    if not isinstance(assist, Mapping):
        return "Done"
    response = assist.get("response")
    if not isinstance(response, Mapping):
        return "Done"
    speech = response.get("speech")
    if not isinstance(speech, Mapping):
        return "Done"
    plain = speech.get("plain")
    if not isinstance(plain, Mapping):
        return "Done"
    value = str(plain.get("speech") or "").strip()
    return value or "Done"


class VoiceAssistCoordinator:
    """Run STT/Assist outside the nio sync callback and answer in Matrix."""

    def __init__(self, hass: Any, account: Any, *, entry_id: str) -> None:
        self._hass = hass
        self._account = account
        self._entry_id = entry_id
        self.settings = settings_for_entry(hass, entry_id)

    def allows(self, *, sender: str, room_id: str, media_payload: Mapping[str, Any]) -> bool:
        return self.settings.allows(
            sender=sender, room_id=room_id, media_payload=media_payload
        )

    def _fire(
        self,
        *,
        room_id: str,
        sender: str,
        status: str,
        transcript: str | None = None,
        conversation_id: str | None = None,
        error: str | None = None,
    ) -> None:
        self._hass.bus.async_fire(
            EVENT_VOICE_ASSIST,
            {
                "account_id": self._entry_id,
                "room_id": room_id,
                "sender": sender,
                "status": status,
                "transcript": transcript,
                "conversation_id": conversation_id,
                "error": error,
            },
        )

    async def _send_text_reply(
        self,
        *,
        room: Any,
        source_event_id: str,
        thread_id: str | None,
        message: str,
    ) -> None:
        await self._account.client.async_send_prepared(
            [room],
            build_reply_content(
                message,
                reply_to=source_event_id,
                thread_id=thread_id,
            ),
        )

    async def _send_voice_reply(
        self,
        *,
        room: Any,
        thread_id: str | None,
        text: str,
    ) -> None:
        from homeassistant.components import tts  # noqa: PLC0415
        from homeassistant.components.tts.media_source import (  # noqa: PLC0415
            generate_media_source_id,
        )

        media_source_id = generate_media_source_id(
            self._hass,
            text,
            engine=self.settings.tts_entity,
            language=self.settings.language,
            options={},
            cache=True,
        )
        extension, audio = await tts.async_get_media_source_audio(
            self._hass, media_source_id
        )
        if not audio:
            raise RuntimeError("Home Assistant TTS returned empty audio")
        ext = str(extension or "mp3").lower().lstrip(".")
        content_type = mimetypes.types_map.get(f".{ext}", "audio/mpeg")
        filename = f"matrix-assist.{ext}"
        upload = await self._account.client.async_upload(
            audio,
            filename=filename,
            content_type=content_type,
            encrypt=bool(room.encrypted),
        )
        await self._account.client.async_send_prepared(
            [room],
            build_media_content(
                media_type="audio",
                mxc_uri=None if room.encrypted else upload.mxc_uri,
                encrypted_file=upload.encrypted_file if room.encrypted else None,
                filename=filename,
                content_type=content_type,
                size=len(audio),
                thread_id=thread_id,
                voice=True,
            ),
        )

    async def async_process(
        self,
        *,
        media_payload: Mapping[str, Any],
        sender: str,
        room_id: str,
        source_event_id: str,
        thread_id: str | None,
    ) -> None:
        """Process one eligible native Matrix voice message and contain failures."""
        if not self.allows(sender=sender, room_id=room_id, media_payload=media_payload):
            return
        transcript: str | None = None
        try:
            # STT/Conversation dependencies are intentionally lazy: receiver import
            # remains lightweight, and these modules load only for admitted native voice.
            from .voice_pipeline import async_process_voice_file  # noqa: PLC0415

            result = await async_process_voice_file(
                self._hass,
                self._account,
                path=str(media_payload["local_path"]),
                stt_entity=self.settings.stt_entity,
                language=self.settings.language,
                assist=True,
                conversation_agent=self.settings.conversation_agent,
            )
            transcript = result.text
            message = _assist_speech(result.assist)
            room = (await self._account.client.async_prepare_rooms([room_id]))[0]
            text_sent = False
            if self.settings.reply_mode in {"text", "both"}:
                await self._send_text_reply(
                    room=room,
                    source_event_id=source_event_id,
                    thread_id=thread_id,
                    message=message,
                )
                text_sent = True

            tts_error: str | None = None
            if self.settings.reply_mode in {"voice", "both"}:
                try:
                    await self._send_voice_reply(
                        room=room,
                        thread_id=thread_id,
                        text=message,
                    )
                except Exception as err:
                    tts_error = _safe_error(err)
                    if not text_sent:
                        await self._send_text_reply(
                            room=room,
                            source_event_id=source_event_id,
                            thread_id=thread_id,
                            message=message,
                        )
            conversation_id = None
            if isinstance(result.assist, Mapping):
                raw_conversation_id = result.assist.get("conversation_id")
                if raw_conversation_id:
                    conversation_id = str(raw_conversation_id)
            self._account.status.mark_send_success()
            self._fire(
                room_id=room_id,
                sender=sender,
                status="succeeded",
                transcript=transcript,
                conversation_id=conversation_id,
                error=tts_error,
            )
        except Exception as err:
            safe_error = _safe_error(err)
            self._account.status.mark_error(f"Voice Assist: {safe_error}")
            self._fire(
                room_id=room_id,
                sender=sender,
                status="failed",
                transcript=transcript,
                error=safe_error,
            )
