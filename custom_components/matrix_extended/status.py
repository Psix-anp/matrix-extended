"""Runtime connection and send status for Matrix Extended."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime


class MatrixRuntimeStatus:
    """Mutable runtime status shared by Matrix entities and services."""

    __slots__ = (
        "connected",
        "default_room_encrypted",
        "last_send",
        "last_receive",
        "last_error",
        "_listeners",
    )

    def __init__(self) -> None:
        self.connected = False
        self.default_room_encrypted: bool | None = None
        self.last_send: datetime | None = None
        self.last_receive: datetime | None = None
        self.last_error: str | None = None
        self._listeners: set[Callable[[], None]] = set()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a status listener and return an unsubscribe callback."""
        self._listeners.add(listener)

        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def mark_connected(self, *, default_room_encrypted: bool | None = None) -> None:
        """Mark the Matrix account reachable and clear the last error."""
        self.connected = True
        if default_room_encrypted is not None:
            self.default_room_encrypted = default_room_encrypted
        self.last_error = None
        self._notify()

    def mark_send_success(self) -> None:
        """Record a successful send."""
        self.connected = True
        self.last_send = datetime.now(UTC)
        self.last_error = None
        self._notify()

    def mark_receive(self) -> None:
        """Record an authorized incoming Matrix event."""
        self.connected = True
        self.last_receive = datetime.now(UTC)
        self.last_error = None
        self._notify()

    def mark_error(self, error: str, *, connected: bool = False) -> None:
        """Record a connection/send error."""
        self.connected = connected
        self.last_error = str(error)
        self._notify()

    def set_default_room_encryption(self, encrypted: bool | None) -> None:
        """Update the encryption state known for the default room."""
        self.default_room_encrypted = encrypted
        self._notify()
