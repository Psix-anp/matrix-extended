from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"
VOICE = COMP / "voice_pipeline.py"


def _source() -> str:
    return VOICE.read_text()


def test_reusable_voice_pipeline_contract_exists() -> None:
    source = _source()
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assert "VoicePipelineResult" in names
    assert "async_process_voice_file" in names
    assert "async_transcribe_voice" in names


def test_voice_pipeline_result_has_stable_response_fields() -> None:
    source = _source()
    for marker in (
        "text: str",
        "stt_entity: str",
        "language: str",
        "normalized: bool",
        "assist_executed: bool",
        "assist: dict[str, Any] | None",
    ):
        assert marker in source


def test_service_adapter_delegates_to_reusable_core() -> None:
    source = _source()
    assert "result = await async_process_voice_file(" in source
    assert 'path=call.data["path"]' in source
    assert 'assist=bool(call.data.get("assist", False))' in source
    assert "return result.as_response()" in source


def test_reusable_core_keeps_path_security_and_stt_fallback() -> None:
    source = _source()
    for marker in (
        "_resolve_incoming_voice_path",
        "is_relative_to",
        "provider.check_metadata",
        "_pcm_metadata_for_provider",
        "_transcode_voice_to_pcm_wav",
        "internal_async_process_audio_stream",
        "SpeechResultState.SUCCESS",
    ):
        assert marker in source


def test_native_wav_content_type_uses_actual_pcm_header_metadata() -> None:
    source = _source()
    for marker in (
        "content_type: str | None = None",
        "_WAV_CONTENT_TYPES",
        "_wav_metadata",
        "wave.open",
        "media_type in _WAV_CONTENT_TYPES",
    ):
        assert marker in source


def test_assist_remains_explicit_and_conversation_context_is_forwarded() -> None:
    source = _source()
    assert "if assist:" in source
    assert "conversation.async_converse(" in source
    assert "conversation_id=conversation_id" in source
    assert "agent_id=conversation_agent" in source
