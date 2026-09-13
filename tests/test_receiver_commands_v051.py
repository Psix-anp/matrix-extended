from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_receiver():
    pkg_name = "matrix_extended_receiver_commands_v051_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    nio = types.ModuleType("nio")
    for name in (
        "ReactionEvent", "RedactionEvent", "RoomEncryptedAudio", "RoomEncryptedFile",
        "RoomEncryptedImage", "RoomEncryptedVideo", "RoomMessageAudio", "RoomMessageEmote",
        "RoomMessageFile", "RoomMessageImage", "RoomMessageNotice", "RoomMessageText",
        "RoomMessageUnknown", "RoomMessageVideo",
    ):
        setattr(nio, name, type(name, (), {}))
    sys.modules["nio"] = nio

    ha = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_core.HomeAssistant = object
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha_core

    def load_local(name: str):
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{name}", COMP / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    const = load_local("const")
    load_local("incoming")

    client = types.ModuleType(f"{pkg_name}.client")
    class MatrixExtendedError(Exception):
        pass
    client.MatrixExtendedError = MatrixExtendedError
    client.MatrixAccount = object
    sys.modules[f"{pkg_name}.client"] = client

    executor_module = types.ModuleType(f"{pkg_name}.command_executor")
    executor_module.CommandExecutor = FakeCommandExecutor
    sys.modules[f"{pkg_name}.command_executor"] = executor_module

    spec = importlib.util.spec_from_file_location(f"{pkg_name}.receiver", COMP / "receiver.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, const


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeHass:
    def __init__(self) -> None:
        self.bus = FakeBus()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeStatus:
    def __init__(self) -> None:
        self.receives = 0

    def mark_receive(self):
        self.receives += 1

    def mark_error(self, _error):
        pass


class FakePolicy:
    def __init__(self, allowed=True) -> None:
        self.allowed = allowed

    def should_process(self, **_kwargs):
        return self.allowed


class FakeClient:
    def add_event_callback(self, *_args):
        pass


class FakeRegistry:
    def __init__(self, command=None) -> None:
        self.command = command
        self.calls = []

    def match(self, body, *, sender, room_id):
        self.calls.append((body, sender, room_id))
        return self.command


class FakeCommandExecutor:
    instances = []

    def __init__(self, hass, account) -> None:
        self.calls = []
        FakeCommandExecutor.instances.append(self)

    async def async_execute(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return types.SimpleNamespace(
            command_id=command.id,
            status="success",
            handler_type="service",
            error=None,
        )


def make_room():
    return types.SimpleNamespace(
        room_id="!home:example.org",
        display_name="Home",
        canonical_alias="#home:example.org",
        user_name=lambda _sender: "Owner",
    )


def make_event(body="!garage open", *, source=None):
    if source is None:
        source = {"content": {"msgtype": "m.text", "body": body}}
    return types.SimpleNamespace(
        sender="@owner:example.org",
        event_id="$command",
        server_timestamp=123,
        transaction_id=None,
        source=source,
        body=body,
        formatted_body=None,
        decrypted=True,
        verified=True,
    )


def make_receiver(tmp_path, *, command=None, allowed=True):
    FakeCommandExecutor.instances.clear()
    mod, const = load_receiver()
    hass = FakeHass()
    registry = FakeRegistry(command)
    account = types.SimpleNamespace(
        client=FakeClient(),
        incoming_policy=FakePolicy(allowed),
        action_registry=None,
        command_registry=registry,
        status=FakeStatus(),
    )
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    return const, hass, account, registry, receiver, FakeCommandExecutor.instances[-1]


@pytest.mark.asyncio
async def test_exact_registered_command_executes_and_fires_diagnostic_event(tmp_path) -> None:
    command = types.SimpleNamespace(id="garage_open", trigger="garage open")
    const, hass, account, registry, receiver, executor = make_receiver(tmp_path, command=command)
    await receiver.async_handle_text(make_room(), make_event())

    assert registry.calls == [("!garage open", "@owner:example.org", "!home:example.org")]
    assert len(executor.calls) == 1
    _, kwargs = executor.calls[0]
    assert kwargs["room_id"] == "!home:example.org"
    assert kwargs["source_event_id"] == "$command"
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_COMMAND
    assert payload["command_id"] == "garage_open"
    assert payload["status"] == "success"
    assert account.status.receives == 1


@pytest.mark.asyncio
async def test_unknown_command_keeps_existing_message_event(tmp_path) -> None:
    const, hass, _, registry, receiver, executor = make_receiver(tmp_path, command=None)
    await receiver.async_handle_text(make_room(), make_event("!unknown"))
    assert registry.calls
    assert executor.calls == []
    assert hass.bus.events[-1][0] == const.EVENT_MESSAGE


@pytest.mark.asyncio
async def test_edit_never_executes_command(tmp_path) -> None:
    command = types.SimpleNamespace(id="garage_open", trigger="garage open")
    const, hass, _, registry, receiver, executor = make_receiver(tmp_path, command=command)
    source = {
        "content": {
            "msgtype": "m.text",
            "body": "* !garage open",
            "m.relates_to": {"rel_type": "m.replace", "event_id": "$old"},
            "m.new_content": {"msgtype": "m.text", "body": "!garage open"},
        }
    }
    await receiver.async_handle_text(make_room(), make_event("* !garage open", source=source))
    assert registry.calls == []
    assert executor.calls == []
    assert hass.bus.events[-1][0] == const.EVENT_EDIT


@pytest.mark.asyncio
async def test_account_allowlist_is_checked_before_command_registry(tmp_path) -> None:
    command = types.SimpleNamespace(id="garage_open", trigger="garage open")
    _, hass, account, registry, receiver, executor = make_receiver(tmp_path, command=command, allowed=False)
    await receiver.async_handle_text(make_room(), make_event())
    assert registry.calls == []
    assert executor.calls == []
    assert hass.bus.events == []
    assert account.status.receives == 0
