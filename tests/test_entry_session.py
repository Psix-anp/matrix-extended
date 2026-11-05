import asyncio
from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def session_module(monkeypatch):
    name = "matrix_entry_session_test"
    package = ModuleType(name)
    source = Path(__file__).parents[1] / "custom_components/matrix_extended"
    assert (source / "entry_session.py").is_file(), "entry session persistence missing"
    package.__path__ = [str(source)]
    monkeypatch.setitem(sys.modules, name, package)
    return import_module(f"{name}.entry_session")


class MemoryStore:
    def __init__(self, data=None, *, writable=True):
        self.data = data
        self.writable = writable

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        if self.writable:
            self.data = data

    async def async_remove(self):
        self.data = None


def make_entry():
    return SimpleNamespace(data={"session_id": "session-1", "access_token": "old",
                                 "refresh_token": "old-refresh", "room": "room"},
                           options={}, title="Matrix", entry_id="test-entry")


@pytest.mark.asyncio
async def test_token_rotation_is_saved_before_config_update(session_module):
    entry = make_entry()
    store = MemoryStore()

    def update(target, *, data):
        assert store.data == {"session_id": "session-1", "access_token": "new",
                              "refresh_token": "rotated"}
        target.data = data

    session = session_module.EntrySession(entry, store, update)
    await session.async_save("new", "rotated")
    assert entry.data["room"] == "room"
    assert entry.data["access_token"] == "new"
    assert session.is_internal_update()
    entry.options = {"example": True}
    assert not session.is_internal_update()


@pytest.mark.asyncio
async def test_restore_uses_journal_only_for_the_same_login(session_module):
    entry = make_entry()
    store = MemoryStore({"session_id": "session-1", "access_token": "new",
                         "refresh_token": "rotated"})
    def update(target, *, data):
        target.data = data

    await session_module.EntrySession(entry, store, update).async_restore()
    assert entry.data["access_token"] == "new"
    entry.data = {"session_id": "new-login", "access_token": "reauthenticated"}
    await session_module.EntrySession(entry, store, update).async_restore()
    assert entry.data == {"session_id": "new-login", "access_token": "reauthenticated"}


@pytest.mark.asyncio
async def test_failed_durable_write_keeps_existing_credentials(session_module):
    entry = make_entry()
    store = MemoryStore(writable=False)
    def update(*args, **kwargs):
        pytest.fail("credentials must not be updated after a failed save")

    with pytest.raises(OSError, match="persist"):
        await session_module.EntrySession(entry, store, update).async_save("new", "rotated")
    assert entry.data["access_token"] == "old"


@pytest.mark.asyncio
async def test_shutdown_refuses_a_deferred_journal_write(session_module):
    entry = make_entry()
    store = MemoryStore()
    session = session_module.EntrySession(entry, store, None, can_save=lambda: False)
    with pytest.raises(OSError, match="shutdown"):
        await session.async_save("new", "rotated")
    assert store.data is None
    assert entry.data["access_token"] == "old"


@pytest.mark.asyncio
async def test_removing_entry_clears_rotated_tokens(session_module):
    entry = make_entry()
    store = MemoryStore({"session_id": "session-1", "access_token": "new",
                         "refresh_token": "rotated"})
    await session_module.EntrySession(entry, store, None).async_remove()
    assert store.data is None


@pytest.mark.asyncio
async def test_cancelled_save_is_drained_before_removal(session_module):
    started = asyncio.Event()
    finish = asyncio.Event()
    entry = make_entry()

    class BlockingStore(MemoryStore):
        async def async_save(self, data):
            started.set()
            await finish.wait()
            await super().async_save(data)

    store = BlockingStore()
    session = session_module.EntrySession(entry, store, None)
    pending_write = asyncio.create_task(session.async_save("new", "rotated"))
    await started.wait()
    pending_write.cancel()
    removal = asyncio.create_task(session.async_remove())
    try:
        await asyncio.sleep(0)
        assert not removal.done()
    finally:
        finish.set()
        await asyncio.gather(pending_write, removal, return_exceptions=True)
    assert store.data is None


@pytest.mark.asyncio
async def test_superseded_writer_cannot_overwrite_new_login(session_module):
    entry = make_entry()
    first_write_started = asyncio.Event()
    release_first_write = asyncio.Event()

    class BlockingStore(MemoryStore):
        async def async_save(self, data):
            if data["session_id"] == "session-1":
                first_write_started.set()
                await release_first_write.wait()
            await super().async_save(data)

    def update(target, *, data):
        target.data = data

    store = BlockingStore()
    old_session = session_module.EntrySession(entry, store, update)
    old_save = asyncio.create_task(old_session.async_save("obsolete", "old-rotation"))
    await first_write_started.wait()
    entry.data = {"session_id": "session-2", "access_token": "reauthed"}
    new_session = session_module.EntrySession(entry, store, update)
    new_save = asyncio.create_task(new_session.async_save("valid", "new-rotation"))
    await asyncio.sleep(0)
    release_first_write.set()
    with pytest.raises(OSError, match="persist"):
        await old_save
    await new_save
    assert entry.data["access_token"] == "valid"
    assert store.data["session_id"] == "session-2"
