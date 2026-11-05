"""Persist rotated Matrix credentials before using them."""

import asyncio
from collections.abc import Callable, Mapping
from typing import Any
from weakref import WeakValueDictionary

from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_SESSION_ID


class EntrySession:
    """Keep a durable journal for one login and mirror it to the config entry."""

    _locks: WeakValueDictionary[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = (
        WeakValueDictionary()
    )

    def __init__(
        self, entry: Any, store: Any, update_entry: Callable[..., Any],
        *, can_save: Callable[[], bool] = lambda: True,
    ) -> None:
        self._entry = entry
        self._store = store
        self._update_entry = update_entry
        self._can_save = can_save
        self._session_id = entry.data.get(CONF_SESSION_ID)
        self._internal_update: tuple[dict, dict, str] | None = None
        lock_key = (asyncio.get_running_loop(), entry.entry_id)
        self._lock = self._locks.setdefault(lock_key, asyncio.Lock())

    def _matches_current_login(self) -> bool:
        return bool(self._session_id and self._entry.data.get(CONF_SESSION_ID) == self._session_id)

    def _mirror(self, access_token: str, refresh_token: str | None) -> None:
        data = dict(self._entry.data)
        data[CONF_ACCESS_TOKEN] = access_token
        if refresh_token is None:
            data.pop(CONF_REFRESH_TOKEN, None)
        else:
            data[CONF_REFRESH_TOKEN] = refresh_token
        if data != self._entry.data:
            self._internal_update = (data, dict(self._entry.options), self._entry.title)
            self._update_entry(self._entry, data=data)

    def is_internal_update(self) -> bool:
        """Tell the reload listener whether only our credentials changed."""
        return self._internal_update == (
            self._entry.data, self._entry.options, self._entry.title
        )

    async def async_restore(self) -> None:
        """Recover a committed rotation after an abrupt HA restart."""
        async with self._lock:
            if not self._matches_current_login():
                return
            data = await self._store.async_load()
            if not isinstance(data, Mapping) or data.get(CONF_SESSION_ID) != self._session_id:
                return
            access_token = data.get(CONF_ACCESS_TOKEN)
            refresh_token = data.get(CONF_REFRESH_TOKEN)
            if self._matches_current_login() and isinstance(access_token, str) and access_token:
                if refresh_token is None or (isinstance(refresh_token, str) and refresh_token):
                    self._mirror(access_token, refresh_token)

    async def async_save(self, access_token: str, refresh_token: str | None) -> None:
        """Commit rotated credentials before the client activates them."""
        async with self._lock:
            if not self._matches_current_login():
                raise OSError("Cannot persist credentials for a superseded Matrix login")
            data = {
                CONF_SESSION_ID: self._session_id,
                CONF_ACCESS_TOKEN: access_token,
                CONF_REFRESH_TOKEN: refresh_token,
            }
            async def persist() -> None:
                if not self._can_save():
                    raise OSError("Cannot persist Matrix credentials during shutdown or removal")
                await self._store.async_save(data)

            write = asyncio.create_task(persist())
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                # The executor may still be replacing the file. Drain it before
                # a replacement session or removal can acquire the entry lock.
                while not write.done():
                    try:
                        await asyncio.shield(write)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not write.cancelled():
                    write.exception()
                raise
            # Home Assistant Store can log a write failure without raising it.
            if await self._store.async_load() != data or not self._matches_current_login():
                raise OSError("Cannot persist rotated Matrix credentials")
            self._mirror(access_token, refresh_token)

    async def async_remove(self) -> None:
        """Delete the credential journal when the account is removed from HA."""
        async with self._lock:
            await self._store.async_remove()
