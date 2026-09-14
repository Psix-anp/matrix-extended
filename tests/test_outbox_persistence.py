from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "outbox.py"


def load():
    assert PATH.exists(), "persistent outbox module is not implemented"
    spec = importlib.util.spec_from_file_location("matrix_extended_outbox_v050", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeStore:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def async_save(self, data: dict) -> None:
        self.saved.append(data)


def test_outbox_round_trips_json_state_and_prunes_expired_items() -> None:
    mod = load()
    stored = {
        "items": [
            {"id": "expired", "created_at": 10.0, "payload": {"message": "old"}},
            {"id": "keep", "created_at": 90.0, "payload": {"message": "new"}},
        ]
    }
    outbox = mod.PersistentOutbox(
        stored,
        max_entries=4,
        ttl_seconds=50,
        now=lambda: 100.0,
    )

    assert [item.delivery_id for item in outbox.pending()] == ["keep"]
    assert outbox.dump() == {
        "items": [
            {"id": "keep", "created_at": 90.0, "payload": {"message": "new"}}
        ]
    }


def test_outbox_restore_ignores_invalid_and_duplicate_records() -> None:
    mod = load()
    outbox = mod.PersistentOutbox(
        {
            "items": [
                {"id": "keep", "created_at": 90, "payload": {"message": "first"}},
                {"id": "keep", "created_at": 91, "payload": {"message": "duplicate"}},
                {"id": "", "created_at": 92, "payload": {"message": "empty id"}},
                {"id": "bad-time", "created_at": "never", "payload": {"message": "bad"}},
                {"id": "bad-payload", "created_at": 93, "payload": ["not", "object"]},
            ]
        },
        ttl_seconds=100,
        now=lambda: 100.0,
    )

    pending = outbox.pending()
    assert len(pending) == 1
    assert pending[0].delivery_id == "keep"
    assert pending[0].payload == {"message": "first"}


@pytest.mark.asyncio
async def test_outbox_is_bounded_deduplicated_and_persisted() -> None:
    mod = load()
    store = FakeStore()
    outbox = mod.PersistentOutbox(
        store=store,
        max_entries=2,
        ttl_seconds=3600,
        now=lambda: 100.0,
    )

    await outbox.async_enqueue({"message": "one"}, delivery_id="one")
    saved_after_first = len(store.saved)
    await outbox.async_enqueue({"message": "one-duplicate"}, delivery_id="one")
    assert len(store.saved) == saved_after_first
    await outbox.async_enqueue({"message": "two"}, delivery_id="two")
    await outbox.async_enqueue({"message": "three"}, delivery_id="three")

    assert [item.delivery_id for item in outbox.pending()] == ["two", "three"]
    assert [item.payload["message"] for item in outbox.pending()] == ["two", "three"]
    assert store.saved[-1] == outbox.dump()

    await outbox.async_remove("two")
    assert [item.delivery_id for item in outbox.pending()] == ["three"]
    assert store.saved[-1] == outbox.dump()


@pytest.mark.asyncio
async def test_outbox_rejects_non_json_payload_without_saving() -> None:
    mod = load()
    store = FakeStore()
    outbox = mod.PersistentOutbox(store=store)

    with pytest.raises(ValueError, match="JSON"):
        await outbox.async_enqueue({"bad": object()}, delivery_id="bad")

    assert outbox.pending() == []
    assert store.saved == []


def test_matrix_transaction_id_is_stable_per_delivery_event_and_room() -> None:
    mod = load()
    first = mod.matrix_transaction_id("delivery", "text", "!room:example")
    assert first == mod.matrix_transaction_id("delivery", "text", "!room:example")
    assert first != mod.matrix_transaction_id("delivery", "media-0", "!room:example")
    assert first != mod.matrix_transaction_id("delivery", "text", "!other:example")
    assert first.startswith("mxext-")
    assert len(first) <= 64
