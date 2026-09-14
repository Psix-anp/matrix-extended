from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_core_platforms_and_runtime_files_exist() -> None:
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    for platform in (
        "Platform.NOTIFY",
        "Platform.BINARY_SENSOR",
        "Platform.SENSOR",
        "Platform.SELECT",
    ):
        assert platform in init
    for filename in (
        "notify.py",
        "binary_sensor.py",
        "sensor.py",
        "select.py",
        "receiver.py",
        "services.yaml",
    ):
        assert (COMP / filename).is_file()


def test_persistent_e2ee_and_incoming_security_are_wired() -> None:
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    config = (COMP / "config_flow.py").read_text(encoding="utf-8")
    assert 'hass.config.path(".storage", DOMAIN, entry.entry_id)' in init
    for token in (
        "CONF_STORE_KEY",
        "CONF_REQUIRE_E2EE",
        "CONF_INCOMING_ENABLED",
        "CONF_ALLOWED_USERS",
        "CONF_ALLOWED_ROOMS",
    ):
        assert token in init or token in config


def test_interactive_actions_rooms_and_routes_are_declared() -> None:
    services = (COMP / "services.yaml").read_text(encoding="utf-8")
    init = (COMP / "__init__.py").read_text(encoding="utf-8")
    notify = (COMP / "notify.py").read_text(encoding="utf-8")
    config = (COMP / "config_flow.py").read_text(encoding="utf-8")
    for service in ("reply:", "react:", "edit:", "redact:"):
        assert service in services
    assert "rooms_snapshot" in notify
    assert "MatrixRoomNotifyEntity" in notify
    assert "ATTR_ROUTE" in init
    assert "ATTR_NOTIFICATION_KEY" in init
    assert "CONF_ROUTING_PROFILES" in config


def test_translations_cover_health_entities_and_room_select() -> None:
    for filename in ("strings.json", "translations/en.json", "translations/ru.json"):
        data = json.loads((COMP / filename).read_text(encoding="utf-8"))
        assert "require_e2ee" in data["config"]["step"]["user"]["data"]
        assert "binary_sensor" in data["entity"]
        assert "sensor" in data["entity"]
        assert "default_room" in data["entity"]["select"]
