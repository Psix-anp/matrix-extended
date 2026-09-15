from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
RUNTIME = ROOT / "custom_components" / "matrix_extended" / "control_panel_runtime.py"


def load_runtime():
    assert RUNTIME.exists(), "control_panel_runtime.py is not implemented yet"
    name = "matrix_extended_control_panel_runtime_v060"
    spec = importlib.util.spec_from_file_location(name, RUNTIME)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeStore:
    def __init__(self) -> None:
        self.saved = []

    async def async_save(self, value) -> None:
        self.saved.append(value)


def test_runtime_store_round_trip_is_json_safe_and_has_no_confirmations() -> None:
    mod = load_runtime()
    runtime = mod.PanelRuntime(
        panel_id="garage",
        room_id="!garage:example",
        root_event_id="$root",
        render_hash="abc123",
        generation=4,
        pin_status="pinned",
        pin_error=None,
        needs_repair=False,
        last_update_at=1234.5,
        last_update_error="temporary failure",
    )
    store = mod.ControlPanelRuntimeStore()
    store.set(runtime)

    dumped = store.dump()
    encoded = json.dumps(dumped, sort_keys=True)

    assert dumped["version"] == 1
    assert dumped["panels"]["garage"]["root_event_id"] == "$root"
    assert dumped["panels"]["garage"]["generation"] == 4
    assert dumped["panels"]["garage"]["pin_status"] == "pinned"
    assert "confirmation" not in encoded.lower()
    assert "sender" not in encoded.lower()

    restored = mod.ControlPanelRuntimeStore(stored=dumped)
    again = restored.get("garage")
    assert again is not None
    assert again.panel_id == "garage"
    assert again.room_id == "!garage:example"
    assert again.root_event_id == "$root"
    assert again.render_hash == "abc123"
    assert again.generation == 4
    assert again.last_update_error == "temporary failure"


@pytest.mark.asyncio
async def test_runtime_store_async_save_uses_attached_ha_store() -> None:
    mod = load_runtime()
    backing = FakeStore()
    store = mod.ControlPanelRuntimeStore(store=backing)
    store.set(mod.PanelRuntime(panel_id="garage", room_id="!garage:example"))

    await store.async_save()

    assert backing.saved == [store.dump()]


def test_confirmation_requires_same_sender_and_is_single_use() -> None:
    mod = load_runtime()
    clock = [100.0]
    registry = mod.PendingConfirmationRegistry(now=lambda: clock[0])
    registry.issue(
        prompt_event_id="$confirm",
        panel_id="garage",
        action_id="unlock",
        sender="@owner:example",
        generation=7,
        expires_in=30,
    )

    assert registry.count == 1
    assert (
        registry.consume(
            "$confirm", sender="@intruder:example", current_generation=7
        )
        is None
    )
    assert registry.count == 1

    confirmation = registry.consume(
        "$confirm", sender="@owner:example", current_generation=7
    )
    assert confirmation is not None
    assert confirmation.panel_id == "garage"
    assert confirmation.action_id == "unlock"
    assert confirmation.sender == "@owner:example"
    assert registry.count == 0
    assert (
        registry.consume(
            "$confirm", sender="@owner:example", current_generation=7
        )
        is None
    )


def test_confirmation_expires_after_thirty_seconds() -> None:
    mod = load_runtime()
    clock = [10.0]
    registry = mod.PendingConfirmationRegistry(now=lambda: clock[0])
    registry.issue(
        prompt_event_id="$confirm",
        panel_id="garage",
        action_id="open",
        sender="@owner:example",
        generation=1,
        expires_in=30,
    )

    clock[0] = 40.001

    assert (
        registry.consume(
            "$confirm", sender="@owner:example", current_generation=1
        )
        is None
    )
    assert registry.count == 0


def test_stale_generation_is_rejected_and_removed() -> None:
    mod = load_runtime()
    registry = mod.PendingConfirmationRegistry(now=lambda: 50.0)
    registry.issue(
        prompt_event_id="$old",
        panel_id="garage",
        action_id="open",
        sender="@owner:example",
        generation=2,
    )

    assert (
        registry.consume("$old", sender="@owner:example", current_generation=3)
        is None
    )
    assert registry.count == 0


def test_cancel_is_same_sender_single_use() -> None:
    mod = load_runtime()
    registry = mod.PendingConfirmationRegistry(now=lambda: 50.0)
    registry.issue(
        prompt_event_id="$cancel",
        panel_id="garage",
        action_id="disarm",
        sender="@owner:example",
        generation=9,
    )

    assert (
        registry.cancel(
            "$cancel", sender="@other:example", current_generation=9
        )
        is False
    )
    assert registry.count == 1
    assert (
        registry.cancel(
            "$cancel", sender="@owner:example", current_generation=9
        )
        is True
    )
    assert registry.count == 0
    assert (
        registry.cancel(
            "$cancel", sender="@owner:example", current_generation=9
        )
        is False
    )


def test_clear_panel_and_global_clear_drop_pending_prompts() -> None:
    mod = load_runtime()
    registry = mod.PendingConfirmationRegistry(now=lambda: 1.0)
    registry.issue(
        prompt_event_id="$garage",
        panel_id="garage",
        action_id="unlock",
        sender="@owner:example",
        generation=1,
    )
    registry.issue(
        prompt_event_id="$alarm",
        panel_id="alarm",
        action_id="disarm",
        sender="@owner:example",
        generation=1,
    )

    assert registry.count == 2
    registry.clear_panel("garage")
    assert registry.count == 1
    assert (
        registry.consume("$garage", sender="@owner:example", current_generation=1)
        is None
    )
    assert (
        registry.consume("$alarm", sender="@owner:example", current_generation=1)
        is not None
    )

    registry.issue(
        prompt_event_id="$again",
        panel_id="garage",
        action_id="unlock",
        sender="@owner:example",
        generation=2,
    )
    registry.clear()
    assert registry.count == 0
