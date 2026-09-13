from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_transcribe_voice_constant_and_service_are_exposed() -> None:
    const = (COMP / "const.py").read_text()
    services = (COMP / "services.yaml").read_text()
    assert 'SERVICE_TRANSCRIBE_VOICE: Final = "transcribe_voice"' in const
    assert "transcribe_voice:" in services
    for marker in (
        "path:",
        "stt_entity:",
        "language:",
        "audio_format:",
        "codec:",
        "sample_rate:",
        "channels:",
        "assist:",
        "conversation_agent:",
    ):
        assert marker in services


def test_transcribe_voice_uses_ha_stt_and_restricts_files_to_incoming_directory() -> None:
    source = (COMP / "v05_services.py").read_text()
    for marker in (
        "SERVICE_TRANSCRIBE_VOICE",
        "async_get_speech_to_text_entity",
        "SpeechMetadata",
        "check_metadata",
        "internal_async_process_audio_stream",
        "incoming",
        "is_relative_to",
        "SpeechResultState.SUCCESS",
    ):
        assert marker in source


def test_stt_normalizes_element_audio_for_pcm_only_providers() -> None:
    source = (COMP / "v05_services.py").read_text()
    assert "get_ffmpeg_manager" in source
    assert "pcm_s16le" in source
    assert "asyncio.create_subprocess_exec" in source


def test_assist_execution_is_explicit_opt_in() -> None:
    source = (COMP / "v05_services.py").read_text()
    assert 'vol.Optional("assist", default=False)' in source
    assert "async_converse" in source
    assert 'call.data.get("assist", False)' in source


def test_manifest_declares_voice_pipeline_after_dependencies() -> None:
    manifest = (COMP / "manifest.json").read_text()
    assert '"stt"' in manifest
    assert '"conversation"' in manifest
    assert '"ffmpeg"' in manifest
