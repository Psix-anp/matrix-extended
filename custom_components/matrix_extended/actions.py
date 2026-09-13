"""Runtime registry for reaction-triggered Home Assistant actions."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any


class ReactionAction:
    """A Home Assistant service call attached to a Matrix reaction."""

    __slots__ = ("service", "target", "data")

    def __init__(
        self,
        *,
        service: str,
        target: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        self.service = service
        self.target = dict(target or {})
        self.data = dict(data or {})


class ReactionActionRegistry:
    """Bounded one-shot mapping from Matrix reactions to explicit HA actions."""

    def __init__(
        self,
        stored: Mapping[str, Any] | None = None,
        *,
        max_entries: int = 256,
        store: Any = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._store = store
        self._items: OrderedDict[
            tuple[str, str], dict[str, ReactionAction]
        ] = OrderedDict()
        if isinstance(stored, Mapping):
            for raw_room, raw_events in stored.items():
                room_id = str(raw_room).strip()
                if not room_id or not isinstance(raw_events, Mapping):
                    continue
                for raw_event, raw_actions in raw_events.items():
                    event_id = str(raw_event).strip()
                    if not event_id or not isinstance(raw_actions, Mapping):
                        continue
                    actions: list[dict[str, Any]] = []
                    for raw_reaction, raw_action in raw_actions.items():
                        if not isinstance(raw_action, Mapping):
                            continue
                        item = dict(raw_action)
                        item["reaction"] = str(raw_reaction)
                        try:
                            self._parse_action(item)
                        except ValueError:
                            continue
                        actions.append(item)
                    if actions:
                        self.register(room_id=room_id, event_id=event_id, actions=actions)

    @staticmethod
    def _parse_action(item: Mapping[str, Any]) -> tuple[str, ReactionAction]:
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
        return reaction, ReactionAction(service=service, target=target, data=data)

    def register(
        self,
        *,
        room_id: str,
        event_id: str,
        actions: Sequence[Mapping[str, Any]],
    ) -> None:
        """Register reaction actions for one outbound Matrix event."""
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
    ) -> ReactionAction | None:
        """Consume a matching action once to avoid duplicate side effects."""
        key = (room_id, event_id)
        actions = self._items.get(key)
        if not actions:
            return None
        action = actions.pop(reaction, None)
        if not actions:
            self._items.pop(key, None)
        return action

    def dump(self) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
        """Return a JSON-safe copy for Home Assistant Store."""
        stored: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
        for (room_id, event_id), actions in self._items.items():
            room = stored.setdefault(room_id, {})
            room[event_id] = {
                reaction: {
                    "service": action.service,
                    "target": dict(action.target),
                    "data": dict(action.data),
                }
                for reaction, action in actions.items()
            }
        return stored

    async def async_save(self) -> None:
        """Persist the current registry when a Home Assistant Store is attached."""
        if self._store is not None:
            await self._store.async_save(self.dump())
