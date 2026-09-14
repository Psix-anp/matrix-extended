from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_media_picker_value_module():
    path = COMP / "media_picker_value.py"
    spec = importlib.util.spec_from_file_location("matrix_extended_media_picker_value", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v052_manifest_version() -> None:
    manifest = json.loads((COMP / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.5.2"


def test_send_media_exposes_native_home_assistant_media_picker() -> None:
    services = (COMP / "services.yaml").read_text(encoding="utf-8")
    assert "send_media:" in services
    assert "media_picker:" in services
    assert "accept:" in services
    for media_type in ("image/*", "audio/*", "video/*"):
        assert media_type in services


def test_media_picker_output_is_normalized_for_existing_media_resolver() -> None:
    media_picker = load_media_picker_value_module()
    result = media_picker.media_picker_to_media_item(
        {
            "media_content_id": "media-source://media_source/local/photo.jpg",
            "media_content_type": "image/jpeg",
            "metadata": {"title": "Photo"},
        }
    )
    assert result == {
        "media_source": "media-source://media_source/local/photo.jpg",
        "type": "auto",
    }


def test_service_localizations_exist_in_english_and_russian() -> None:
    expected_services = {
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
    }
    for language in ("en", "ru"):
        data = json.loads((COMP / "translations" / f"{language}.json").read_text(encoding="utf-8"))
        assert expected_services <= set(data["services"])
        for service in expected_services:
            assert data["services"][service]["name"].strip()

    ru = json.loads((COMP / "translations" / "ru.json").read_text(encoding="utf-8"))
    assert ru["services"]["send"]["name"] == "Отправить сообщение Matrix"
    assert ru["services"]["send_media"]["fields"]["media_picker"]["name"] == "Медиа — выбрать"


def test_select_option_translation_keys_are_declared() -> None:
    services = (COMP / "services.yaml").read_text(encoding="utf-8")
    for key in ("message_type", "message_format", "audio_format", "audio_codec"):
        assert f"translation_key: {key}" in services

    ru = json.loads((COMP / "translations" / "ru.json").read_text(encoding="utf-8"))
    assert ru["selector"]["message_type"]["options"]["text"] == "Текст"
    assert ru["selector"]["message_format"]["options"]["markdown"] == "Markdown"
