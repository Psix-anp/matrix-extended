from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "actions.py"


def load():
    spec = importlib.util.spec_from_file_location("matrix_extended_actions_v050", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeStore:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def async_save(self, data: dict) -> None:
        self.saved.append(data)


@pytest.mark.asyncio
async def test_registry_store_tracks_registration_and_one_shot_consumption() -> None:
    mod = load()
    store = FakeStore()
    registry = mod.ReactionActionRegistry(store=store)
    registry.register(
        room_id="!room:example",
        event_id="$message",
        actions=[
            {
                "reaction": "✅",
                "service": "counter.increment",
                "target": {"entity_id": "counter.matrix_reaction"},
            }
        ],
    )

    await registry.async_save()
    assert store.saved[-1] == {
        "!room:example": {
            "$message": {
                "✅": {
                    "service": "counter.increment",
                    "target": {"entity_id": "counter.matrix_reaction"},
                    "data": {},
                }
            }
        }
    }

    assert registry.consume(
        room_id="!room:example",
        event_id="$message",
        reaction="✅",
    ) is not None
    await registry.async_save()
    assert store.saved[-1] == {}
    assert len(store.saved) == 2
