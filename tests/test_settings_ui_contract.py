from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
CONFIG_FLOW = COMP / "config_flow.py"
INIT = COMP / "__init__.py"
SERVICES = COMP / "services.yaml"
STRINGS = COMP / "strings.json"
RU = COMP / "translations" / "ru.json"
MANIFEST = COMP / "manifest.json"
README = ROOT / "README.md"
README_RU = ROOT / "README.ru.md"


def test_options_flow_is_split_into_graphical_sections() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "async_show_menu" in source
    for step in (
        "async_step_general",
        "async_step_incoming",
        "async_step_media",
        "async_step_routes",
        "async_step_route_add",
        "async_step_route_edit",
        "async_step_route_delete",
    ):
        assert step in source
    assert "selector.ObjectSelector()" not in source


def test_default_room_and_tls_are_editable_options_used_at_runtime() -> None:
    flow = CONFIG_FLOW.read_text(encoding="utf-8")
    runtime = INIT.read_text(encoding="utf-8")
    assert "CONF_DEFAULT_ROOM" in flow
    assert "CONF_VERIFY_SSL" in flow
    assert "_entry_value(entry, CONF_DEFAULT_ROOM" in runtime
    assert "_entry_value(entry, CONF_VERIFY_SSL" in runtime


def test_routes_use_graphical_crud_instead_of_raw_json() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "SelectSelector" in source
    assert "CONF_ROUTE_NAME" in source
    assert "CONF_ROUTE_ROOMS" in source
    assert "normalize_routing_profiles" in source


def test_action_editor_prefers_native_graphical_selectors() -> None:
    services = SERVICES.read_text(encoding="utf-8")
    assert services.count("config_entry:") >= 9
    assert "integration: matrix_extended" in services
    assert "language: {}" in services
    assert "domain: tts" in services
    # Complex media and reaction actions must render as structured forms, not raw YAML boxes.
    assert "label_field: filename" in services
    assert "label_field: reaction" in services
    assert "multiple: true" in services


def test_settings_and_actions_have_current_bilingual_help() -> None:
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    ru = json.loads(RU.read_text(encoding="utf-8"))
    for payload in (strings, ru):
        options = payload["options"]["step"]
        for step in ("init", "general", "incoming", "media", "routes", "route_add", "route_edit", "route_delete"):
            assert step in options
            assert options[step].get("title")
            assert options[step].get("description")
        for action in (
            "send",
            "send_media",
            "send_voice",
            "transcribe_voice",
            "send_location",
            "reply",
            "react",
            "edit",
            "redact",
            "purge_media",
        ):
            assert payload["services"][action].get("description")


def test_public_docs_track_current_version_and_gui_first_setup() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] == "0.5.4"
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        assert "0.5.4" in text
        assert "Settings" in text or "Настройки" in text
        assert "YAML" in text
