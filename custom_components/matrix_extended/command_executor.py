"""Execution engine for pre-registered Matrix Extended safe commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .commands import (
    CameraSnapshotCommandHandler,
    RegisteredCommand,
    ServiceCommandHandler,
)
from .content import build_edit_content, build_reply_content
from .safe_action_executor import (
    SafeActionExecutionContext,
    SafeActionExecutor,
    safe_error,
)
from .safe_actions import (
    CameraSnapshotActionHandler,
    SafeActionDefinition,
    ServiceActionHandler,
)


@dataclass(slots=True, frozen=True)
class CommandExecutionResult:
    """Bounded execution outcome exposed to receiver diagnostics."""

    command_id: str
    status: str
    handler_type: str
    error: str | None = None


def _to_safe_action(command: RegisteredCommand) -> SafeActionDefinition:
    """Adapt the persisted command schema to the shared safe-action model."""
    if isinstance(command.handler, ServiceCommandHandler):
        handler = ServiceActionHandler(
            service=command.handler.service,
            target=dict(command.handler.target),
            data=dict(command.handler.data),
        )
    elif isinstance(command.handler, CameraSnapshotCommandHandler):
        handler = CameraSnapshotActionHandler(
            entity_id=command.handler.entity_id,
            caption=command.handler.caption,
        )
    else:  # pragma: no cover - command registry validation prevents this.
        raise ValueError("unsupported command handler")
    return SafeActionDefinition(id=command.id, handler=handler)


class CommandExecutor:
    """Execute only already validated, pre-registered command definitions."""

    def __init__(self, hass: Any, account: Any) -> None:
        self._hass = hass
        self._account = account
        self._safe_actions = SafeActionExecutor(hass)

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
        del sender  # Authorization happened before execution; retained for audit API stability.
        progress_room = None
        progress_event_id: str | None = None

        try:
            action = _to_safe_action(command)
            if command.progress:
                progress_room, progress_event_id = await self._send_progress(
                    room_id=room_id,
                    source_event_id=source_event_id,
                    thread_id=thread_id,
                )

            result = await self._safe_actions.async_execute(
                action,
                context=SafeActionExecutionContext(
                    account=self._account,
                    room_id=room_id,
                    thread_id=thread_id,
                    prepared_room=progress_room,
                ),
            )
        except Exception as err:
            error = safe_error(err)
            if progress_room is not None and progress_event_id:
                try:
                    await self._edit_progress(
                        progress_room,
                        progress_event_id,
                        f"❌ Failed: {error}",
                    )
                except Exception:
                    pass
            return CommandExecutionResult(
                command_id=command.id,
                status="failed",
                handler_type="unknown",
                error=error,
            )

        if result.status != "success":
            if progress_room is not None and progress_event_id:
                try:
                    await self._edit_progress(
                        progress_room,
                        progress_event_id,
                        f"❌ Failed: {result.error or 'action failed'}",
                    )
                except Exception:
                    pass
            return CommandExecutionResult(
                command_id=command.id,
                status=result.status,
                handler_type=result.handler_type,
                error=result.error,
            )

        if progress_room is not None and progress_event_id:
            await self._edit_progress(progress_room, progress_event_id, "✅ Done")
        return CommandExecutionResult(
            command_id=command.id,
            status="success",
            handler_type=result.handler_type,
            error=None,
        )
