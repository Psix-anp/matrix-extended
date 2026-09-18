"""Execution core for preconfigured Matrix Extended safe actions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .safe_actions import (
    CameraSnapshotActionHandler,
    SafeActionDefinition,
    ServiceActionHandler,
)

_SECRET_RE = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:token|password|secret)[a-z0-9_-]*)\s*[:=]\s*[^\s,;]+"
)
_MAX_ERROR_CHARS = 200


@dataclass(slots=True, frozen=True)
class SafeActionExecutionContext:
    """Optional Matrix context required by handlers that emit Matrix output."""

    account: Any | None = None
    room_id: str | None = None
    thread_id: str | None = None
    prepared_room: Any | None = None


@dataclass(slots=True, frozen=True)
class SafeActionExecutionResult:
    """Bounded action execution result safe for diagnostics and Matrix replies."""

    action_id: str
    status: str
    handler_type: str
    error: str | None = None


def safe_error(error: Exception) -> str:
    """Return one bounded line with obvious credentials redacted."""
    summary = " ".join(str(error).split())
    summary = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", summary)
    if not summary:
        summary = error.__class__.__name__
    return summary[:_MAX_ERROR_CHARS]


def _handler_type(action: SafeActionDefinition) -> str:
    if isinstance(action.handler, ServiceActionHandler):
        return "service"
    if isinstance(action.handler, CameraSnapshotActionHandler):
        return "camera_snapshot"
    return "unknown"


class SafeActionExecutor:
    """Execute only already validated, preconfigured action definitions."""

    def __init__(self, hass: Any) -> None:
        self._hass = hass

    async def _async_camera_snapshot(
        self,
        handler: CameraSnapshotActionHandler,
        *,
        context: SafeActionExecutionContext,
    ) -> None:
        if context.account is None or not context.room_id:
            raise ValueError("camera_snapshot requires Matrix account and room context")

        from .content import build_media_content
        from .media import MediaResolver

        media = await MediaResolver(self._hass).async_resolve(
            {"entity_id": handler.entity_id, "type": "image"}
        )
        room = context.prepared_room
        if room is None:
            room = (
                await context.account.client.async_prepare_rooms([context.room_id])
            )[0]

        upload = await context.account.client.async_upload(
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
            thread_id=context.thread_id,
        )
        await context.account.client.async_send_prepared([room], content)

    async def async_execute(
        self,
        action: SafeActionDefinition,
        *,
        context: SafeActionExecutionContext | None = None,
    ) -> SafeActionExecutionResult:
        """Execute one stored action and return a bounded result."""
        handler_type = _handler_type(action)
        try:
            if isinstance(action.handler, ServiceActionHandler):
                domain, service = action.handler.service.split(".", 1)
                await self._hass.services.async_call(
                    domain,
                    service,
                    dict(action.handler.data),
                    blocking=True,
                    target=dict(action.handler.target) or None,
                )
            elif isinstance(action.handler, CameraSnapshotActionHandler):
                await self._async_camera_snapshot(
                    action.handler,
                    context=context or SafeActionExecutionContext(),
                )
            else:  # pragma: no cover - validation prevents unsupported handlers.
                raise ValueError("unsupported safe action handler")
        except Exception as err:
            return SafeActionExecutionResult(
                action_id=action.id,
                status="failed",
                handler_type=handler_type,
                error=safe_error(err),
            )

        return SafeActionExecutionResult(
            action_id=action.id,
            status="success",
            handler_type=handler_type,
            error=None,
        )
