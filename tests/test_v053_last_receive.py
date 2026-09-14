from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_status_module():
    path = COMP / "status.py"
    spec = importlib.util.spec_from_file_location("matrix_extended_status_v053", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_status_keeps_last_incoming_event_kind_and_payload() -> None:
    mod = load_status_module()
    status = mod.MatrixRuntimeStatus()
    payload = {
        "sender": "@sergey:matrix.test",
        "room_id": "!room:matrix.test",
        "event_id": "$event",
        "reaction": "✅",
        "reacts_to": "$message",
        "encrypted": True,
    }

    status.mark_receive_event("reaction", payload)

    assert status.last_receive is not None
    assert status.last_receive_type == "reaction"
    assert status.last_receive_payload == payload
    assert status.last_receive_payload is not payload


def test_last_receive_sensor_is_event_kind_with_event_attributes() -> None:
    sensor = (COMP / "sensor.py").read_text(encoding="utf-8")
    assert "return self._account.status.last_receive_type" in sensor
    assert "received_at" in sensor
    assert "last_receive_payload" in sensor
    assert "MatrixLastReceiveSensor" in sensor
