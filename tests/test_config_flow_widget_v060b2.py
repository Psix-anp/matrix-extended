from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
CONFIG_FLOW = COMP / "config_flow.py"
STRINGS = COMP / "strings.json"
EN = COMP / "translations" / "en.json"
RU = COMP / "translations" / "ru.json"
WIDGET_CONFIG = COMP / "widget_config.py"


def test_panel_manage_exposes_widget_subflow() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert '"panel_widget"' in source
    assert "async def async_step_panel_widget(" in source
    assert "async def async_step_panel_widget_entity(" in source
    assert "widget_enabled" in source
    assert "widget_url" in source
    assert "widget_controls" in source
    assert "confirm_controls" in source


def test_widget_config_helper_contains_exact_device_without_secrets() -> None:
    assert WIDGET_CONFIG.exists(), "widget_config.py is not implemented yet"
    source = WIDGET_CONFIG.read_text(encoding="utf-8")
    assert "build_widget_config" in source
    assert "device_id" in source
    assert "$matrix_room_id" in source
    assert "$matrix_user_id" in source
    lowered = source.lower()
    assert "access_token" not in lowered
    assert "store_key" not in lowered
    assert "password" not in lowered


def test_widget_options_are_translated_in_english_and_russian() -> None:
    docs = [
        json.loads(STRINGS.read_text(encoding="utf-8")),
        json.loads(EN.read_text(encoding="utf-8")),
        json.loads(RU.read_text(encoding="utf-8")),
    ]
    for doc in docs:
        options = doc["options"]["step"]
        assert "panel_widget" in options
        assert "panel_widget_entity" in options
        assert "widget_enabled" in options["panel_widget"]["data"]
        assert "widget_url" in options["panel_widget"]["data"]
        assert "widget_controls" in options["panel_widget_entity"]["data"]
        assert "confirm_controls" in options["panel_widget_entity"]["data"]
