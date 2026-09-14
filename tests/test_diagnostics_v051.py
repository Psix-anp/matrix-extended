from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_status():
    spec = importlib.util.spec_from_file_location("matrix_extended_status_v051_test", COMP / "status.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_status_tracks_delivery_and_command_and_notifies() -> None:
    mod = load_status()
    status = mod.MatrixRuntimeStatus()
    notifications = []
    status.add_listener(lambda: notifications.append("changed"))

    status.mark_delivery("queued")
    assert status.last_delivery_status == "queued"
    status.mark_command(
        {
            "command_id": "garage_open",
            "sender": "@owner:example.org",
            "room_id": "!home:example.org",
            "handler_type": "service",
            "status": "success",
        }
    )
    assert status.last_command["command_id"] == "garage_open"
    assert len(notifications) == 2


def test_sensor_platform_exposes_compact_v051_diagnostics() -> None:
    source = (COMP / "sensor.py").read_text()
    for marker in (
        "MatrixOutboxSizeSensor",
        "MatrixLastDeliveryStatusSensor",
        "MatrixLastCommandSensor",
        '_attr_translation_key = "outbox_size"',
        '_attr_translation_key = "last_delivery_status"',
        '_attr_translation_key = "last_command"',
        "EntityCategory.DIAGNOSTIC",
    ):
        assert marker in source


def test_binary_sensor_exposes_e2ee_ready() -> None:
    source = (COMP / "binary_sensor.py").read_text()
    assert "MatrixE2EEReadyBinarySensor" in source
    assert '_attr_translation_key = "e2ee_ready"' in source
    assert "default_room_encrypted is True" in source


def test_delivery_and_command_paths_update_runtime_status() -> None:
    core = (COMP / "__init__.py").read_text()
    v05 = (COMP / "v05_services.py").read_text()
    receiver = (COMP / "receiver.py").read_text()
    assert "account.status.mark_delivery(status)" in core
    assert "account.status.mark_delivery(status)" in v05
    assert 'getattr(self._account.status, "mark_command", None)' in receiver
    assert "callable(mark_command)" in receiver
    assert "mark_command(" in receiver


def test_diagnostic_translation_keys_exist() -> None:
    strings = json.loads((COMP / "strings.json").read_text())
    ru = json.loads((COMP / "translations" / "ru.json").read_text())
    for doc in (strings, ru):
        assert "e2ee_ready" in doc["entity"]["binary_sensor"]
        sensors = doc["entity"]["sensor"]
        for key in ("outbox_size", "last_delivery_status", "last_command"):
            assert key in sensors
