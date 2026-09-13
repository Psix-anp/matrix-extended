"""Execution engine for pre-registered Matrix Extended safe commands."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .commands import (
    CameraSnapshotCommandHandler,
    RegisteredCommand,
    ServiceCommandHandler,
)
from .content import build_edit_content, build_media_content, build_reply_content

_SECRET_RE = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:token|password|secret)[a-z0-9_-]*)\s*[:=]\s*[^\s,;]+"
)
_MAX_ERROR_CHARS = 200


@dataclass(slots=True, frozen=True)
class CommandExecutionResult:
    """Bounded execution outcome exposed to receiver diagnostics."""

    command_id: str
    status: str
    handler_type: str
    error: str | None = None


def _handler_type(command: RegisteredCommand) -> str:
    if isinstance(command.handler, ServiceCommandHandler):
        return "service"
    if isinstance(command.handler, CameraSnapshotCommandHandler):
        return "camera_snapshot"
    return "unknown"


def _safe_error(error: Exception) -> str:
    """Return a one-line bounded error with obvious secrets removed."""
    summary = " ".join(str(error).split())
    summary = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", summary)
    if not summary:
        summary = error.__class__.__name__
    return summary[:_MAX_ERROR_CHARS]


class CommandExecutor:
    """Execute only already validated, pre-registered command definitions."""

    def __init__(self, hass: Any, account: Any) -> None:
        self._hass = hass
        self._account = account

    async def _send_progress(
        self,
        *,
        room_id: str,
        source_event_id: str,
        thread_id: str | None,
    ) -> tuple[Any, str | None]:
        rooms = await self._account.client.async_prepare_rooms([room_id])
        event_ids = await self._account.client.async_send_prepared(
            rooms,
            build_reply_content(
                "⏳ Running…",
                reply_to=source_event_id,
                thread_id=thread_id,
            ),
        )
        return rooms[0], event_ids[0]

    async def _edit_progress(
        self,
        room: Any,
        progress_event_id: str,
        message: str,
    ) -> None:
        await self._account.client.async_send_prepared(
            [room],
            build_edit_content(message, event_id=progress_event_id),
        )

    async def _send_camera_snapshot(
        self,
        handler: CameraSnapshotCommandHandler,
        *,
        room_id: str,
        thread_id: str | None,
        prepared_room: Any | None = None,
    ) -> None:
        """Resolve the pre-registered camera and send one Matrix image."""
        # Local import keeps service-only command execution independent from
        # Home Assistant media/camera runtime imports.
        from .media import MediaResolver

        media = await MediaResolver(self._hass).async_resolve(
            {"entity_id": handler.entity_id, "type": "image"}
        )
        room = prepared_room
        if room is None:
            room = (await self._account.client.async_prepare_rooms([room_id]))[0]

        upload = await self._account.client.async_upload(
            media.data,
            filename=media.filename,
            content_type=media.content_type,
            encrypt=bool(room.encrypted),
        )
        content = build_media_content(
            media_type="image",
            mxc_uri=None if room.encrypted else upload.mxc_uri,
            encrypted_file=upload.encrypted_file if room.encrypted else None,
            filename=media.filename,
            content_type=media.content_type,
            size=media.size,
            caption=handler.caption,
            width=media.width,
            height=media.height,
            duration_ms=getattr(media, "duration_ms", None),
            thread_id=thread_id,
        )
        await self._account.client.async_send_prepared([room], content)

    async def async_execute(
        self,
        command: RegisteredCommand,
        *,
        room_id: str,
        sender: str,
        source_event_id: str,
        thread_id: str | None,
    ) -> CommandExecutionResult:
        """Execute one exact stored command without using Matrix text as arguments."""
        del sender  # authorization happened before execution; retained for audit API stability.
        handler_type = _handler_type(command)
        progress_room = None
        progress_event_id: str | None = None

        try:
            if command.progress:
                progress_room, progress_event_id = await self._send_progress(
                    room_id=room_id,
                    source_event_id=source_event_id,
                    thread_id=thread_id,
                )

            if isinstance(command.handler, ServiceCommandHandler):
                domain, service = command.handler.service.split(".", 1)
                await self._hass.services.async_call(
                    domain,
                    service,
                    dict(command.handler.data),
                    blocking=True,
                    target=dict(command.handler.target) or None,
                )
            elif isinstance(command.handler, CameraSnapshotCommandHandler):
                await self._send_camera_snapshot(
                    command.handler,
                    room_id=room_id,
                    thread_id=thread_id,
                    prepared_room=progress_room,
                )
            else:  # pragma: no cover - registry validation prevents this.
                raise RuntimeError("unsupported command handler")
        except Exception as err:  # execution failure is represented, not leaked.
            safe_error = _safe_error(err)
            if progress_room is not None and progress_event_id:
                try:
                    await self._edit_progress(
                        progress_room,
                        progress_event_id,
                        f"❌ Failed: {safe_error}",
                    )
                except Exception:
                    pass
            return CommandExecutionResult(
                command_id=command.id,
                status="failed",
                handler_type=handler_type,
                error=safe_error,
            )

        if progress_room is not None and progress_event_id:
            await self._edit_progress(progress_room, progress_event_id, "✅ Done")
        return CommandExecutionResult(
            command_id=command.id,
            status="success",
            handler_type=handler_type,
            error=None,
        )
