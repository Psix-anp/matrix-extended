from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_v02_registers_health_platforms_and_persistent_store() -> None:
    source = (COMP / "__init__.py").read_text()
    assert "Platform.BINARY_SENSOR" in source
    assert "Platform.SENSOR" in source
    assert 'hass.config.path(".storage", DOMAIN, entry.entry_id)' in source
    assert "CONF_STORE_KEY" in source
    assert "CONF_REQUIRE_E2EE" in source


def test_config_flow_creates_e2ee_store_key_and_policy() -> None:
    source = (COMP / "config_flow.py").read_text()
    assert "secrets.token_urlsafe" in source
    assert "CONF_STORE_KEY" in source
    assert "CONF_REQUIRE_E2EE" in source


def test_health_entity_platforms_exist() -> None:
    assert (COMP / "binary_sensor.py").exists()
    assert (COMP / "sensor.py").exists()


def test_translations_expose_health_entities_and_e2ee_option() -> None:
    for filename in ("strings.json", "translations/en.json", "translations/ru.json"):
        data = json.loads((COMP / filename).read_text())
        assert "require_e2ee" in data["config"]["step"]["user"]["data"]
        assert "binary_sensor" in data["entity"]
        assert "sensor" in data["entity"]
