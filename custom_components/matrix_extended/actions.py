"""Persistent registry for reaction-triggered Home Assistant actions."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
import time
from typing import Any

DEFAULT_EXPIRES_IN = 60 * 60
MAX_EXPIRES_IN = 7 * 24 * 60 * 60
DEFAULT_MAX_USES = 1
MAX_USES = 100


class ReactionAction:
    """A bounded Home Assistant service call attached to a Matrix reaction."""

    __slots__ = (
        "service",
        "target",
        "data",
        "expires_at",
        "remaining_uses",
        "allowed_users",
    )

    def __init__(
        self,
        *,
        service: str,
        target: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        expires_at: float,
        remaining_uses: int,
        allowed_users: Sequence[str] | None = None,
    ) -> None:
        self.service = service
        self.target = dict(target or {})
        self.data = dict(data or {})
        self.expires_at = float(expires_at)
        self.remaining_uses = int(remaining_uses)
        self.allowed_users = tuple(allowed_users or ())


class ReactionActionRegistry:
    """Bounded persistent mapping from Matrix reactions to explicit HA actions."""

    def __init__(
        self,
        stored: Mapping[str, Any] | None = None,
        *,
        max_entries: int = 256,
        store: Any = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._store = store
        self._now = now
        self._items: OrderedDict[
            tuple[str, str], dict[str, ReactionAction]
        ] = OrderedDict()
        if isinstance(stored, Mapping):
            self._restore(stored)
        self._prune_expired()
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    @staticmethod
    def _allowed_users(value: Any) -> tuple[str, ...]:
        if value in (None, []):
            return ()
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError("allowed_users must be a list of Matrix user IDs")
        users: list[str] = []
        seen: set[str] = set()
        for raw in value:
            user_id = str(raw).strip()
            if not user_id or not user_id.startswith("@") or ":" not in user_id[1:]:
                raise ValueError("allowed_users must contain valid Matrix user IDs")
            if user_id not in seen:
                seen.add(user_id)
                users.append(user_id)
        return tuple(users)

    @staticmethod
    def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as err:
            raise ValueError(f"{name} must be an integer") from err
        if result < minimum or result > maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return result

    def _parse_action(
        self,
        item: Mapping[str, Any],
        *,
        stored: bool = False,
    ) -> tuple[str, ReactionAction]:
        reaction = str(item.get("reaction", "")).strip()
        service = str(item.get("service", "")).strip()
        if not reaction:
            raise ValueError("reaction must not be empty")
        if service.count(".") != 1 or any(not part for part in service.split(".", 1)):
            raise ValueError("service must use domain.service format")
        target = item.get("target")
        data = item.get("data")
        if target is not None and not isinstance(target, Mapping):
            raise ValueError("target must be an object")
        if data is not None and not isinstance(data, Mapping):
            raise ValueError("data must be an object")

        allowed_users = self._allowed_users(item.get("allowed_users"))
        if stored and item.get("expires_at") is not None:
            try:
                expires_at = float(item["expires_at"])
            except (TypeError, ValueError) as err:
                raise ValueError("expires_at must be numeric") from err
        else:
            expires_in = self._bounded_int(
                item.get("expires_in", DEFAULT_EXPIRES_IN),
                name="expires_in",
                minimum=1,
                maximum=MAX_EXPIRES_IN,
            )
            expires_at = self._now() + expires_in

        remaining_uses = self._bounded_int(
            item.get(
                "remaining_uses" if stored else "max_uses",
                DEFAULT_MAX_USES,
            ),
            name="remaining_uses" if stored else "max_uses",
            minimum=1,
            maximum=MAX_USES,
        )
        return reaction, ReactionAction(
            service=service,
            target=target,
            data=data,
            expires_at=expires_at,
            remaining_uses=remaining_uses,
            allowed_users=allowed_users,
        )

    def _restore(self, stored: Mapping[str, Any]) -> None:
        for raw_room, raw_events in stored.items():
            room_id = str(raw_room).strip()
            if not room_id or not isinstance(raw_events, Mapping):
                continue
            for raw_event, raw_actions in raw_events.items():
                event_id = str(raw_event).strip()
                if not event_id or not isinstance(raw_actions, Mapping):
                    continue
                parsed: dict[str, ReactionAction] = {}
                for raw_reaction, raw_action in raw_actions.items():
                    if not isinstance(raw_action, Mapping):
                        continue
                    item = dict(raw_action)
                    item["reaction"] = str(raw_reaction)
                    try:
                        reaction, action = self._parse_action(item, stored=True)
                    except ValueError:
                        continue
                    if action.expires_at <= self._now():
                        continue
                    parsed[reaction] = action
                if parsed:
                    self._items[(room_id, event_id)] = parsed

    def _prune_expired(self) -> None:
        now = self._now()
        for key, actions in list(self._items.items()):
            for reaction, action in list(actions.items()):
                if action.expires_at <= now or action.remaining_uses <= 0:
                    actions.pop(reaction, None)
            if not actions:
                self._items.pop(key, None)

    def register(
        self,
        *,
        room_id: str,
        event_id: str,
        actions: Sequence[Mapping[str, Any]],
    ) -> None:
        """Register bounded reaction actions for one outbound Matrix event."""
        self._prune_expired()
        parsed: dict[str, ReactionAction] = {}
        for item in actions:
            reaction, action = self._parse_action(item)
            if reaction in parsed:
                raise ValueError(f"duplicate reaction action: {reaction}")
            parsed[reaction] = action
        if not parsed:
            return
        key = (room_id, event_id)
        self._items.pop(key, None)
        self._items[key] = parsed
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)

    def consume(
        self,
        *,
        room_id: str,
        event_id: str,
        reaction: str,
        sender: str | None = None,
    ) -> ReactionAction | None:
        """Consume one permitted use without spending it on unauthorized users."""
        self._prune_expired()
        key = (room_id, event_id)
        actions = self._items.get(key)
        if not actions:
            return None
        action = actions.get(reaction)
        if action is None:
            return None
        if action.allowed_users and sender not in action.allowed_users:
            return None

        action.remaining_uses -= 1
        if action.remaining_uses <= 0:
            actions.pop(reaction, None)
        if not actions:
            self._items.pop(key, None)
        return action

    def dump(self) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        """Return a JSON-safe copy for Home Assistant Store."""
        self._prune_expired()
        stored: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for (room_id, event_id), actions in self._items.items():
            room = stored.setdefault(room_id, {})
            room[event_id] = {
                reaction: {
                    "service": action.service,
                    "target": dict(action.target),
                    "data": dict(action.data),
                    "expires_at": action.expires_at,
                    "remaining_uses": action.remaining_uses,
                    "allowed_users": list(action.allowed_users),
                }
                for reaction, action in actions.items()
            }
        return stored

    async def async_save(self) -> None:
        """Persist the current registry when a Home Assistant Store is attached."""
        if self._store is not None:
            await self._store.async_save(self.dump())
