"""Authorized runtime manager for Matrix Extended native Widgets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import time
from typing import Any, Callable
from uuid import uuid4

from .control_panels import ControlPanelDefinition, PanelEntity
from .widget_controls import build_control_action, project_entity
from .widget_protocol import (
    WIDGET_EVENT_TYPE,
    WidgetActionRequest,
    WidgetConfirmRequest,
    WidgetHeartbeatRequest,
    WidgetSubscribeRequest,
    build_widget_message,
    parse_widget_request,
)
from .widget_sessions import WidgetSessionRegistry

_CONFIRMATION_TTL = 30.0


@dataclass(slots=True)
class _PendingWidgetConfirmation:
    confirmation_id: str
    panel_id: str
    sender: str
    generation: int
    kind: str
    action_id: str | None
    entity_id: str | None
    control: str | None
    value: Any
    expires_at: float


class _Reject(Exception):
    def __init__(self, status: str, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


class WidgetControlManager:
    """Authorize Widget requests and route them through local safe actions."""

    def __init__(
        self,
        *,
        hass: Any,
        transport: Any,
        panels: Mapping[str, ControlPanelDefinition],
        runtime_store: Any,
        safe_action_executor: Any,
        account_allowed_users: set[str],
        account_allowed_room_ids: set[str],
        sessions: WidgetSessionRegistry | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hass = hass
        self.transport = transport
        self.panels = dict(panels)
        self.runtime_store = runtime_store
        self.safe_action_executor = safe_action_executor
        self.account_allowed_users = set(account_allowed_users)
        self.account_allowed_room_ids = set(account_allowed_room_ids)
        self.sessions = sessions or WidgetSessionRegistry(now=now)
        self._now = now
        self._confirmations: dict[str, _PendingWidgetConfirmation] = {}
        self._last_error: str | None = None

    def _runtime(self, panel_id: str) -> Any:
        return self.runtime_store.get(panel_id)

    def _authorize(self, sender: str, request: Any) -> tuple[ControlPanelDefinition, Any]:
        panel = self.panels.get(request.panel_id)
        if panel is None:
            raise _Reject("unknown_panel", "panel is not configured")
        if request.room_id not in self.account_allowed_room_ids or panel.room_id != request.room_id:
            raise _Reject("unauthorized_room", "room is not authorized for this panel")
        if not panel.enabled or not panel.widget_enabled:
            raise _Reject("widget_disabled", "Widget is not enabled for this panel")
        if panel.allowed_users and sender not in panel.allowed_users:
            raise _Reject("unauthorized_user", "user is not authorized for this panel")
        runtime = self._runtime(panel.panel_id)
        if runtime is None:
            raise _Reject("runtime_unavailable", "panel runtime is unavailable")
        if getattr(runtime, "needs_repair", False):
            raise _Reject("needs_repair", "panel requires repair")
        current_generation = int(getattr(runtime, "generation", 0))
        if isinstance(request, WidgetSubscribeRequest) and request.generation == 0:
            return panel, runtime
        if request.generation != current_generation:
            raise _Reject("stale_generation", "panel generation is stale")
        return panel, runtime

    async def _send(
        self,
        user_id: str,
        *,
        op: str,
        panel: ControlPanelDefinition,
        generation: int,
        request_id: str | None = None,
        **fields: Any,
    ) -> None:
        content = build_widget_message(
            op=op,
            room_id=panel.room_id,
            panel_id=panel.panel_id,
            generation=generation,
            request_id=request_id,
            **fields,
        )
        await self.transport.async_send(WIDGET_EVENT_TYPE, user_id, "*", content)

    async def _send_error_raw(
        self, sender: str, raw: Mapping[str, Any], *, status: str, error: str
    ) -> None:
        panel_id = raw.get("panel_id")
        panel = self.panels.get(str(panel_id)) if isinstance(panel_id, str) else None
        if panel is None:
            return
        runtime = self._runtime(panel.panel_id)
        generation = int(getattr(runtime, "generation", 0)) if runtime is not None else 0
        self._last_error = str(error)[:200]
        await self._send(
            sender,
            op="error",
            panel=panel,
            generation=generation,
            status=status,
            error=self._last_error,
        )

    def _snapshot(self, panel: ControlPanelDefinition, generation: int) -> dict[str, Any]:
        return {
            "title": panel.title,
            "revision": self.sessions.next_revision(panel.panel_id),
            "entities": [
                project_entity(entity, self.hass.states.get(entity.entity_id))
                for entity in panel.entities
            ],
            "actions": [
                {
                    "id": item.id,
                    "label": item.label,
                    "confirmation_required": item.action.confirmation_required,
                }
                for item in panel.actions
            ],
        }

    async def _send_state(self, panel: ControlPanelDefinition, runtime: Any, user_id: str) -> None:
        await self._send(
            user_id,
            op="state",
            panel=panel,
            generation=int(runtime.generation),
            **self._snapshot(panel, int(runtime.generation)),
        )

    async def async_publish(self, panel_id: str) -> None:
        """Publish one complete current state snapshot to active subscribers."""
        panel = self.panels.get(panel_id)
        runtime = self._runtime(panel_id)
        if (
            panel is None
            or runtime is None
            or not panel.enabled
            or not panel.widget_enabled
            or getattr(runtime, "needs_repair", False)
        ):
            self.sessions.clear_panel(panel_id)
            return
        for user_id in self.sessions.active_users(panel_id):
            if user_id not in self.account_allowed_users:
                continue
            if panel.allowed_users and user_id not in panel.allowed_users:
                continue
            await self._send_state(panel, runtime, user_id)

    def _resolve_action(
        self,
        panel: ControlPanelDefinition,
        *,
        kind: str,
        action_id: str | None = None,
        entity_id: str | None = None,
        control: str | None = None,
        value: Any = None,
    ) -> Any:
        if kind == "panel_action":
            for item in panel.actions:
                if item.id == action_id:
                    return item.action
            raise _Reject("unknown_action", "panel action is not configured")
        if kind == "entity_control":
            entity: PanelEntity | None = next(
                (item for item in panel.entities if item.entity_id == entity_id), None
            )
            if entity is None:
                raise _Reject("unknown_entity", "entity is not configured on this panel")
            try:
                return build_control_action(
                    entity,
                    self.hass.states.get(entity.entity_id),
                    str(control or ""),
                    value,
                )
            except ValueError as err:
                raise _Reject("invalid_control", str(err)) from err
        raise _Reject("invalid_action", "unsupported Widget action kind")

    def _prune_confirmations(self) -> None:
        now = self._now()
        for key, item in tuple(self._confirmations.items()):
            if item.expires_at <= now:
                self._confirmations.pop(key, None)

    async def _execute(self, sender: str, panel: ControlPanelDefinition, runtime: Any, request_id: str, action: Any) -> None:
        result = await self.safe_action_executor.async_execute(action)
        if getattr(result, "status", None) == "success":
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request_id,
                status="accepted",
            )
        else:
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request_id,
                status="failed",
                error=str(getattr(result, "error", "action failed"))[:200],
            )

    async def _handle_action(self, sender: str, request: WidgetActionRequest, panel: ControlPanelDefinition, runtime: Any) -> None:
        if not self.sessions.accept_request(panel.panel_id, sender, request.request_id or ""):
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="duplicate_request",
            )
            return
        action = self._resolve_action(
            panel,
            kind=request.kind,
            action_id=request.action_id,
            entity_id=request.entity_id,
            control=request.control,
            value=request.value,
        )
        if action.confirmation_required:
            confirmation_id = str(uuid4())
            self._confirmations[confirmation_id] = _PendingWidgetConfirmation(
                confirmation_id=confirmation_id,
                panel_id=panel.panel_id,
                sender=sender,
                generation=int(runtime.generation),
                kind=request.kind,
                action_id=request.action_id,
                entity_id=request.entity_id,
                control=request.control,
                value=request.value,
                expires_at=self._now() + _CONFIRMATION_TTL,
            )
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="confirmation_required",
                confirmation_id=confirmation_id,
                expires_in=int(_CONFIRMATION_TTL),
            )
            return
        await self._execute(sender, panel, runtime, request.request_id or "", action)

    async def _handle_confirmation(self, sender: str, request: WidgetConfirmRequest, panel: ControlPanelDefinition, runtime: Any) -> None:
        if not self.sessions.accept_request(panel.panel_id, sender, request.request_id or ""):
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="duplicate_request",
            )
            return
        self._prune_confirmations()
        pending = self._confirmations.get(request.confirmation_id)
        if pending is None:
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="confirmation_expired",
            )
            return
        if pending.sender != sender or pending.panel_id != panel.panel_id:
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="confirmation_rejected",
            )
            return
        if pending.generation != int(runtime.generation):
            self._confirmations.pop(request.confirmation_id, None)
            raise _Reject("stale_generation", "confirmation belongs to a stale panel generation")
        self._confirmations.pop(request.confirmation_id, None)
        if request.op == "cancel":
            await self._send(
                sender,
                op="result",
                panel=panel,
                generation=int(runtime.generation),
                request_id=request.request_id,
                status="cancelled",
            )
            return
        action = self._resolve_action(
            panel,
            kind=pending.kind,
            action_id=pending.action_id,
            entity_id=pending.entity_id,
            control=pending.control,
            value=pending.value,
        )
        await self._execute(sender, panel, runtime, request.request_id or "", action)

    async def async_handle(self, sender: str, content: Mapping[str, Any]) -> None:
        """Handle one authenticated Matrix to-device Widget payload."""
        if sender not in self.account_allowed_users:
            return
        try:
            request = parse_widget_request(content)
        except ValueError as err:
            await self._send_error_raw(
                sender, content, status="invalid_request", error=str(err)
            )
            return
        try:
            panel, runtime = self._authorize(sender, request)
            if isinstance(request, WidgetSubscribeRequest):
                self.sessions.subscribe(panel.panel_id, panel.room_id, sender)
                await self._send_state(panel, runtime, sender)
                return
            if isinstance(request, WidgetHeartbeatRequest):
                status = (
                    "accepted"
                    if self.sessions.heartbeat(panel.panel_id, sender)
                    else "no_subscription"
                )
                await self._send(
                    sender,
                    op="result",
                    panel=panel,
                    generation=int(runtime.generation),
                    status=status,
                )
                return
            if isinstance(request, WidgetActionRequest):
                await self._handle_action(sender, request, panel, runtime)
                return
            if isinstance(request, WidgetConfirmRequest):
                await self._handle_confirmation(sender, request, panel, runtime)
                return
        except _Reject as err:
            self._last_error = err.error[:200]
            panel = self.panels.get(request.panel_id)
            if panel is None:
                return
            runtime = self._runtime(panel.panel_id)
            generation = int(getattr(runtime, "generation", 0)) if runtime else 0
            await self._send(
                sender,
                op="error",
                panel=panel,
                generation=generation,
                request_id=getattr(request, "request_id", None),
                status=err.status,
                error=self._last_error,
            )

    async def async_close(self) -> None:
        self._confirmations.clear()
        for panel_id in tuple(self.panels):
            self.sessions.clear_panel(panel_id)

    def diagnostics_snapshot(self) -> dict[str, Any]:
        return {
            "protocol_schema": 1,
            "enabled_panels": sum(
                1 for panel in self.panels.values() if panel.enabled and panel.widget_enabled
            ),
            "active_subscriptions": sum(
                len(self.sessions.active_users(panel_id)) for panel_id in self.panels
            ),
            "pending_confirmations": len(self._confirmations),
            "last_error": self._last_error,
        }
