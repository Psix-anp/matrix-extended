"""Persistent bounded outbox primitives for Matrix Extended sends."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import secrets
import time
from typing import Any

DEFAULT_MAX_ENTRIES = 128
DEFAULT_TTL_SECONDS = 24 * 60 * 60


@dataclass(slots=True, frozen=True)
class OutboxItem:
    """One queued Matrix send request."""

    delivery_id: str
    created_at: float
    payload: dict[str, Any]


def _json_copy(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach a payload using the same primitives HA Store writes."""
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as err:
        raise ValueError("outbox payload must be JSON serializable") from err
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ValueError("outbox payload must be a JSON object")
    return decoded


def matrix_transaction_id(delivery_id: str, event_key: str, room_id: str) -> str:
    """Build a stable Matrix transaction ID for one logical delivery event."""
    raw = f"{delivery_id}\0{event_key}\0{room_id}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:40]
    return f"mxext-{digest}"


class PersistentOutbox:
    """FIFO, TTL-bounded, JSON-safe queue backed by Home Assistant Store."""

    def __init__(
        self,
        stored: Mapping[str, Any] | None = None,
        *,
        store: Any = None,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        now: Callable[[], float] = time.time,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._store = store
        self._max_entries = max_entries
        self._ttl_seconds = float(ttl_seconds)
        self._now = now
        self._items: OrderedDict[str, OutboxItem] = OrderedDict()

        raw_items = stored.get("items", []) if isinstance(stored, Mapping) else []
        if isinstance(raw_items, list):
            for raw in raw_items:
                if not isinstance(raw, Mapping):
                    continue
                delivery_id = str(raw.get("id", "")).strip()
                payload = raw.get("payload")
                try:
                    created_at = float(raw.get("created_at"))
                    safe_payload = _json_copy(payload) if isinstance(payload, Mapping) else None
                except (TypeError, ValueError):
                    continue
                if not delivery_id or safe_payload is None:
                    continue
                if self._expired(created_at):
                    continue
                if delivery_id in self._items:
                    continue
                self._items[delivery_id] = OutboxItem(
                    delivery_id=delivery_id,
                    created_at=created_at,
                    payload=safe_payload,
                )

        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    def _expired(self, created_at: float) -> bool:
        return self._now() - created_at > self._ttl_seconds

    def _prune_expired(self) -> None:
        expired = [
            delivery_id
            for delivery_id, item in self._items.items()
            if self._expired(item.created_at)
        ]
        for delivery_id in expired:
            self._items.pop(delivery_id, None)

    def pending(self) -> list[OutboxItem]:
        """Return a stable FIFO snapshot of non-expired items."""
        self._prune_expired()
        return list(self._items.values())

    def dump(self) -> dict[str, list[dict[str, Any]]]:
        """Return JSON-safe state for Home Assistant Store."""
        self._prune_expired()
        return {
            "items": [
                {
                    "id": item.delivery_id,
                    "created_at": item.created_at,
                    "payload": _json_copy(item.payload),
                }
                for item in self._items.values()
            ]
        }

    async def async_save(self) -> None:
        """Persist current state when a Store is attached."""
        if self._store is not None:
            await self._store.async_save(self.dump())

    async def async_enqueue(
        self,
        payload: Mapping[str, Any],
        *,
        delivery_id: str | None = None,
    ) -> str:
        """Append one request, preserving the first copy of a duplicate ID."""
        safe_payload = _json_copy(payload)
        self._prune_expired()
        delivery_id = str(delivery_id or secrets.token_hex(16)).strip()
        if not delivery_id:
            raise ValueError("delivery_id must not be empty")
        if delivery_id in self._items:
            return delivery_id

        self._items[delivery_id] = OutboxItem(
            delivery_id=delivery_id,
            created_at=self._now(),
            payload=safe_payload,
        )
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)
        await self.async_save()
        return delivery_id

    async def async_remove(self, delivery_id: str) -> bool:
        """Remove one delivered or permanently failed request and persist."""
        removed = self._items.pop(delivery_id, None) is not None
        if removed:
            await self.async_save()
        return removed
