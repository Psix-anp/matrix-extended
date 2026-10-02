"""Ephemeral native Widget subscriptions and replay protection."""

from __future__ import annotations

from dataclasses import dataclass, replace
import time
from typing import Callable

_DEFAULT_TTL = 90.0
_DEFAULT_REPLAY_TTL = 300.0
_DEFAULT_REPLAY_LIMIT = 256


@dataclass(slots=True, frozen=True)
class WidgetSubscription:
    panel_id: str
    room_id: str
    user_id: str
    expires_at: float


class WidgetSessionRegistry:
    """Memory-only Widget lifecycle state; intentionally never persisted."""

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        subscription_ttl: float = _DEFAULT_TTL,
        replay_ttl: float = _DEFAULT_REPLAY_TTL,
        replay_limit: int = _DEFAULT_REPLAY_LIMIT,
    ) -> None:
        self._now = now
        self._subscription_ttl = float(subscription_ttl)
        self._replay_ttl = float(replay_ttl)
        self._replay_limit = int(replay_limit)
        if self._subscription_ttl <= 0 or self._replay_ttl <= 0:
            raise ValueError("Widget TTLs must be positive")
        if self._replay_limit <= 0:
            raise ValueError("replay_limit must be positive")
        self._subscriptions: dict[tuple[str, str], WidgetSubscription] = {}
        self._revisions: dict[str, int] = {}
        self._requests: dict[tuple[str, str], dict[str, float]] = {}

    def _prune_subscriptions(self) -> None:
        now = self._now()
        for key, item in tuple(self._subscriptions.items()):
            if item.expires_at <= now:
                self._subscriptions.pop(key, None)

    def _prune_requests(self, key: tuple[str, str]) -> dict[str, float]:
        now = self._now()
        bucket = self._requests.setdefault(key, {})
        for request_id, expires_at in tuple(bucket.items()):
            if expires_at <= now:
                bucket.pop(request_id, None)
        return bucket

    def subscribe(self, panel_id: str, room_id: str, user_id: str) -> WidgetSubscription:
        panel_id = str(panel_id).strip()
        room_id = str(room_id).strip()
        user_id = str(user_id).strip()
        if not panel_id or not room_id or not user_id:
            raise ValueError("subscription identifiers must not be empty")
        item = WidgetSubscription(
            panel_id=panel_id,
            room_id=room_id,
            user_id=user_id,
            expires_at=self._now() + self._subscription_ttl,
        )
        self._subscriptions[(panel_id, user_id)] = item
        return item

    def heartbeat(self, panel_id: str, user_id: str) -> bool:
        self._prune_subscriptions()
        key = (str(panel_id).strip(), str(user_id).strip())
        item = self._subscriptions.get(key)
        if item is None:
            return False
        self._subscriptions[key] = replace(
            item, expires_at=self._now() + self._subscription_ttl
        )
        return True

    def active_users(self, panel_id: str) -> tuple[str, ...]:
        self._prune_subscriptions()
        panel_id = str(panel_id).strip()
        return tuple(
            item.user_id
            for item in self._subscriptions.values()
            if item.panel_id == panel_id
        )

    def next_revision(self, panel_id: str) -> int:
        panel_id = str(panel_id).strip()
        if not panel_id:
            raise ValueError("panel_id must not be empty")
        revision = self._revisions.get(panel_id, 0) + 1
        self._revisions[panel_id] = revision
        return revision

    def accept_request(self, panel_id: str, user_id: str, request_id: str) -> bool:
        key = (str(panel_id).strip(), str(user_id).strip())
        request_id = str(request_id).strip()
        if not all((*key, request_id)):
            raise ValueError("replay identifiers must not be empty")
        bucket = self._prune_requests(key)
        if request_id in bucket:
            return False
        while len(bucket) >= self._replay_limit:
            oldest = min(bucket, key=bucket.__getitem__)
            bucket.pop(oldest, None)
        bucket[request_id] = self._now() + self._replay_ttl
        return True

    def clear_panel(self, panel_id: str) -> None:
        panel_id = str(panel_id).strip()
        for key in tuple(self._subscriptions):
            if key[0] == panel_id:
                self._subscriptions.pop(key, None)
        for key in tuple(self._requests):
            if key[0] == panel_id:
                self._requests.pop(key, None)
        self._revisions.pop(panel_id, None)
