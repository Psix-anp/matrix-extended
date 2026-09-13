from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_manifest_bumped_to_v04() -> None:
    manifest = json.loads((COMP / "manifest.json").read_text())
    assert manifest["version"] == "0.5.0"


def test_v04_adds_room_select_and_room_notify_support() -> None:
    init = (COMP / "__init__.py").read_text()
    notify = (COMP / "notify.py").read_text()
    assert "Platform.SELECT" in init
    assert (COMP / "select.py").exists()
    assert "rooms_snapshot" in notify
    assert "MatrixRoomNotifyEntity" in notify


def test_send_service_exposes_route_and_notification_key() -> None:
    const = (COMP / "const.py").read_text()
    services = (COMP / "services.yaml").read_text()
    init = (COMP / "__init__.py").read_text()
    for token in ("ATTR_ROUTE", "ATTR_NOTIFICATION_KEY"):
        assert token in const
        assert token in init
    assert "route:" in services
    assert "notification_key:" in services


def test_routing_profiles_are_configurable_and_optional() -> None:
    const = (COMP / "const.py").read_text()
    config = (COMP / "config_flow.py").read_text()
    assert "CONF_ROUTING_PROFILES" in const
    assert "CONF_ROUTING_PROFILES" in config
    assert "routing_profiles" in (COMP / "strings.json").read_text()


def test_select_translation_exists() -> None:
    for filename in ("strings.json", "translations/en.json", "translations/ru.json"):
        data = json.loads((COMP / filename).read_text())
        assert "select" in data["entity"]
        assert "default_room" in data["entity"]["select"]
