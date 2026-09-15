from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
TESTS = ROOT / "tests"
COMP = ROOT / "custom_components" / "matrix_extended"


def load_helper(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, TESTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakePanelManager:
    def __init__(self, *, handled: bool) -> None:
        self.handled = handled
        self.reactions = []
        self.redactions = []

    async def async_handle_reaction(self, room_id, event_id, reaction, sender):
        self.reactions.append((room_id, event_id, reaction, sender))
        return types.SimpleNamespace(
            handled=self.handled,
            action_id="panel_action" if self.handled else None,
            status="success" if self.handled else "ignored",
            error=None,
            confirmation_prompt_event_id=None,
        )

    async def async_handle_redaction(self, room_id, event_id):
        self.redactions.append((room_id, event_id))
        return True


def test_receiver_control_only_registers_reaction_and_redaction_only(tmp_path) -> None:
    helper = load_helper("test_receiver_behavior.py", "receiver_setup_helpers_v060")
    mod, _, _ = helper.load_receiver()
    account = helper.make_account()
    receiver = mod.MatrixInboundReceiver(
        helper.FakeHass(),
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )

    receiver.register(control_only=True)

    assert len(account.client.callbacks) == 2
    assert account.client.callbacks[0][1] is mod.ReactionEvent
    assert account.client.callbacks[1][1] is mod.RedactionEvent


def test_receiver_default_registration_stays_backward_compatible(tmp_path) -> None:
    helper = load_helper("test_receiver_behavior.py", "receiver_default_helpers_v060")
    mod, _, _ = helper.load_receiver()
    account = helper.make_account()
    receiver = mod.MatrixInboundReceiver(
        helper.FakeHass(),
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )

    receiver.register()

    assert len(account.client.callbacks) == 5


@pytest.mark.asyncio
async def test_control_only_panel_reaction_has_no_general_inbound_event(tmp_path) -> None:
    helper = load_helper("test_receiver_behavior.py", "receiver_control_only_panel_v060")
    mod, _, _ = helper.load_receiver()
    hass = helper.FakeHass()
    account = helper.make_account()
    panel = FakePanelManager(handled=True)
    account.panel_manager = panel
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    receiver.register(control_only=True)

    await receiver.async_handle_reaction(
        helper.make_room(), helper.make_event(key="💡", reacts_to="$panel")
    )

    assert panel.reactions == [
        ("!home:example", "$panel", "💡", "@user:example")
    ]
    assert hass.bus.events == []


@pytest.mark.asyncio
async def test_control_only_unknown_reaction_never_falls_to_legacy_registry(tmp_path) -> None:
    helper = load_helper("test_receiver_behavior.py", "receiver_control_only_legacy_v060")
    mod, _, _ = helper.load_receiver()
    hass = helper.FakeHass()
    legacy = helper.FakeRegistry(helper.Action(service="light.turn_on"))
    account = helper.make_account(registry=legacy)
    panel = FakePanelManager(handled=False)
    account.panel_manager = panel
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    receiver.register(control_only=True)

    await receiver.async_handle_reaction(
        helper.make_room(), helper.make_event(key="💡", reacts_to="$legacy")
    )

    assert panel.reactions == [
        ("!home:example", "$legacy", "💡", "@user:example")
    ]
    assert legacy.calls == []
    assert hass.services.calls == []
    assert hass.bus.events == []


@pytest.mark.asyncio
async def test_control_only_redaction_repairs_panel_without_general_event(tmp_path) -> None:
    helper = load_helper("test_receiver_behavior.py", "receiver_control_only_redaction_v060")
    mod, _, _ = helper.load_receiver()
    hass = helper.FakeHass()
    account = helper.make_account()
    panel = FakePanelManager(handled=True)
    account.panel_manager = panel
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    receiver.register(control_only=True)

    await receiver.async_handle_redaction(
        helper.make_room(), helper.make_event(redacts="$panel", reason="removed")
    )

    assert panel.redactions == [("!home:example", "$panel")]
    assert hass.bus.events == []


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"function not found: {name}")


def test_setup_entry_wires_panels_after_resolving_account_allowlist() -> None:
    source = _function_source(COMP / "__init__.py", "async_setup_entry")

    assert "normalize_control_panels" in source
    assert "ControlPanelManager" in source
    assert "SafeActionExecutor" in source
    assert "ControlPanelRuntimeStore" in source
    assert source.index("allowed_rooms = {") < source.index("normalize_control_panels(")
    assert "incoming_enabled or enabled_panels" in source
    assert "receiver.register(control_only=not incoming_enabled)" in source
    assert source.index("await panel_manager.async_start()") < source.index("receiver.register(")


def test_unload_stops_panel_manager_before_closing_matrix_client() -> None:
    source = _function_source(COMP / "__init__.py", "async_unload_entry")

    assert "await account.panel_manager.async_stop()" in source
    assert source.index("await account.panel_manager.async_stop()") < source.index(
        "await account.client.async_close()"
    )
