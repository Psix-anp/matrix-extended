from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
CONFIG_FLOW = COMP / "config_flow.py"
INIT = COMP / "__init__.py"
SERVICES = COMP / "services.yaml"
STRINGS = COMP / "strings.json"
EN = COMP / "translations" / "en.json"
RU = COMP / "translations" / "ru.json"
MANIFEST = COMP / "manifest.json"
README = ROOT / "README.md"
README_RU = ROOT / "README.ru.md"
SETTINGS = ROOT / "docs" / "SETTINGS.md"
SETTINGS_RU = ROOT / "docs" / "SETTINGS.ru.md"


def test_options_flow_is_split_into_graphical_sections() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")
    assert "async_show_menu" in source
    for step in (
        "async_step_general",
        "async_step_incoming",
        "async_step_media",
        "async_step_voice_assist",
        "async_step_routes",
        "async_step_route_add",
        "async_step_route_edit",
        "async_step_route_delete",
    ):
        assert step in source
    assert "selector.ObjectSelector()" not in source


def test_default_room_and_tls_are_editable_connection_settings() -> None:
    flow = CONFIG_FLOW.read_text(encoding="utf-8")
    runtime = INIT.read_text(encoding="utf-8")
    assert "connection_data[CONF_DEFAULT_ROOM] = room" in flow
    assert "connection_data[CONF_VERIFY_SSL] = verify_ssl" in flow
    assert "self.hass.config_entries.async_update_entry" in flow
    # Runtime reads connection parameters from ConfigEntry.data, so GUI changes
    # use the same source of truth as initial setup and the room select entity.
    assert "data[CONF_DEFAULT_ROOM]" in runtime
    assert "verify_ssl=data[CONF_VERIFY_SSL]" in runtime


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
    assert "label_field: filename" in services
    assert "label_field: reaction" in services
    assert "multiple: true" in services


def test_settings_and_actions_have_current_bilingual_help() -> None:
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    en = json.loads(EN.read_text(encoding="utf-8"))
    ru = json.loads(RU.read_text(encoding="utf-8"))
    assert en == strings
    for payload in (strings, ru):
        options = payload["options"]["step"]
        for step in (
            "init",
            "general",
            "incoming",
            "media",
            "voice_assist",
            "routes",
            "route_add",
            "route_edit",
            "route_delete",
        ):
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
            "register_command",
            "unregister_command",
        ):
            assert payload["services"][action].get("description")


def test_public_docs_track_manifest_version_and_gui_first_setup() -> None:
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    for path in (README, README_RU):
        text = path.read_text(encoding="utf-8")
        assert version in text
        assert "Settings" in text or "Настройки" in text
        assert "YAML" in text


def test_public_readme_explains_install_connection_and_ai_assistance() -> None:
    english = README.read_text(encoding="utf-8")
    russian = README_RU.read_text(encoding="utf-8")

    assert "AI-assisted" in english
    assert "HACS" in english and "custom repository" in english.lower()
    assert "First connection" in english
    assert "Voice Assist" in english
    assert "register_command" in english

    assert "ИИ" in russian
    assert "HACS" in russian and "пользовательск" in russian.lower()
    assert "Первое подключение" in russian
    assert "Voice Assist" in russian
    assert "register_command" in russian


def test_settings_guides_cover_initial_setup_and_all_option_sections() -> None:
    for path in (SETTINGS, SETTINGS_RU):
        text = path.read_text(encoding="utf-8")
        for token in (
            "homeserver",
            "default_room",
            "verify_ssl",
            "require_e2ee",
            "incoming_enabled",
            "allowed_users",
            "allowed_rooms",
            "download_incoming_media",
            "voice_assist",
            "text",
            "voice",
            "both",
        ):
            assert token in text
