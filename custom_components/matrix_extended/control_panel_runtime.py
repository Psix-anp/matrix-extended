"""Persistent runtime state and ephemeral confirmations for Matrix control panels."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import time
from typing import Any

_STORE_VERSION = 1
_DEFAULT_CONFIRMATION_TTL = 30.0


@dataclass(slots=True)
class PanelRuntime:
    """Persisted runtime identity and health for one Matrix control panel."""

    panel_id: str
    room_id: str
    root_event_id: str | None = None
    render_hash: str | None = None
    generation: int = 0
    pin_status: str = "unknown"
    pin_error: str | None = None
    needs_repair: bool = False
    last_update_at: float | None = None
    last_update_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for Home Assistant Store."""
        return {
            "room_id": self.room_id,
            "root_event_id": self.root_event_id,
            "render_hash": self.render_hash,
            "generation": self.generation,
            "pin_status": self.pin_status,
            "pin_error": self.pin_error,
            "needs_repair": self.needs_repair,
            "last_update_at": self.last_update_at,
            "last_update_error": self.last_update_error,
        }

    @classmethod
    def from_dict(cls, panel_id: str, value: Mapping[str, Any]) -> "PanelRuntime":
        """Restore one runtime entry, rejecting malformed identity fields."""
        room_id = str(value.get("room_id", "")).strip()
        if not panel_id or not room_id:
            raise ValueError("panel runtime requires panel_id and room_id")

        try:
            generation = int(value.get("generation", 0))
        except (TypeError, ValueError) as err:
            raise ValueError("panel generation must be an integer") from err
        if generation < 0:
            raise ValueError("panel generation must not be negative")

        def optional_text(name: str) -> str | None:
            raw = value.get(name)
            if raw is None:
                return None
            text = str(raw).strip()
            return text or None

        raw_updated = value.get("last_update_at")
        if raw_updated is None:
            last_update_at = None
        else:
            try:
                last_update_at = float(raw_updated)
            except (TypeError, ValueError) as err:
                raise ValueError("last_update_at must be numeric") from err

        return cls(
            panel_id=panel_id,
            room_id=room_id,
            root_event_id=optional_text("root_event_id"),
            render_hash=optional_text("render_hash"),
            generation=generation,
            pin_status=str(value.get("pin_status", "unknown") or "unknown"),
            pin_error=optional_text("pin_error"),
            needs_repair=bool(value.get("needs_repair", False)),
            last_update_at=last_update_at,
            last_update_error=optional_text("last_update_error"),
        )


class ControlPanelRuntimeStore:
    """Small adapter around Home Assistant Store for panel runtime state."""

    def __init__(
        self,
        stored: Mapping[str, Any] | None = None,
        *,
        store: Any = None,
    ) -> None:
        self._store = store
        self._panels: dict[str, PanelRuntime] = {}
        if stored is not None:
            self.restore(stored)

    def restore(self, stored: Mapping[str, Any] | None) -> None:
        """Replace current runtime state from a persisted JSON-safe mapping."""
        self._panels.clear()
        if not isinstance(stored, Mapping):
            return
        raw_panels = stored.get("panels", {})
        if not isinstance(raw_panels, Mapping):
            return
        for raw_panel_id, raw_runtime in raw_panels.items():
            panel_id = str(raw_panel_id).strip()
            if not panel_id or not isinstance(raw_runtime, Mapping):
                continue
            try:
                runtime = PanelRuntime.from_dict(panel_id, raw_runtime)
            except ValueError:
                continue
            self._panels[panel_id] = runtime

    def get(self, panel_id: str) -> PanelRuntime | None:
        """Return runtime state for one configured panel."""
        return self._panels.get(panel_id)

    def set(self, runtime: PanelRuntime) -> None:
        """Insert or replace runtime state for one panel."""
        if not runtime.panel_id:
            raise ValueError("panel_id must not be empty")
        if not runtime.room_id:
            raise ValueError("room_id must not be empty")
        self._panels[runtime.panel_id] = runtime

    def remove(self, panel_id: str) -> PanelRuntime | None:
        """Remove and return one runtime entry."""
        return self._panels.pop(panel_id, None)

    def values(self) -> tuple[PanelRuntime, ...]:
        """Return a stable runtime snapshot."""
        return tuple(self._panels.values())

    def dump(self) -> dict[str, Any]:
        """Return JSON-safe persisted runtime data.

        Confirmation prompts are deliberately not part of this store.
        """
        return {
            "version": _STORE_VERSION,
            "panels": {
                panel_id: runtime.to_dict()
                for panel_id, runtime in self._panels.items()
            },
        }

    async def async_save(self) -> None:
        """Persist runtime state when a Home Assistant Store is attached."""
        if self._store is not None:
            await self._store.async_save(self.dump())


@dataclass(slots=True, frozen=True)
class PendingConfirmation:
    """Memory-only binding for one dangerous Matrix action confirmation."""

    prompt_event_id: str
    panel_id: str
    action_id: str
    sender: str
    generation: int
    expires_at: float


class PendingConfirmationRegistry:
    """Single-use, same-sender confirmation prompts keyed by Matrix event ID."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._now = now
        self._items: dict[str, PendingConfirmation] = {}

    def _prune_expired(self) -> None:
        now = self._now()
        for event_id, confirmation in tuple(self._items.items()):
            if confirmation.expires_at <= now:
                self._items.pop(event_id, None)

    @property
    def count(self) -> int:
        """Return the number of currently valid pending prompts."""
        self._prune_expired()
        return len(self._items)

    def get(self, prompt_event_id: str) -> PendingConfirmation | None:
        """Return one still-valid prompt without consuming it."""
        self._prune_expired()
        return self._items.get(prompt_event_id)

    def issue(
        self,
        *,
        prompt_event_id: str,
        panel_id: str,
        action_id: str,
        sender: str,
        generation: int,
        expires_in: float = _DEFAULT_CONFIRMATION_TTL,
    ) -> PendingConfirmation:
        """Register or replace a bounded confirmation prompt."""
        prompt_event_id = str(prompt_event_id).strip()
        panel_id = str(panel_id).strip()
        action_id = str(action_id).strip()
        sender = str(sender).strip()
        if not prompt_event_id or not panel_id or not action_id or not sender:
            raise ValueError("confirmation identifiers must not be empty")
        try:
            generation = int(generation)
        except (TypeError, ValueError) as err:
            raise ValueError("generation must be an integer") from err
        if generation < 0:
            raise ValueError("generation must not be negative")
        try:
            ttl = float(expires_in)
        except (TypeError, ValueError) as err:
            raise ValueError("expires_in must be numeric") from err
        if ttl <= 0:
            raise ValueError("expires_in must be greater than zero")

        confirmation = PendingConfirmation(
            prompt_event_id=prompt_event_id,
            panel_id=panel_id,
            action_id=action_id,
            sender=sender,
            generation=generation,
            expires_at=self._now() + ttl,
        )
        self._items[prompt_event_id] = confirmation
        return confirmation

    def _take(
        self,
        prompt_event_id: str,
        *,
        sender: str,
        current_generation: int,
    ) -> PendingConfirmation | None:
        self._prune_expired()
        confirmation = self._items.get(prompt_event_id)
        if confirmation is None:
            return None
        # A forged reaction from another Matrix account must not consume the
        # legitimate user's still-valid confirmation prompt.
        if confirmation.sender != sender:
            return None
        if confirmation.generation != current_generation:
            # The panel root was replaced/repaired after this prompt was
            # issued. It can never become valid again, so remove it.
            self._items.pop(prompt_event_id, None)
            return None
        self._items.pop(prompt_event_id, None)
        return confirmation

    def consume(
        self,
        prompt_event_id: str,
        *,
        sender: str,
        current_generation: int,
    ) -> PendingConfirmation | None:
        """Atomically consume a valid confirmation for the same sender."""
        return self._take(
            prompt_event_id,
            sender=sender,
            current_generation=current_generation,
        )

    def cancel(
        self,
        prompt_event_id: str,
        *,
        sender: str,
        current_generation: int,
    ) -> bool:
        """Cancel a prompt only when the same sender still owns it."""
        return (
            self._take(
                prompt_event_id,
                sender=sender,
                current_generation=current_generation,
            )
            is not None
        )

    def clear_panel(self, panel_id: str) -> None:
        """Invalidate all pending confirmations for one panel generation."""
        for event_id, confirmation in tuple(self._items.items()):
            if confirmation.panel_id == panel_id:
                self._items.pop(event_id, None)

    def clear(self) -> None:
        """Invalidate every pending prompt, for example on reload/unload."""
        self._items.clear()
