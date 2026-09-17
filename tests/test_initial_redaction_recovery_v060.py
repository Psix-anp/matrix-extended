from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
CLIENT = ROOT / "custom_components" / "matrix_extended" / "client.py"
SETUP = ROOT / "custom_components" / "matrix_extended" / "__init__.py"


def load_client(name: str):
    spec = importlib.util.spec_from_file_location(name, CLIENT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRedactionEvent:
    def __init__(
        self,
        *,
        redacts: str,
        sender: str,
        transaction_id: str | None = None,
    ) -> None:
        self.redacts = redacts
        self.sender = sender
        self.transaction_id = transaction_id


class FakeSyncResponse:
    def __init__(self, events) -> None:
        self.rooms = types.SimpleNamespace(
            join={
                "!control:test": types.SimpleNamespace(
                    timeline=types.SimpleNamespace(events=list(events))
                )
            }
        )


class FakeNio:
    def __init__(self, response) -> None:
        self.response = response
        self.sync_calls = []

    async def sync(self, **kwargs):
        self.sync_calls.append(dict(kwargs))
        return self.response


@pytest.mark.asyncio
async def test_initial_full_state_sync_buffers_only_redactions_for_panel_recovery() -> None:
    mod = load_client("matrix_extended_client_initial_redaction_v060")
    mod.SyncResponse = FakeSyncResponse
    mod.RedactionEvent = FakeRedactionEvent
    redaction = FakeRedactionEvent(
        redacts="$panel-root",
        sender="@operator:test",
        transaction_id=None,
    )
    nio = FakeNio(FakeSyncResponse([object(), redaction]))
    client = mod.MatrixClient.__new__(mod.MatrixClient)
    client._client = nio
    client._initial_redactions = []

    await client._async_sync(full_state=True)

    assert client.drain_initial_redactions() == [
        ("!control:test", "$panel-root", "@operator:test", None)
    ]
    assert client.drain_initial_redactions() == []
    assert nio.sync_calls == [
        {"timeout": 0, "full_state": True, "set_presence": "offline"}
    ]


@pytest.mark.asyncio
async def test_incremental_sync_does_not_feed_initial_redaction_recovery() -> None:
    mod = load_client("matrix_extended_client_incremental_redaction_v060")
    mod.SyncResponse = FakeSyncResponse
    mod.RedactionEvent = FakeRedactionEvent
    nio = FakeNio(
        FakeSyncResponse(
            [FakeRedactionEvent(redacts="$panel-root", sender="@operator:test")]
        )
    )
    client = mod.MatrixClient.__new__(mod.MatrixClient)
    client._client = nio
    client._initial_redactions = []

    await client._async_sync(full_state=False)

    assert client.drain_initial_redactions() == []


def test_setup_replays_initial_redactions_through_incoming_policy_before_receiver() -> None:
    source = SETUP.read_text(encoding="utf-8")
    start = source.index("async def async_setup_entry")
    end = source.index("async def async_unload_entry", start)
    setup = source[start:end]

    assert "drain_initial_redactions" in setup
    assert "account.incoming_policy.should_process" in setup
    assert setup.index("drain_initial_redactions") < setup.index(
        "await panel_manager.async_start()"
    )
    assert setup.index("async_handle_redaction") < setup.index(
        "await panel_manager.async_start()"
    )
    assert setup.index("drain_initial_redactions") < setup.index("receiver.register(")
