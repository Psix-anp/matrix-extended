"""Lifecycle manager for native Matrix Extended control panels."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
import time
from typing import Any

from .client import MatrixConnectionError, MatrixSendError
from .content import (
    build_edit_content,
    build_reaction_content,
    build_reply_content,
    build_text_content,
)
from .control_panel_render import RenderedPanel, render_control_panel
from .control_panel_runtime import (
    ControlPanelRuntimeStore,
    PanelRuntime,
    PendingConfirmationRegistry,
)
from .control_panels import ControlPanelDefinition, PanelAction
from .safe_action_executor import SafeActionExecutionContext, SafeActionExecutor

PANEL_METADATA_KEY = "io.psix.matrix_extended.panel"
PANEL_SCHEMA = 1
_CONFIRM_REACTION = "✅"
_CANCEL_REACTION = "❌"
_CONFIRMATION_TTL_SECONDS = 30.0


@dataclass(slots=True, frozen=True)
class PanelReactionOutcome:
    """Bounded result of routing one Matrix reaction through panel control."""

    handled: bool
    action_id: str | None = None
    status: str | None = None
    error: str | None = None
    confirmation_prompt_event_id: str | None = None


class ControlPanelManager:
    """Own root messages, live edits, pins, retries and repair state."""

    def __init__(
        self,
        *,
        hass: Any,
        client: Any,
        panels: Mapping[str, ControlPanelDefinition],
        runtime_store: ControlPanelRuntimeStore,
        confirmations: PendingConfirmationRegistry | None = None,
        safe_action_executor: SafeActionExecutor | None = None,
        track_state_change: Callable[..., Callable[[], None]] | None = None,
        retry_delay: float = 5.0,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.hass = hass
        self.client = client
        self.panels = dict(panels)
        self.runtime_store = runtime_store
        self.confirmations = confirmations or PendingConfirmationRegistry()
        self.safe_action_executor = safe_action_executor or SafeActionExecutor(hass)
        self._track_state_change = track_state_change
        self._retry_delay = max(0.01, float(retry_delay))
        self._now = now
        self._started = False
        self._unsubscribers: list[Callable[[], None]] = []
        self._debounce_tasks: dict[str, asyncio.Task[Any]] = {}
        self._retry_tasks: dict[str, asyncio.Task[Any]] = {}
        self._desired: dict[str, RenderedPanel] = {}
        self._listeners: list[Callable[[], Any]] = []

    @property
    def pending_retry_count(self) -> int:
        """Return the number of live retry workers, bounded to one per panel."""
        return sum(1 for task in self._retry_tasks.values() if not task.done())

    def add_listener(self, listener: Callable[[], Any]) -> Callable[[], None]:
        """Subscribe to diagnostics-affecting manager changes."""
        self._listeners.append(listener)

        def remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return remove

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                result = listener()
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:
                # A diagnostics listener must never break panel control.
                continue

    @staticmethod
    def _metadata(panel: ControlPanelDefinition) -> dict[str, Any]:
        return {
            PANEL_METADATA_KEY: {
                "schema": PANEL_SCHEMA,
                "panel_id": panel.panel_id,
            }
        }

    def _states_for(self, panel: ControlPanelDefinition) -> dict[str, Any]:
        return {
            entity.entity_id: self.hass.states.get(entity.entity_id)
            for entity in panel.entities
        }

    def _render(self, panel: ControlPanelDefinition) -> RenderedPanel:
        return render_control_panel(panel, self._states_for(panel))

    def _runtime_for(self, panel: ControlPanelDefinition) -> PanelRuntime:
        runtime = self.runtime_store.get(panel.panel_id)
        if runtime is None:
            runtime = PanelRuntime(panel_id=panel.panel_id, room_id=panel.room_id)
            self.runtime_store.set(runtime)
            return runtime
        if runtime.room_id != panel.room_id:
            # Moving a configured panel to another already-authorized room is
            # a new root generation. Never try to edit the old room's event.
            runtime.room_id = panel.room_id
            runtime.root_event_id = None
            runtime.render_hash = None
            runtime.needs_repair = False
            runtime.pin_status = "unknown"
            runtime.pin_error = None
        return runtime

    @staticmethod
    def _valid_root(event: Mapping[str, Any] | None, panel: ControlPanelDefinition) -> bool:
        if not isinstance(event, Mapping) or event.get("type") != "m.room.message":
            return False
        content = event.get("content")
        if not isinstance(content, Mapping):
            return False
        marker = content.get(PANEL_METADATA_KEY)
        return (
            isinstance(marker, Mapping)
            and marker.get("schema") == PANEL_SCHEMA
            and marker.get("panel_id") == panel.panel_id
        )

    async def _save(self) -> None:
        await self.runtime_store.async_save()
        self._notify()

    async def _attempt_pin(
        self, panel: ControlPanelDefinition, runtime: PanelRuntime
    ) -> None:
        if not runtime.root_event_id:
            return
        try:
            await self.client.async_pin_event(panel.room_id, runtime.root_event_id)
        except (MatrixConnectionError, MatrixSendError) as err:
            runtime.pin_status = "error"
            runtime.pin_error = str(err)
        else:
            runtime.pin_status = "pinned"
            runtime.pin_error = None
        await self._save()

    async def _add_action_reactions(
        self, panel: ControlPanelDefinition, root_event_id: str
    ) -> None:
        for action in panel.actions:
            await self.client.async_send_event(
                panel.room_id,
                "m.reaction",
                build_reaction_content(root_event_id, action.reaction),
            )

    async def _create_root(
        self,
        panel: ControlPanelDefinition,
        runtime: PanelRuntime,
    ) -> str:
        rendered = self._render(panel)
        content = build_text_content(
            rendered.body,
            formatted_body=rendered.formatted_body,
            extra_content=self._metadata(panel),
        )
        root_event_id = await self.client.async_send_content(panel.room_id, content)
        if not root_event_id:
            raise MatrixSendError("Matrix control panel root send returned no event ID")

        runtime.root_event_id = root_event_id
        runtime.render_hash = rendered.digest
        runtime.generation = max(0, runtime.generation) + 1
        runtime.needs_repair = False
        runtime.last_update_at = self._now()
        runtime.last_update_error = None
        runtime.pin_status = "unknown"
        runtime.pin_error = None
        self.confirmations.clear_panel(panel.panel_id)
        await self._add_action_reactions(panel, root_event_id)
        await self._save()
        await self._attempt_pin(panel, runtime)
        return root_event_id

    async def _prepare_panel(self, panel: ControlPanelDefinition) -> None:
        runtime = self._runtime_for(panel)
        if runtime.root_event_id:
            try:
                event = await self.client.async_get_event(
                    panel.room_id, runtime.root_event_id
                )
            except (MatrixConnectionError, MatrixSendError) as err:
                # A transport/permission problem does not prove the root is
                # gone. Keep identity intact and expose the error.
                runtime.last_update_error = str(err)
                await self._save()
                return
            if not self._valid_root(event, panel):
                runtime.needs_repair = True
                runtime.last_update_error = "control panel root is missing or invalid"
                self.confirmations.clear_panel(panel.panel_id)
                await self._save()
                return

            runtime.needs_repair = False
            await self._attempt_pin(panel, runtime)
            rendered = self._render(panel)
            if rendered.digest != runtime.render_hash:
                self._desired[panel.panel_id] = rendered
                await self._try_send_latest(panel.panel_id, schedule_retry=True)
            return

        if runtime.generation > 0 or runtime.needs_repair:
            runtime.needs_repair = True
            runtime.last_update_error = "control panel root requires explicit repair"
            await self._save()
            return

        await self._create_root(panel, runtime)

    def _state_changed(self, panel_id: str) -> None:
        if not self._started:
            return
        panel = self.panels.get(panel_id)
        if panel is None or not panel.enabled:
            return
        old_task = self._debounce_tasks.get(panel_id)
        if old_task is not None and not old_task.done():
            old_task.cancel()

        async def runner() -> None:
            try:
                await asyncio.sleep(panel.debounce)
                rendered = self._render(panel)
                self._desired[panel_id] = rendered
                retry = self._retry_tasks.get(panel_id)
                if retry is None or retry.done():
                    await self._try_send_latest(panel_id, schedule_retry=True)
            except asyncio.CancelledError:
                raise
            finally:
                current = asyncio.current_task()
                if self._debounce_tasks.get(panel_id) is current:
                    self._debounce_tasks.pop(panel_id, None)

        self._debounce_tasks[panel_id] = asyncio.create_task(
            runner(), name=f"matrix_extended_panel_debounce_{panel_id}"
        )

    async def _try_send_latest(
        self, panel_id: str, *, schedule_retry: bool
    ) -> bool:
        panel = self.panels.get(panel_id)
        if panel is None or not panel.enabled:
            self._desired.pop(panel_id, None)
            return True
        runtime = self.runtime_store.get(panel_id)
        if runtime is None or runtime.needs_repair or not runtime.root_event_id:
            self._desired.pop(panel_id, None)
            return True

        rendered = self._desired.get(panel_id) or self._render(panel)
        self._desired[panel_id] = rendered
        if rendered.digest == runtime.render_hash:
            self._desired.pop(panel_id, None)
            if runtime.last_update_error is not None:
                runtime.last_update_error = None
                await self._save()
            return True

        content = build_edit_content(
            rendered.body,
            event_id=runtime.root_event_id,
            formatted_body=rendered.formatted_body,
            extra_content=self._metadata(panel),
        )
        try:
            await self.client.async_send_content(panel.room_id, content)
        except (MatrixConnectionError, MatrixSendError) as err:
            runtime.last_update_error = str(err)
            await self._save()
            if schedule_retry:
                self._ensure_retry(panel_id)
            return False

        runtime.render_hash = rendered.digest
        runtime.last_update_at = self._now()
        runtime.last_update_error = None
        current = self._desired.get(panel_id)
        if current is not None and current.digest == rendered.digest:
            self._desired.pop(panel_id, None)
        await self._save()
        return True

    def _ensure_retry(self, panel_id: str) -> None:
        existing = self._retry_tasks.get(panel_id)
        if existing is not None and not existing.done():
            return

        async def runner() -> None:
            try:
                while self._started:
                    await asyncio.sleep(self._retry_delay)
                    panel = self.panels.get(panel_id)
                    runtime = self.runtime_store.get(panel_id)
                    if (
                        panel is None
                        or not panel.enabled
                        or runtime is None
                        or runtime.needs_repair
                        or not runtime.root_event_id
                    ):
                        return
                    # Re-render here so ten changes during an outage collapse
                    # to the latest desired Home Assistant state.
                    self._desired[panel_id] = self._render(panel)
                    if await self._try_send_latest(
                        panel_id, schedule_retry=False
                    ):
                        return
            except asyncio.CancelledError:
                raise
            finally:
                current = asyncio.current_task()
                if self._retry_tasks.get(panel_id) is current:
                    self._retry_tasks.pop(panel_id, None)

        self._retry_tasks[panel_id] = asyncio.create_task(
            runner(), name=f"matrix_extended_panel_retry_{panel_id}"
        )

    def _subscribe_panel(self, panel: ControlPanelDefinition) -> None:
        entity_ids = [entity.entity_id for entity in panel.entities]
        if not entity_ids:
            return
        tracker = self._track_state_change
        if tracker is None:
            from homeassistant.helpers.event import async_track_state_change_event

            tracker = async_track_state_change_event
        unsubscribe = tracker(
            self.hass,
            entity_ids,
            lambda _event, panel_id=panel.panel_id: self._state_changed(panel_id),
        )
        self._unsubscribers.append(unsubscribe)

    async def async_start(self) -> None:
        """Restore/validate roots, create first roots and subscribe HA state."""
        if self._started:
            return
        self._started = True
        try:
            for panel in self.panels.values():
                if not panel.enabled:
                    continue
                await self._prepare_panel(panel)
                self._subscribe_panel(panel)
        except Exception:
            await self.async_stop()
            raise

    async def async_stop(self) -> None:
        """Cancel bounded workers, unsubscribe state listeners and clear prompts."""
        self._started = False
        for unsubscribe in self._unsubscribers:
            with suppress(Exception):
                unsubscribe()
        self._unsubscribers.clear()

        tasks = [
            task
            for task in (*self._debounce_tasks.values(), *self._retry_tasks.values())
            if not task.done()
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._debounce_tasks.clear()
        self._retry_tasks.clear()
        self._desired.clear()
        self.confirmations.clear()
        self._notify()

    async def async_repair(self, panel_id: str) -> str:
        """Explicitly replace a missing/invalid panel root with one new root."""
        panel = self.panels.get(panel_id)
        if panel is None or not panel.enabled:
            raise ValueError("unknown or disabled control panel")
        runtime = self._runtime_for(panel)
        if runtime.root_event_id and not runtime.needs_repair:
            raise ValueError("control panel does not need repair")

        debounce = self._debounce_tasks.pop(panel_id, None)
        if debounce is not None and not debounce.done():
            debounce.cancel()
            with suppress(asyncio.CancelledError):
                await debounce
        retry = self._retry_tasks.pop(panel_id, None)
        if retry is not None and not retry.done():
            retry.cancel()
            with suppress(asyncio.CancelledError):
                await retry
        self._desired.pop(panel_id, None)
        self.confirmations.clear_panel(panel_id)
        return await self._create_root(panel, runtime)

    def _panel_for_root(
        self, room_id: str, event_id: str
    ) -> tuple[ControlPanelDefinition, PanelRuntime] | None:
        for panel in self.panels.values():
            if not panel.enabled or panel.room_id != room_id:
                continue
            runtime = self.runtime_store.get(panel.panel_id)
            if runtime is not None and runtime.root_event_id == event_id:
                return panel, runtime
        return None

    @staticmethod
    def _action_for_reaction(
        panel: ControlPanelDefinition, reaction: str
    ) -> PanelAction | None:
        return next(
            (action for action in panel.actions if action.reaction == reaction),
            None,
        )

    @staticmethod
    def _action_by_id(
        panel: ControlPanelDefinition, action_id: str
    ) -> PanelAction | None:
        return next(
            (action for action in panel.actions if action.id == action_id),
            None,
        )

    async def _execute_panel_action(
        self,
        panel: ControlPanelDefinition,
        action: PanelAction,
    ) -> PanelReactionOutcome:
        result = await self.safe_action_executor.async_execute(
            action.action,
            context=SafeActionExecutionContext(room_id=panel.room_id),
        )
        return PanelReactionOutcome(
            handled=True,
            action_id=action.id,
            status=result.status,
            error=result.error,
        )

    async def _request_confirmation(
        self,
        panel: ControlPanelDefinition,
        runtime: PanelRuntime,
        action: PanelAction,
        sender: str,
    ) -> PanelReactionOutcome:
        prompt_event_id = await self.client.async_send_content(
            panel.room_id,
            build_reply_content(
                f"⚠️ Confirm: {action.label}",
                reply_to=runtime.root_event_id,
            ),
        )
        if not prompt_event_id:
            return PanelReactionOutcome(
                handled=True,
                action_id=action.id,
                status="failed",
                error="Matrix confirmation prompt returned no event ID",
            )
        for reaction in (_CONFIRM_REACTION, _CANCEL_REACTION):
            await self.client.async_send_event(
                panel.room_id,
                "m.reaction",
                build_reaction_content(prompt_event_id, reaction),
            )
        self.confirmations.issue(
            prompt_event_id=prompt_event_id,
            panel_id=panel.panel_id,
            action_id=action.id,
            sender=sender,
            generation=runtime.generation,
            expires_in=_CONFIRMATION_TTL_SECONDS,
        )
        self._notify()
        return PanelReactionOutcome(
            handled=True,
            action_id=action.id,
            status="confirmation_required",
            confirmation_prompt_event_id=prompt_event_id,
        )

    async def async_handle_reaction(
        self,
        room_id: str,
        event_id: str,
        reaction: str,
        sender: str,
    ) -> PanelReactionOutcome:
        """Route one already account-authorized Matrix reaction safely."""
        pending = self.confirmations.get(event_id)
        if pending is not None:
            panel = self.panels.get(pending.panel_id)
            runtime = self.runtime_store.get(pending.panel_id)
            if (
                panel is None
                or runtime is None
                or panel.room_id != room_id
                or runtime.needs_repair
            ):
                return PanelReactionOutcome(
                    handled=True,
                    action_id=pending.action_id,
                    status="invalid",
                )
            if pending.sender != sender:
                return PanelReactionOutcome(
                    handled=True,
                    action_id=pending.action_id,
                    status="unauthorized",
                )
            if reaction == _CANCEL_REACTION:
                cancelled = self.confirmations.cancel(
                    event_id,
                    sender=sender,
                    current_generation=runtime.generation,
                )
                self._notify()
                return PanelReactionOutcome(
                    handled=True,
                    action_id=pending.action_id,
                    status="cancelled" if cancelled else "expired",
                )
            if reaction != _CONFIRM_REACTION:
                return PanelReactionOutcome(
                    handled=True,
                    action_id=pending.action_id,
                    status="ignored",
                )
            confirmation = self.confirmations.consume(
                event_id,
                sender=sender,
                current_generation=runtime.generation,
            )
            self._notify()
            if confirmation is None:
                return PanelReactionOutcome(
                    handled=True,
                    action_id=pending.action_id,
                    status="expired",
                )
            action = self._action_by_id(panel, confirmation.action_id)
            if action is None:
                return PanelReactionOutcome(
                    handled=True,
                    action_id=confirmation.action_id,
                    status="invalid",
                )
            return await self._execute_panel_action(panel, action)

        matched = self._panel_for_root(room_id, event_id)
        if matched is None:
            return PanelReactionOutcome(handled=False, status="ignored")
        panel, runtime = matched
        if runtime.needs_repair:
            return PanelReactionOutcome(handled=True, status="repair_required")
        if panel.allowed_users and sender not in panel.allowed_users:
            return PanelReactionOutcome(handled=True, status="unauthorized")
        action = self._action_for_reaction(panel, reaction)
        if action is None:
            # A reaction on a managed root is owned by the panel subsystem;
            # never fall through to a legacy reaction mapping for that root.
            return PanelReactionOutcome(handled=True, status="ignored")
        if action.action.confirmation_required:
            return await self._request_confirmation(panel, runtime, action, sender)
        return await self._execute_panel_action(panel, action)

    async def async_handle_redaction(
        self, room_id: str, redacted_event_id: str
    ) -> bool:
        """Mark an active control root for explicit repair after redaction."""
        for panel in self.panels.values():
            if panel.room_id != room_id:
                continue
            runtime = self.runtime_store.get(panel.panel_id)
            if runtime is None or runtime.root_event_id != redacted_event_id:
                continue
            runtime.needs_repair = True
            runtime.last_update_error = "control panel root was redacted"
            self.confirmations.clear_panel(panel.panel_id)
            self._desired.pop(panel.panel_id, None)
            retry = self._retry_tasks.pop(panel.panel_id, None)
            if retry is not None and not retry.done():
                retry.cancel()
            await self._save()
            return True
        return False

    def diagnostics_snapshot(self) -> list[dict[str, Any]]:
        """Return bounded, secret-free panel runtime diagnostics."""
        result: list[dict[str, Any]] = []
        for panel in self.panels.values():
            runtime = self.runtime_store.get(panel.panel_id)
            result.append(
                {
                    "panel_id": panel.panel_id,
                    "room_id": panel.room_id,
                    "root_event_id": runtime.root_event_id if runtime else None,
                    "state": (
                        "repair_required"
                        if runtime and runtime.needs_repair
                        else "active"
                        if runtime and runtime.root_event_id
                        else "inactive"
                    ),
                    "pin_status": runtime.pin_status if runtime else "unknown",
                    "watched_entities": len(panel.entities),
                    "actions": len(panel.actions),
                    "last_update_at": runtime.last_update_at if runtime else None,
                    "last_update_error": (
                        runtime.last_update_error if runtime else None
                    ),
                    "pending_confirmations": self.confirmations.count,
                }
            )
        return result
