from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "client.py"


class _Response:
    pass


class ErrorResponse(_Response):
    pass


class AsyncClientConfig:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class AsyncClient:
    last_instance = None

    def __init__(self, *args, **kwargs) -> None:
        type(self).last_instance = self
        self.rooms = {}
        self.sent: list[dict] = []

    async def room_send(self, **kwargs):
        self.sent.append(kwargs)
        response = _Response()
        response.event_id = f"$event-{len(self.sent)}"
        return response


def load(monkeypatch):
    nio = types.ModuleType("nio")
    nio.AsyncClient = AsyncClient
    nio.AsyncClientConfig = AsyncClientConfig
    responses = types.ModuleType("nio.responses")
    for name in (
        "ErrorResponse",
        "LoginResponse",
        "RoomResolveAliasResponse",
        "SyncResponse",
        "UploadResponse",
        "WhoamiResponse",
    ):
        setattr(responses, name, ErrorResponse if name == "ErrorResponse" else type(name, (_Response,), {}))
    monkeypatch.setitem(sys.modules, "nio", nio)
    monkeypatch.setitem(sys.modules, "nio.responses", responses)

    spec = importlib.util.spec_from_file_location("matrix_extended_client_txid_v050", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    return mod


def make_client(mod):
    return mod.MatrixClient(
        homeserver="https://matrix.example",
        user_id="@ha:example",
        access_token="token",
        device_id="DEVICE",
        verify_ssl=True,
        store_path="/tmp/matrix-store",
        store_key="secret-key",
    )


@pytest.mark.asyncio
async def test_prepared_send_forwards_transaction_id_per_room(monkeypatch) -> None:
    mod = load(monkeypatch)
    client = make_client(mod)
    rooms = [
        mod.PreparedRoom("!one:example", True),
        mod.PreparedRoom("!two:example", True),
    ]

    result = await client.async_send_event_prepared(
        rooms,
        "m.room.message",
        {"msgtype": "m.text", "body": "queued"},
        tx_ids=["mxext-one", "mxext-two"],
    )

    assert result == ["$event-1", "$event-2"]
    assert [call["tx_id"] for call in AsyncClient.last_instance.sent] == [
        "mxext-one",
        "mxext-two",
    ]


@pytest.mark.asyncio
async def test_prepared_send_rejects_transaction_id_count_mismatch(monkeypatch) -> None:
    mod = load(monkeypatch)
    client = make_client(mod)
    rooms = [
        mod.PreparedRoom("!one:example", True),
        mod.PreparedRoom("!two:example", True),
    ]

    with pytest.raises(ValueError, match="tx_ids"):
        await client.async_send_event_prepared(
            rooms,
            "m.room.message",
            {"msgtype": "m.text", "body": "queued"},
            tx_ids=["only-one"],
        )

    assert AsyncClient.last_instance.sent == []
