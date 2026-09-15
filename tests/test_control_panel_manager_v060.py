from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
MANAGER = COMP / "control_panel_manager.py"


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_modules():
    package_name = "mxpanel_manager_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(COMP)]
    sys.modules[package_name] = package

    loaded = {}
    for short in (
        "safe_actions",
        "control_panels",
        "control_panel_render",
        "content",
        "control_panel_runtime",
    ):
        loaded[short] = load_file(f"{package_name}.{short}", COMP / f"{short}.py")
    assert MANAGER.exists(), "control_panel_manager.py is not implemented yet"
    loaded["manager"] = load_file(f"{package_name}.control_panel_manager", MANAGER)
    return loaded


class FakeState:
    def __init__(self, state: str, **attributes) -> None:
        self.state = state
        self.attributes = attributes


class FakeStates:
    def __init__(self, values=None) -> None:
        self.values = dict(values or {})

    def get(self, entity_id: str):
        return self.values.get(entity_id)


class FakeHass:
    def __init__(self, states=None) -> None:
        self.states = FakeStates(states)


class FakeTracker:
    def __init__(self) -> None:
        self.items = []
        self.unsubscribed = 0

    def __call__(self, hass, entity_ids, callback):
        item = {"ids": set(entity_ids), "callback": callback, "active": True}
        self.items.append(item)

        def unsubscribe():
            if item["active"]:
                item["active"] = False
                self.unsubscribed += 1

        return unsubscribe

    def fire(self, entity_id: str) -> None:
        event = types.SimpleNamespace(data={"entity_id": entity_id})
        for item in list(self.items):
            if item["active"] and entity_id in item["ids"]:
                item["callback"](event)


class FakeClient:
    def __init__(self, *, connection_error, send_error) -> None:
        self.connection_error = connection_error
        self.send_error = send_error
        self.events = {}
        self.root_sends = []
        self.edits = []
        self.reactions = []
        self.pin_calls = []
        self.fail_edits = False
        self.fail_pin = False
        self._next_root = 1
        self._next_edit = 1

    async def async_get_event(self, room_id, event_id):
        return self.events.get((room_id, event_id))

    async def async_send_content(self, room_id, content):
        relation = content.get("m.relates_to", {})
        if relation.get("rel_type") == "m.replace":
            self.edits.append((room_id, content))
            if self.fail_edits:
                raise self.connection_error("matrix down")
            event_id = f"$edit{self._next_edit}"
            self._next_edit += 1
            return event_id

        event_id = f"$root{self._next_root}"
        self._next_root += 1
        self.root_sends.append((room_id, content))
        self.events[(room_id, event_id)] = {
            "event_id": event_id,
            "type": "m.room.message",
            "content": dict(content),
        }
        return event_id

    async def async_send_event(self, room_id, event_type, content):
        self.reactions.append((room_id, event_type, content))
        return f"$reaction{len(self.reactions)}"

    async def async_pin_event(self, room_id, event_id):
        self.pin_calls.append((room_id, event_id))
        if self.fail_pin:
            raise self.send_error("M_FORBIDDEN")
        return True


def build_panel(modules, *, debounce=0.01):
    safe = modules["safe_actions"]
    panels = modules["control_panels"]
    action = safe.SafeActionDefinition(
        id="toggle",
        handler=safe.ServiceActionHandler(
            service="light.toggle",
            target={"entity_id": "light.garage"},
            data={},
        ),
    )
    return panels.ControlPanelDefinition(
        panel_id="garage",
        room_id="!garage:example",
        title="Garage",
        enabled=True,
        entities=(panels.PanelEntity("light.garage", "Light"),),
        actions=(panels.PanelAction("toggle", "💡", "Toggle", action),),
        allowed_users=("@owner:example",),
        debounce=debounce,
    )


def build_manager(modules, *, runtime_store=None, client=None, hass=None, tracker=None, retry_delay=0.02):
    manager_mod = modules["manager"]
    runtime_mod = modules["control_panel_runtime"]
    runtime_store = runtime_store or runtime_mod.ControlPanelRuntimeStore()
    client = client or FakeClient(
        connection_error=manager_mod.MatrixConnectionError,
        send_error=manager_mod.MatrixSendError,
    )
    hass = hass or FakeHass({"light.garage": FakeState("off")})
    tracker = tracker or FakeTracker()
    manager = manager_mod.ControlPanelManager(
        hass=hass,
        client=client,
        panels={"garage": build_panel(modules)},
        runtime_store=runtime_store,
        track_state_change=tracker,
        retry_delay=retry_delay,
    )
    return manager, runtime_store, client, hass, tracker


@pytest.mark.asyncio
async def test_first_start_creates_one_root_reaction_and_pin_then_restart_reuses_root() -> None:
    modules = load_modules()
    manager, store, client, hass, tracker = build_manager(modules)

    await manager.async_start()
    runtime = store.get("garage")
    assert runtime is not None
    assert runtime.root_event_id == "$root1"
    assert runtime.generation == 1
    assert len(client.root_sends) == 1
    assert len(client.reactions) == 1
    assert client.pin_calls == [("!garage:example", "$root1")]

    await manager.async_stop()
    manager2, _, _, _, _ = build_manager(
        modules,
        runtime_store=store,
        client=client,
        hass=hass,
        tracker=FakeTracker(),
    )
    await manager2.async_start()

    assert len(client.root_sends) == 1
    assert len(client.reactions) == 1
    assert store.get("garage").root_event_id == "$root1"
    assert store.get("garage").generation == 1
    await manager2.async_stop()


@pytest.mark.asyncio
async def test_known_missing_root_requires_explicit_repair() -> None:
    modules = load_modules()
    runtime_mod = modules["control_panel_runtime"]
    store = runtime_mod.ControlPanelRuntimeStore()
    store.set(
        runtime_mod.PanelRuntime(
            panel_id="garage",
            room_id="!garage:example",
            root_event_id="$gone",
            generation=3,
            render_hash="old",
        )
    )
    manager, _, client, _, _ = build_manager(modules, runtime_store=store)

    await manager.async_start()

    runtime = store.get("garage")
    assert runtime.needs_repair is True
    assert runtime.root_event_id == "$gone"
    assert client.root_sends == []

    new_root = await manager.async_repair("garage")

    assert new_root == "$root1"
    assert runtime.needs_repair is False
    assert runtime.root_event_id == "$root1"
    assert runtime.generation == 4
    assert len(client.root_sends) == 1
    assert len(client.reactions) == 1
    assert client.pin_calls[-1] == ("!garage:example", "$root1")
    await manager.async_stop()


@pytest.mark.asyncio
async def test_two_state_changes_debounce_to_one_edit_and_unchanged_hash_sends_none() -> None:
    modules = load_modules()
    manager, store, client, hass, tracker = build_manager(modules)
    await manager.async_start()
    client.edits.clear()

    hass.states.values["light.garage"] = FakeState("on")
    tracker.fire("light.garage")
    tracker.fire("light.garage")
    await asyncio.sleep(0.05)

    assert len(client.edits) == 1
    assert client.edits[0][1]["m.relates_to"] == {
        "rel_type": "m.replace",
        "event_id": "$root1",
    }
    first_hash = store.get("garage").render_hash

    client.edits.clear()
    tracker.fire("light.garage")
    await asyncio.sleep(0.05)

    assert client.edits == []
    assert store.get("garage").render_hash == first_hash
    await manager.async_stop()


@pytest.mark.asyncio
async def test_matrix_outage_coalesces_to_one_retry_and_latest_render() -> None:
    modules = load_modules()
    manager, store, client, hass, tracker = build_manager(modules, retry_delay=0.03)
    await manager.async_start()
    client.edits.clear()
    client.fail_edits = True

    hass.states.values["light.garage"] = FakeState("on")
    tracker.fire("light.garage")
    await asyncio.sleep(0.02)
    assert manager.pending_retry_count == 1

    for index in range(10):
        hass.states.values["light.garage"] = FakeState("on" if index % 2 else "off")
        tracker.fire("light.garage")
    hass.states.values["light.garage"] = FakeState("on")
    tracker.fire("light.garage")
    await asyncio.sleep(0.02)

    assert manager.pending_retry_count == 1
    client.fail_edits = False
    await asyncio.sleep(0.08)

    assert manager.pending_retry_count == 0
    assert "Light: On" in client.edits[-1][1]["m.new_content"]["body"]
    assert store.get("garage").last_update_error is None
    await manager.async_stop()


@pytest.mark.asyncio
async def test_pin_permission_failure_is_nonfatal_and_diagnostic() -> None:
    modules = load_modules()
    manager, store, client, _, _ = build_manager(modules)
    client.fail_pin = True

    await manager.async_start()

    runtime = store.get("garage")
    assert runtime.root_event_id == "$root1"
    assert runtime.pin_status == "error"
    assert "M_FORBIDDEN" in runtime.pin_error
    assert runtime.needs_repair is False
    await manager.async_stop()


@pytest.mark.asyncio
async def test_stop_unsubscribes_cancels_tasks_and_clears_confirmations() -> None:
    modules = load_modules()
    runtime_mod = modules["control_panel_runtime"]
    confirmations = runtime_mod.PendingConfirmationRegistry(now=lambda: 1.0)
    manager, store, client, hass, tracker = build_manager(modules)
    manager.confirmations = confirmations
    await manager.async_start()
    confirmations.issue(
        prompt_event_id="$confirm",
        panel_id="garage",
        action_id="toggle",
        sender="@owner:example",
        generation=1,
    )

    hass.states.values["light.garage"] = FakeState("on")
    tracker.fire("light.garage")
    await manager.async_stop()

    assert tracker.unsubscribed == 1
    assert manager.pending_retry_count == 0
    assert confirmations.count == 0
