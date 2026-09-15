from __future__ import annotations

import importlib.util
from pathlib import Path
import types

import pytest
from nio.responses import ErrorResponse

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
CLIENT = COMP / "client.py"
CONTENT = COMP / "content.py"


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_client(mod, nio_client):
    client = mod.MatrixClient.__new__(mod.MatrixClient)
    client._client = nio_client
    client._room_cache = {}
    return client


class FakeNio:
    def __init__(self) -> None:
        self.event_response = types.SimpleNamespace(
            event=types.SimpleNamespace(
                source={"event_id": "$panel", "type": "m.room.message", "content": {"body": "x"}}
            )
        )
        self.state_response = types.SimpleNamespace(content={"pinned": ["$foreign"]})
        self.put_response = types.SimpleNamespace(event_id="$state")
        self.get_event_calls = []
        self.get_state_calls = []
        self.put_state_calls = []

    async def room_get_event(self, room_id, event_id):
        self.get_event_calls.append((room_id, event_id))
        return self.event_response

    async def room_get_state_event(self, room_id, event_type, state_key=""):
        self.get_state_calls.append((room_id, event_type, state_key))
        return self.state_response

    async def room_put_state(self, room_id, event_type, content, state_key=""):
        self.put_state_calls.append(
            {
                "room_id": room_id,
                "event_type": event_type,
                "content": content,
                "state_key": state_key,
            }
        )
        return self.put_response


@pytest.mark.asyncio
async def test_get_event_returns_source_mapping() -> None:
    mod = load_file("matrix_extended_client_control_state", CLIENT)
    nio = FakeNio()
    client = make_client(mod, nio)

    event = await client.async_get_event("!room:test", "$panel")

    assert event == {
        "event_id": "$panel",
        "type": "m.room.message",
        "content": {"body": "x"},
    }
    assert nio.get_event_calls == [("!room:test", "$panel")]


@pytest.mark.asyncio
async def test_get_event_returns_none_only_for_matrix_not_found() -> None:
    mod = load_file("matrix_extended_client_control_missing", CLIENT)
    nio = FakeNio()
    client = make_client(mod, nio)
    nio.event_response = ErrorResponse("missing", "M_NOT_FOUND")
    assert await client.async_get_event("!room:test", "$missing") is None

    nio.event_response = ErrorResponse("forbidden", "M_FORBIDDEN")
    with pytest.raises(mod.MatrixSendError, match="forbidden"):
        await client.async_get_event("!room:test", "$private")


@pytest.mark.asyncio
async def test_state_get_and_put_wrap_matrix_nio() -> None:
    mod = load_file("matrix_extended_client_control_state_rw", CLIENT)
    nio = FakeNio()
    client = make_client(mod, nio)

    state = await client.async_get_state_event(
        "!room:test", "m.room.pinned_events"
    )
    event_id = await client.async_put_state_event(
        "!room:test",
        "io.psix.matrix_extended.test",
        {"enabled": True},
        state_key="panel",
    )

    assert state == {"pinned": ["$foreign"]}
    assert event_id == "$state"
    assert nio.get_state_calls == [
        ("!room:test", "m.room.pinned_events", "")
    ]
    assert nio.put_state_calls[-1] == {
        "room_id": "!room:test",
        "event_type": "io.psix.matrix_extended.test",
        "content": {"enabled": True},
        "state_key": "panel",
    }


@pytest.mark.asyncio
async def test_pin_merges_foreign_pins_and_is_idempotent() -> None:
    mod = load_file("matrix_extended_client_control_pin", CLIENT)
    nio = FakeNio()
    client = make_client(mod, nio)

    assert await client.async_pin_event("!room:test", "$panel") is True
    assert nio.put_state_calls == [
        {
            "room_id": "!room:test",
            "event_type": "m.room.pinned_events",
            "content": {"pinned": ["$foreign", "$panel"]},
            "state_key": "",
        }
    ]

    nio.put_state_calls.clear()
    nio.state_response = types.SimpleNamespace(
        content={"pinned": ["$foreign", "$panel"]}
    )
    assert await client.async_pin_event("!room:test", "$panel") is False
    assert nio.put_state_calls == []


def test_panel_metadata_is_preserved_in_root_and_edit() -> None:
    content = load_file("matrix_extended_content_control", CONTENT)
    marker = {
        "io.psix.matrix_extended.panel": {"schema": 1, "panel_id": "garage"}
    }

    root = content.build_text_content("Garage", extra_content=marker)
    edit = content.build_edit_content(
        "Garage updated", event_id="$panel", extra_content=marker
    )

    assert root["io.psix.matrix_extended.panel"] == {
        "schema": 1,
        "panel_id": "garage",
    }
    assert edit["m.new_content"]["io.psix.matrix_extended.panel"] == {
        "schema": 1,
        "panel_id": "garage",
    }


@pytest.mark.parametrize("reserved", ["msgtype", "body", "m.relates_to", "m.new_content"])
def test_extra_content_cannot_override_matrix_message_structure(reserved) -> None:
    content = load_file("matrix_extended_content_control_reserved", CONTENT)
    with pytest.raises(ValueError, match="reserved"):
        content.build_text_content("Garage", extra_content={reserved: "bad"})
    with pytest.raises(ValueError, match="reserved"):
        content.build_edit_content(
            "Garage", event_id="$panel", extra_content={reserved: "bad"}
        )
