from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_executor():
    pkg_name = "matrix_extended_command_executor_v051_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    for name in ("commands", "content"):
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{name}", COMP / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.command_executor", COMP / "command_executor.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, sys.modules[f"{pkg_name}.commands"]


class FakeServices:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
        self.error = error

    async def async_call(self, domain, service, data, *, blocking, target):
        self.calls.append((domain, service, data, blocking, target))
        if self.error is not None:
            raise self.error


class FakeHass:
    def __init__(self, error: Exception | None = None) -> None:
        self.services = FakeServices(error)


class FakeClient:
    def __init__(self) -> None:
        self.prepared = []
        self.sent = []
        self.next_ids = ["$progress", "$edit"]

    async def async_prepare_rooms(self, rooms):
        prepared = [types.SimpleNamespace(room_id=room, encrypted=True) for room in rooms]
        self.prepared.append(list(rooms))
        return prepared

    async def async_send_prepared(self, rooms, content, *, tx_ids=None):
        self.sent.append((rooms, content, tx_ids))
        event_id = self.next_ids.pop(0)
        return [event_id for _ in rooms]


def service_command(mod_commands, *, progress=True):
    return mod_commands.CommandRegistry().register(
        {
            "id": "garage_open",
            "trigger": "garage open",
            "progress": progress,
            "handler": {
                "type": "service",
                "service": "script.turn_on",
                "target": {"entity_id": "script.open_garage"},
                "data": {"variables": {"source": "matrix"}},
            },
        }
    )


@pytest.mark.asyncio
async def test_service_command_uses_only_stored_service_target_and_data() -> None:
    mod, commands = load_executor()
    hass = FakeHass()
    client = FakeClient()
    account = types.SimpleNamespace(client=client)
    executor = mod.CommandExecutor(hass, account)

    result = await executor.async_execute(
        service_command(commands),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id=None,
    )

    assert result.status == "success"
    assert result.command_id == "garage_open"
    assert result.handler_type == "service"
    assert result.error is None
    assert hass.services.calls == [
        (
            "script",
            "turn_on",
            {"variables": {"source": "matrix"}},
            True,
            {"entity_id": "script.open_garage"},
        )
    ]


@pytest.mark.asyncio
async def test_progress_uses_reply_then_edits_same_event_on_success() -> None:
    mod, commands = load_executor()
    client = FakeClient()
    executor = mod.CommandExecutor(FakeHass(), types.SimpleNamespace(client=client))

    await executor.async_execute(
        service_command(commands),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id="$thread",
    )

    assert len(client.sent) == 2
    pending = client.sent[0][1]
    done = client.sent[1][1]
    assert pending["body"] == "⏳ Running…"
    assert pending["m.relates_to"]["m.in_reply_to"]["event_id"] == "$command"
    assert done["m.new_content"]["body"] == "✅ Done"
    assert done["m.relates_to"] == {"rel_type": "m.replace", "event_id": "$progress"}


@pytest.mark.asyncio
async def test_failure_edits_progress_and_returns_bounded_safe_error() -> None:
    mod, commands = load_executor()
    error = RuntimeError("secret-token=" + "x" * 500)
    client = FakeClient()
    executor = mod.CommandExecutor(FakeHass(error), types.SimpleNamespace(client=client))

    result = await executor.async_execute(
        service_command(commands),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id=None,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert len(result.error) <= 200
    failed = client.sent[-1][1]["m.new_content"]["body"]
    assert failed.startswith("❌ Failed: ")
    assert len(failed) <= len("❌ Failed: ") + 200
    assert "Traceback" not in failed


@pytest.mark.asyncio
async def test_progress_can_be_disabled_without_matrix_send() -> None:
    mod, commands = load_executor()
    client = FakeClient()
    executor = mod.CommandExecutor(FakeHass(), types.SimpleNamespace(client=client))

    result = await executor.async_execute(
        service_command(commands, progress=False),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id=None,
    )

    assert result.status == "success"
    assert client.prepared == []
    assert client.sent == []
