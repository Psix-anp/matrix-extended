from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
from uuid import uuid4

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
PKG = "matrix_extended_widget_protocol_v060b2_testpkg"
package = types.ModuleType(PKG)
package.__path__ = [str(COMP)]
sys.modules[PKG] = package
protocol = importlib.import_module(f"{PKG}.widget_protocol")

WIDGET_EVENT_TYPE = protocol.WIDGET_EVENT_TYPE
WIDGET_SCHEMA = protocol.WIDGET_SCHEMA
WidgetActionRequest = protocol.WidgetActionRequest
WidgetConfirmRequest = protocol.WidgetConfirmRequest
WidgetHeartbeatRequest = protocol.WidgetHeartbeatRequest
WidgetSubscribeRequest = protocol.WidgetSubscribeRequest
build_widget_message = protocol.build_widget_message
parse_widget_request = protocol.parse_widget_request

ROOM = "!living:matrix.test"
PANEL = "living"
GENERATION = 7


def base(op: str, **extra):
    payload = {
        "schema": 1,
        "op": op,
        "room_id": ROOM,
        "panel_id": PANEL,
        "generation": GENERATION,
    }
    payload.update(extra)
    return payload


def test_protocol_constants_are_versioned():
    assert WIDGET_EVENT_TYPE == "io.psix.matrix_extended.widget.v1"
    assert WIDGET_SCHEMA == 1


def test_parse_subscribe_and_heartbeat():
    subscribe = parse_widget_request(base("subscribe"))
    heartbeat = parse_widget_request(base("heartbeat"))
    assert isinstance(subscribe, WidgetSubscribeRequest)
    assert isinstance(heartbeat, WidgetHeartbeatRequest)
    assert subscribe.room_id == ROOM
    assert subscribe.panel_id == PANEL
    assert subscribe.generation == GENERATION


def test_parse_panel_action_requires_uuid_request_id():
    request_id = str(uuid4())
    parsed = parse_widget_request(
        base(
            "action",
            request_id=request_id,
            kind="panel_action",
            action_id="movie_scene",
        )
    )
    assert isinstance(parsed, WidgetActionRequest)
    assert parsed.request_id == request_id
    assert parsed.kind == "panel_action"
    assert parsed.action_id == "movie_scene"
    assert parsed.entity_id is None


def test_parse_entity_control_keeps_bounded_value():
    request_id = str(uuid4())
    parsed = parse_widget_request(
        base(
            "action",
            request_id=request_id,
            kind="entity_control",
            entity_id="light.living_room",
            control="brightness",
            value=65,
        )
    )
    assert isinstance(parsed, WidgetActionRequest)
    assert parsed.entity_id == "light.living_room"
    assert parsed.control == "brightness"
    assert parsed.value == 65


@pytest.mark.parametrize("op", ["confirm", "cancel"])
def test_parse_confirm_and_cancel(op: str):
    request_id = str(uuid4())
    confirmation_id = str(uuid4())
    parsed = parse_widget_request(
        base(op, request_id=request_id, confirmation_id=confirmation_id)
    )
    assert isinstance(parsed, WidgetConfirmRequest)
    assert parsed.op == op
    assert parsed.confirmation_id == confirmation_id


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"schema": 2, "op": "subscribe", "room_id": ROOM, "panel_id": PANEL, "generation": 1}, "schema"),
        (base("explode"), "op"),
        ({"schema": 1, "op": "subscribe", "panel_id": PANEL, "generation": 1}, "room_id"),
        ({"schema": 1, "op": "subscribe", "room_id": ROOM, "generation": 1}, "panel_id"),
        ({"schema": 1, "op": "subscribe", "room_id": ROOM, "panel_id": PANEL}, "generation"),
        (base("subscribe", generation=-1), "generation"),
        (base("action", request_id="not-a-uuid", kind="panel_action", action_id="x"), "request_id"),
        (base("subscribe", panel_id="x" * 129), "panel_id"),
    ],
)
def test_invalid_envelopes_fail_closed(payload, message):
    with pytest.raises(ValueError, match=message):
        parse_widget_request(payload)


@pytest.mark.parametrize("forbidden", ["service", "target", "data", "template", "yaml"])
def test_action_rejects_forbidden_execution_keys_anywhere(forbidden: str):
    request_id = str(uuid4())
    payload = base(
        "action",
        request_id=request_id,
        kind="entity_control",
        entity_id="light.living_room",
        control="toggle",
        value={"nested": {forbidden: "evil"}},
    )
    with pytest.raises(ValueError, match="forbidden"):
        parse_widget_request(payload)


def test_build_widget_message_emits_common_envelope_without_none_values():
    content = build_widget_message(
        op="result",
        room_id=ROOM,
        panel_id=PANEL,
        generation=GENERATION,
        request_id=str(uuid4()),
        status="accepted",
        error=None,
    )
    assert content["schema"] == 1
    assert content["op"] == "result"
    assert content["status"] == "accepted"
    assert "error" not in content
