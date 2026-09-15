from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
TESTS = ROOT / "tests"
COMP = ROOT / "custom_components" / "matrix_extended"


def load_test_helper(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, TESTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeExecutionResult:
    def __init__(self, action_id: str, *, status: str = "success", error=None):
        self.action_id = action_id
        self.status = status
        self.handler_type = "service"
        self.error = error


class FakeExecutor:
    def __init__(self) -> None:
        self.actions = []

    async def async_execute(self, action, *, context=None):
        self.actions.append((action, context))
        return FakeExecutionResult(action.id)


class PanelClient:
    def __init__(self) -> None:
        self.contents = []
        self.events = []
        self._next = 1

    async def async_send_content(self, room_id, content):
        self.contents.append((room_id, content))
        event_id = f"$prompt{self._next}"
        self._next += 1
        return event_id

    async def async_send_event(self, room_id, event_type, content):
        self.events.append((room_id, event_type, content))
        return f"$event{len(self.events)}"


def make_manager(*, dangerous: bool = False, allowed_users=("@owner:example",)):
    helper = load_test_helper(
        "test_control_panel_manager_v060.py", "panel_manager_helpers_v060"
    )
    modules = helper.load_modules()
    safe = modules["safe_actions"]
    panels = modules["control_panels"]
    runtime_mod = modules["control_panel_runtime"]
    manager_mod = modules["manager"]

    definition = panels.ControlPanelDefinition(
        panel_id="garage",
        room_id="!garage:example",
        title="Garage",
        enabled=True,
        entities=(),
        actions=(
            panels.PanelAction(
                "unlock",
                "🔓",
                "Unlock garage",
                safe.SafeActionDefinition(
                    id="unlock",
                    handler=safe.ServiceActionHandler(
                        service="lock.unlock",
                        target={"entity_id": "lock.garage"},
                        data={},
                    ),
                    confirmation_required=dangerous,
                ),
            ),
        ),
        allowed_users=allowed_users,
        debounce=1.5,
    )
    store = runtime_mod.ControlPanelRuntimeStore()
    store.set(
        runtime_mod.PanelRuntime(
            panel_id="garage",
            room_id="!garage:example",
            root_event_id="$panel",
            render_hash="hash",
            generation=5,
        )
    )
    client = PanelClient()
    executor = FakeExecutor()
    manager = manager_mod.ControlPanelManager(
        hass=types.SimpleNamespace(states=types.SimpleNamespace(get=lambda _: None)),
        client=client,
        panels={"garage": definition},
        runtime_store=store,
    )
    manager.safe_action_executor = executor
    return manager, store, client, executor


@pytest.mark.asyncio
async def test_low_risk_panel_reaction_executes_exact_preconfigured_action() -> None:
    manager, _, _, executor = make_manager(dangerous=False)

    outcome = await manager.async_handle_reaction(
        "!garage:example", "$panel", "🔓", "@owner:example"
    )

    assert outcome.handled is True
    assert outcome.action_id == "unlock"
    assert outcome.status == "success"
    assert outcome.confirmation_prompt_event_id is None
    assert len(executor.actions) == 1
    action, _ = executor.actions[0]
    assert action.handler.service == "lock.unlock"
    assert action.handler.target == {"entity_id": "lock.garage"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("room_id", "event_id", "reaction", "sender"),
    [
        ("!other:example", "$panel", "🔓", "@owner:example"),
        ("!garage:example", "$forged", "🔓", "@owner:example"),
        ("!garage:example", "$panel", "❓", "@owner:example"),
        ("!garage:example", "$panel", "🔓", "@intruder:example"),
    ],
)
async def test_forged_or_unauthorized_panel_reactions_never_execute(
    room_id, event_id, reaction, sender
) -> None:
    manager, _, _, executor = make_manager(dangerous=False)

    outcome = await manager.async_handle_reaction(
        room_id, event_id, reaction, sender
    )

    assert outcome.status != "success"
    assert executor.actions == []


@pytest.mark.asyncio
async def test_dangerous_action_requires_same_sender_confirmation_and_is_single_use() -> None:
    manager, store, client, executor = make_manager(dangerous=True)

    first = await manager.async_handle_reaction(
        "!garage:example", "$panel", "🔓", "@owner:example"
    )

    assert first.handled is True
    assert first.status == "confirmation_required"
    assert first.confirmation_prompt_event_id == "$prompt1"
    assert executor.actions == []
    prompt = client.contents[-1][1]
    assert prompt["body"] == "⚠️ Confirm: Unlock garage"
    assert "lock.unlock" not in str(prompt)
    assert "lock.garage" not in str(prompt)
    assert [event[2]["m.relates_to"]["key"] for event in client.events] == ["✅", "❌"]

    wrong_sender = await manager.async_handle_reaction(
        "!garage:example", "$prompt1", "✅", "@intruder:example"
    )
    assert wrong_sender.status != "success"
    assert executor.actions == []
    assert manager.confirmations.count == 1

    confirmed = await manager.async_handle_reaction(
        "!garage:example", "$prompt1", "✅", "@owner:example"
    )
    assert confirmed.status == "success"
    assert len(executor.actions) == 1
    assert manager.confirmations.count == 0

    replay = await manager.async_handle_reaction(
        "!garage:example", "$prompt1", "✅", "@owner:example"
    )
    assert replay.status != "success"
    assert len(executor.actions) == 1

    # A repaired/replaced root invalidates confirmations from the old generation.
    second = await manager.async_handle_reaction(
        "!garage:example", "$panel", "🔓", "@owner:example"
    )
    assert second.confirmation_prompt_event_id == "$prompt2"
    store.get("garage").generation += 1
    stale = await manager.async_handle_reaction(
        "!garage:example", "$prompt2", "✅", "@owner:example"
    )
    assert stale.status != "success"
    assert len(executor.actions) == 1


@pytest.mark.asyncio
async def test_dangerous_confirmation_can_be_cancelled_once() -> None:
    manager, _, _, executor = make_manager(dangerous=True)
    first = await manager.async_handle_reaction(
        "!garage:example", "$panel", "🔓", "@owner:example"
    )

    cancelled = await manager.async_handle_reaction(
        "!garage:example",
        first.confirmation_prompt_event_id,
        "❌",
        "@owner:example",
    )
    assert cancelled.handled is True
    assert cancelled.status == "cancelled"
    assert executor.actions == []
    assert manager.confirmations.count == 0


class FakePanelManager:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = []
        self.redactions = []

    async def async_handle_reaction(self, room_id, event_id, reaction, sender):
        self.calls.append((room_id, event_id, reaction, sender))
        return self.outcome

    async def async_handle_redaction(self, room_id, event_id):
        self.redactions.append((room_id, event_id))
        return True


@pytest.mark.asyncio
async def test_receiver_routes_panel_before_legacy_reaction_registry(tmp_path) -> None:
    helper = load_test_helper("test_receiver_behavior.py", "receiver_helpers_v060")
    receiver_mod, const, _ = helper.load_receiver()
    hass = helper.FakeHass()
    legacy = helper.FakeRegistry(helper.Action(service="light.turn_on"))
    account = helper.make_account(registry=legacy)
    panel = FakePanelManager(
        types.SimpleNamespace(
            handled=True,
            action_id="unlock",
            status="success",
            error=None,
            confirmation_prompt_event_id=None,
        )
    )
    account.panel_manager = panel
    receiver = receiver_mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )

    event = helper.make_event(key="🔓", reacts_to="$panel")
    await receiver.async_handle_reaction(helper.make_room(), event)

    assert panel.calls == [
        ("!home:example", "$panel", "🔓", "@user:example")
    ]
    assert legacy.calls == []
    assert hass.services.calls == []
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_REACTION
    assert payload["action_executed"] is True
    assert payload["panel_action_id"] == "unlock"


@pytest.mark.asyncio
async def test_receiver_forwards_authorized_root_redaction_to_panel_manager(tmp_path) -> None:
    helper = load_test_helper("test_receiver_behavior.py", "receiver_redaction_helpers_v060")
    receiver_mod, const, _ = helper.load_receiver()
    hass = helper.FakeHass()
    account = helper.make_account()
    panel = FakePanelManager(
        types.SimpleNamespace(
            handled=False,
            action_id=None,
            status=None,
            error=None,
            confirmation_prompt_event_id=None,
        )
    )
    account.panel_manager = panel
    receiver = receiver_mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    event = helper.make_event(redacts="$panel", reason="removed")

    await receiver.async_handle_redaction(helper.make_room(), event)

    assert panel.redactions == [("!home:example", "$panel")]
    assert hass.bus.events[-1][0] == const.EVENT_REDACTION
