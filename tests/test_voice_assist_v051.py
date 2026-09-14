from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_voice_assist_constants_and_event_exist() -> None:
    source = (COMP / "const.py").read_text()
    for marker in (
        'CONF_VOICE_ASSIST_ENABLED: Final = "voice_assist_enabled"',
        'CONF_VOICE_ASSIST_STT_ENTITY: Final = "voice_assist_stt_entity"',
        'CONF_VOICE_ASSIST_LANGUAGE: Final = "voice_assist_language"',
        'CONF_VOICE_ASSIST_CONVERSATION_AGENT: Final = "voice_assist_conversation_agent"',
        'CONF_VOICE_ASSIST_REPLY_MODE: Final = "voice_assist_reply_mode"',
        'CONF_VOICE_ASSIST_TTS_ENTITY: Final = "voice_assist_tts_entity"',
        'CONF_VOICE_ASSIST_ALLOWED_USERS: Final = "voice_assist_allowed_users"',
        'CONF_VOICE_ASSIST_ALLOWED_ROOMS: Final = "voice_assist_allowed_rooms"',
        'EVENT_VOICE_ASSIST: Final = "matrix_extended_voice_assist"',
    ):
        assert marker in source


def test_voice_assist_module_has_settings_and_coordinator() -> None:
    source = (COMP / "voice_assist.py").read_text()
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "VoiceAssistSettings" in names
    assert "VoiceAssistCoordinator" in names
    assert "async_process" in names
    assert "allows" in names


def test_voice_assist_is_fail_closed_to_native_voice_and_safe_local_file() -> None:
    source = (COMP / "voice_assist.py").read_text()
    for marker in (
        'if not self.enabled:',
        'if not bool(media_payload.get("voice")):',
        'local_path = media_payload.get("local_path")',
        'if not local_path or media_payload.get("download_error"):',
        'sender not in self.allowed_users',
        'room_id not in self.allowed_rooms',
        'async_process_voice_file(',
    ):
        assert marker in source


def test_voice_assist_forwards_downloaded_content_type_to_stt_pipeline() -> None:
    source = (COMP / "voice_assist.py").read_text()
    assert 'content_type=media_payload.get("content_type")' in source


def test_options_flow_exposes_voice_assist_disabled_by_default() -> None:
    source = (COMP / "config_flow.py").read_text()
    assert "CONF_VOICE_ASSIST_ENABLED" in source
    assert "default=value(CONF_VOICE_ASSIST_ENABLED, False)" in source
    for mode in ('"text"', '"voice"', '"both"'):
        assert mode in source
    for marker in (
        "CONF_VOICE_ASSIST_STT_ENTITY",
        "CONF_VOICE_ASSIST_LANGUAGE",
        "CONF_VOICE_ASSIST_CONVERSATION_AGENT",
        "CONF_VOICE_ASSIST_REPLY_MODE",
        "CONF_VOICE_ASSIST_TTS_ENTITY",
        "CONF_VOICE_ASSIST_ALLOWED_USERS",
        "CONF_VOICE_ASSIST_ALLOWED_ROOMS",
    ):
        assert marker in source


def test_receiver_schedules_voice_assist_after_media_event_without_blocking_sync() -> None:
    source = (COMP / "receiver.py").read_text()
    assert "VoiceAssistCoordinator" in source
    assert "voice_assist" in source
    assert "self._hass.async_create_task(" in source
    assert 'async_fire("matrix_extended_voice_assist"' not in source


def test_voice_assist_translation_keys_exist_in_both_languages() -> None:
    strings = json.loads((COMP / "strings.json").read_text())
    ru = json.loads((COMP / "translations" / "ru.json").read_text())
    for doc in (strings, ru):
        init = doc["options"]["step"]["init"]["data"]
        for key in (
            "voice_assist_enabled",
            "voice_assist_stt_entity",
            "voice_assist_language",
            "voice_assist_conversation_agent",
            "voice_assist_reply_mode",
            "voice_assist_tts_entity",
            "voice_assist_allowed_users",
            "voice_assist_allowed_rooms",
        ):
            assert key in init
