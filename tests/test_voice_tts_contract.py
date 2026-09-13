from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_send_voice_constant_and_service_are_exposed() -> None:
    const = (COMP / "const.py").read_text()
    services = (COMP / "services.yaml").read_text()
    assert 'SERVICE_SEND_VOICE: Final = "send_voice"' in const
    assert "send_voice:" in services
    for marker in ("text:", "tts_engine:", "language:", "tts_options:"):
        assert marker in services


def test_send_voice_uses_home_assistant_tts_and_native_matrix_voice() -> None:
    source = (COMP / "v05_services.py").read_text()
    for marker in (
        "SERVICE_SEND_VOICE",
        "generate_media_source_id",
        "async_get_media_source_audio",
        'media_type="audio"',
        "voice=True",
        "async_upload",
        "async_send_prepared",
    ):
        assert marker in source


def test_manifest_declares_tts_as_after_dependency() -> None:
    manifest = (COMP / "manifest.json").read_text()
    assert '"tts"' in manifest
