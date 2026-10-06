from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
import types
from uuid import uuid4

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
PKG = "matrix_extended_widget_manager_v060b2_testpkg"
package = types.ModuleType(PKG)
package.__path__ = [str(COMP)]
sys.modules[PKG] = package
panels_mod = importlib.import_module(f"{PKG}.control_panels")
safe_mod = importlib.import_module(f"{PKG}.safe_actions")
manager_mod = importlib.import_module(f"{PKG}.widget_manager")
protocol_mod = importlib.import_module(f"{PKG}.widget_protocol")
sessions_mod = importlib.import_module(f"{PKG}.widget_sessions")

ControlPanelDefinition = panels_mod.ControlPanelDefinition
PanelAction = panels_mod.PanelAction
PanelEntity = panels_mod.PanelEntity
SafeActionDefinition = safe_mod.SafeActionDefinition
ServiceActionHandler = safe_mod.ServiceActionHandler
WidgetControlManager = manager_mod.WidgetControlManager
WIDGET_EVENT_TYPE = protocol_mod.WIDGET_EVENT_TYPE
WidgetSessionRegistry = sessions_mod.WidgetSessionRegistry

ROOM = "!living:matrix.test"
OWNER = "@owner:matrix.test"
OTHER = "@other:matrix.test"
PANEL_ID = "living"


@dataclass
class State:
    state: str
    attributes: dict


@dataclass
class Runtime:
    panel_id: str = PANEL_ID
    room_id: str = ROOM
    generation: int = 3
    needs_repair: bool = False


class RuntimeStore:
    def __init__(self, runtime=None):
        self.runtime = runtime or Runtime()

    def get(self, panel_id):
        return self.runtime if panel_id == PANEL_ID else None


class States:
    def __init__(self):
        self.data = {
            "light.living": State(
                "on",
                {"brightness": 128, "supported_color_modes": ["brightness"]},
            )
        }

    def get(self, entity_id):
        return self.data.get(entity_id)


class Hass:
    def __init__(self):
        self.states = States()


class Transport:
    def __init__(self):
        self.sent = []

    async def async_send(self, event_type, user_id, device_id, content):
        self.sent.append((event_type, user_id, device_id, content))


class Executor:
    def __init__(self):
        self.actions = []

    async def async_execute(self, action, *, context=None):
        self.actions.append(action)
        return type("Result", (), {"status": "success", "error": None})()


def make_panel(*, enabled=True, widget_enabled=True, allowed_users=(OWNER,), confirm=False):
    panel_action = PanelAction(
        id="movie",
        reaction="🎬",
        label="Movie",
        action=SafeActionDefinition(
            id="movie",
            handler=ServiceActionHandler(
                "scene.turn_on", {"entity_id": "scene.movie"}, {}
            ),
            confirmation_required=confirm,
        ),
    )
    return ControlPanelDefinition(
        panel_id=PANEL_ID,
        room_id=ROOM,
        title="Living",
        enabled=enabled,
        entities=(
            PanelEntity(
                "light.living",
                "Light",
                ("toggle", "brightness"),
                ("brightness",) if confirm else (),
            ),
        ),
        actions=(panel_action,),
        allowed_users=allowed_users,
        widget_enabled=widget_enabled,
        widget_url="https://widgets.example/panel",
    )


def make_manager(*, panel=None, runtime=None, now=lambda: 100.0):
    transport = Transport()
    executor = Executor()
    sessions = WidgetSessionRegistry(now=now)
    manager = WidgetControlManager(
        hass=Hass(),
        transport=transport,
        panels={PANEL_ID: panel or make_panel()},
        runtime_store=RuntimeStore(runtime),
        safe_action_executor=executor,
        account_allowed_users={OWNER},
        account_allowed_room_ids={ROOM},
        sessions=sessions,
        now=now,
    )
    return manager, transport, executor, sessions


def subscribe(generation=3):
    return {
        "schema": 1,
        "op": "subscribe",
        "room_id": ROOM,
        "panel_id": PANEL_ID,
        "generation": generation,
    }


def action(**extra):
    value = {
        "schema": 1,
        "op": "action",
        "room_id": ROOM,
        "panel_id": PANEL_ID,
        "generation": 3,
        "request_id": str(uuid4()),
        "kind": "panel_action",
        "action_id": "movie",
    }
    value.update(extra)
    return value


@pytest.mark.asyncio
async def test_subscribe_authorizes_and_returns_complete_snapshot():
    manager, transport, _, sessions = make_manager()
    await manager.async_handle(OWNER, subscribe())
    assert sessions.active_users(PANEL_ID) == (OWNER,)
    assert len(transport.sent) == 1
    event_type, user, device, content = transport.sent[0]
    assert event_type == WIDGET_EVENT_TYPE
    assert (user, device) == (OWNER, "*")
    assert content["op"] == "state"
    assert content["generation"] == 3
    assert content["title"] == "Living"
    assert content["entities"][0]["entity_id"] == "light.living"
    assert content["actions"][0]["id"] == "movie"


@pytest.mark.asyncio
async def test_subscribe_generation_zero_is_bootstrap_but_stale_nonzero_is_rejected():
    manager, transport, _, sessions = make_manager()
    await manager.async_handle(OWNER, subscribe(generation=0))
    assert sessions.active_users(PANEL_ID) == (OWNER,)
    transport.sent.clear()
    await manager.async_handle(OWNER, subscribe(generation=2))
    assert transport.sent[-1][3]["op"] == "error"
    assert transport.sent[-1][3]["status"] == "stale_generation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sender,payload,panel,runtime",
    [
        (OTHER, subscribe(), None, None),
        (OWNER, {**subscribe(), "room_id": "!forged:matrix.test"}, None, None),
        (OWNER, subscribe(), make_panel(enabled=False), None),
        (OWNER, subscribe(), make_panel(widget_enabled=False), None),
        (OWNER, subscribe(), None, Runtime(needs_repair=True)),
    ],
)
async def test_subscribe_rejects_unauthorized_or_unusable_panel(sender, payload, panel, runtime):
    manager, transport, _, sessions = make_manager(panel=panel, runtime=runtime)
    await manager.async_handle(sender, payload)
    assert sessions.active_users(PANEL_ID) == ()
    assert not transport.sent or transport.sent[-1][3]["op"] == "error"


@pytest.mark.asyncio
async def test_panel_action_executes_stored_definition_once_and_duplicate_request_is_rejected():
    manager, transport, executor, _ = make_manager()
    payload = action()
    await manager.async_handle(OWNER, payload)
    await manager.async_handle(OWNER, payload)
    assert len(executor.actions) == 1
    assert executor.actions[0].handler.service == "scene.turn_on"
    assert transport.sent[0][3]["status"] == "accepted"
    assert transport.sent[1][3]["status"] == "duplicate_request"


@pytest.mark.asyncio
async def test_entity_control_builds_local_service_and_never_trusts_service_payload():
    manager, transport, executor, _ = make_manager()
    payload = action(
        kind="entity_control",
        action_id=None,
        entity_id="light.living",
        control="brightness",
        value=65,
    )
    payload.pop("action_id")
    await manager.async_handle(OWNER, payload)
    assert executor.actions[0].handler.service == "light.turn_on"
    assert executor.actions[0].handler.target == {"entity_id": "light.living"}
    assert executor.actions[0].handler.data == {"brightness_pct": 65}
    assert transport.sent[-1][3]["status"] == "accepted"

    malicious = dict(payload, request_id=str(uuid4()), service="lock.unlock")
    await manager.async_handle(OWNER, malicious)
    assert len(executor.actions) == 1


@pytest.mark.asyncio
async def test_success_does_not_optimistically_publish_state():
    manager, transport, _, _ = make_manager()
    await manager.async_handle(OWNER, action())
    assert [item[3]["op"] for item in transport.sent] == ["result"]


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.mark.asyncio
async def test_confirmation_is_same_sender_single_use_and_expires():
    clock = Clock()
    manager, transport, executor, _ = make_manager(panel=make_panel(confirm=True), now=clock)
    await manager.async_handle(OWNER, action())
    result = transport.sent[-1][3]
    assert result["status"] == "confirmation_required"
    confirmation_id = result["confirmation_id"]
    assert executor.actions == []

    wrong = {
        "schema": 1,
        "op": "confirm",
        "room_id": ROOM,
        "panel_id": PANEL_ID,
        "generation": 3,
        "request_id": str(uuid4()),
        "confirmation_id": confirmation_id,
    }
    await manager.async_handle(OTHER, wrong)
    assert executor.actions == []

    clock.advance(31)
    confirm = dict(wrong, request_id=str(uuid4()))
    await manager.async_handle(OWNER, confirm)
    assert executor.actions == []
    assert transport.sent[-1][3]["status"] == "confirmation_expired"


@pytest.mark.asyncio
async def test_confirmation_executes_once_and_cancel_never_executes():
    manager, transport, executor, _ = make_manager(panel=make_panel(confirm=True))
    await manager.async_handle(OWNER, action())
    cid = transport.sent[-1][3]["confirmation_id"]
    confirm = {
        "schema": 1,
        "op": "confirm",
        "room_id": ROOM,
        "panel_id": PANEL_ID,
        "generation": 3,
        "request_id": str(uuid4()),
        "confirmation_id": cid,
    }
    await manager.async_handle(OWNER, confirm)
    await manager.async_handle(OWNER, dict(confirm, request_id=str(uuid4())))
    assert len(executor.actions) == 1

    await manager.async_handle(OWNER, action(request_id=str(uuid4())))
    cid2 = transport.sent[-1][3]["confirmation_id"]
    cancel = dict(
        confirm,
        op="cancel",
        request_id=str(uuid4()),
        confirmation_id=cid2,
    )
    await manager.async_handle(OWNER, cancel)
    assert len(executor.actions) == 1
    assert transport.sent[-1][3]["status"] == "cancelled"
