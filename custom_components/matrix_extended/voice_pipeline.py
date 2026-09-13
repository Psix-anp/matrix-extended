"""Home Assistant STT/Assist pipeline for downloaded Matrix voice messages."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import MatrixAccount
from .const import ATTR_ACCOUNT, DOMAIN

TRANSCRIBE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Required("path"): cv.string,
        vol.Optional("stt_entity"): cv.entity_id,
        vol.Optional("language"): cv.string,
        vol.Optional("audio_format", default="ogg"): vol.In(["ogg", "wav"]),
        vol.Optional("codec", default="opus"): vol.In(["opus", "pcm"]),
        vol.Optional("bit_rate", default=16): vol.In([8, 16, 24, 32]),
        vol.Optional("sample_rate", default=48000): vol.In([8000, 11000, 16000, 18900, 22000, 32000, 37800, 44100, 48000]),
        vol.Optional("channels", default=1): vol.In([1, 2]),
        vol.Optional("assist", default=False): cv.boolean,
        vol.Optional("conversation_agent"): cv.entity_id,
        vol.Optional("conversation_id"): cv.string,
    }
)


def _select_account(hass: HomeAssistant, account_id: str | None) -> MatrixAccount:
    accounts: dict[str, MatrixAccount] = hass.data.get(DOMAIN, {})
    if account_id:
        account = accounts.get(account_id)
        if account is None:
            raise HomeAssistantError(f"Unknown Matrix Extended account: {account_id}")
        return account
    if len(accounts) == 1:
        return next(iter(accounts.values()))
    if not accounts:
        raise HomeAssistantError("No Matrix Extended accounts are loaded")
    raise HomeAssistantError("Multiple Matrix Extended accounts are loaded; set 'account' to a config entry ID")


def _resolve_incoming_voice_path(hass: HomeAssistant, account: MatrixAccount, value: str) -> Path:
    """Resolve only regular files inside this account's incoming Matrix directory."""
    if not account.entry_id:
        raise HomeAssistantError("Matrix account has no config entry ID")
    root = Path(hass.config.path(DOMAIN, "incoming", account.entry_id)).resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise HomeAssistantError("Voice path must not be a symlink")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise HomeAssistantError("Voice path must be inside Matrix incoming media directory")
    if not resolved.is_file():
        raise HomeAssistantError("Voice file does not exist")
    return resolved


def _stt_language(provider: Any, requested: str) -> str:
    supported = [str(item) for item in provider.supported_languages]
    if requested in supported:
        return requested
    base = requested.split("-", 1)[0].lower()
    matches = [item for item in supported if item.split("-", 1)[0].lower() == base]
    if len(matches) == 1:
        return matches[0]
    raise HomeAssistantError(f"STT provider does not support language {requested}; supported={supported}")


async def _byte_stream(data: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(data), 4096):
        yield data[start : start + 4096]


async def _transcode_voice_to_pcm_wav(hass: HomeAssistant, path: Path, *, sample_rate: int, channels: int) -> bytes:
    """Normalize Element OGG/Opus for PCM-only STT providers via HA ffmpeg."""
    from homeassistant.components.ffmpeg import get_ffmpeg_manager  # noqa: PLC0415

    binary = get_ffmpeg_manager(hass).binary
    process = await asyncio.create_subprocess_exec(
        binary, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-f", "wav", "-acodec", "pcm_s16le", "-ar", str(sample_rate),
        "-ac", str(channels), "pipe:1",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0 or not stdout:
        detail = stderr.decode(errors="replace").strip()[-500:]
        raise HomeAssistantError(f"Unable to normalize voice audio with ffmpeg: {detail}")
    return stdout


def _pcm_metadata_for_provider(stt: Any, provider: Any, language: str) -> Any | None:
    if (
        stt.AudioFormats.WAV not in provider.supported_formats
        or stt.AudioCodecs.PCM not in provider.supported_codecs
        or stt.AudioBitRates.BITRATE_16 not in provider.supported_bit_rates
    ):
        return None
    if not provider.supported_sample_rates or not provider.supported_channels:
        return None
    sample_rate = stt.AudioSampleRates.SAMPLERATE_16000 if stt.AudioSampleRates.SAMPLERATE_16000 in provider.supported_sample_rates else provider.supported_sample_rates[0]
    channel = stt.AudioChannels.CHANNEL_MONO if stt.AudioChannels.CHANNEL_MONO in provider.supported_channels else provider.supported_channels[0]
    return stt.SpeechMetadata(
        language=language,
        format=stt.AudioFormats.WAV,
        codec=stt.AudioCodecs.PCM,
        bit_rate=stt.AudioBitRates.BITRATE_16,
        sample_rate=sample_rate,
        channel=channel,
    )


async def async_transcribe_voice(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    """Transcribe a downloaded Matrix voice file and optionally execute Assist."""
    from homeassistant.components import stt  # noqa: PLC0415

    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    path = await hass.async_add_executor_job(_resolve_incoming_voice_path, hass, account, call.data["path"])
    entity_id = call.data.get("stt_entity") or stt.async_default_engine(hass)
    if not entity_id:
        raise HomeAssistantError("No Home Assistant STT entity is available")
    provider = stt.async_get_speech_to_text_entity(hass, str(entity_id))
    if provider is None:
        raise HomeAssistantError(f"STT entity not found: {entity_id}; select a modern stt.* entity")
    language = _stt_language(provider, str(call.data.get("language") or hass.config.language or "en"))
    metadata = stt.SpeechMetadata(
        language=language,
        format=stt.AudioFormats(call.data["audio_format"]),
        codec=stt.AudioCodecs(call.data["codec"]),
        bit_rate=stt.AudioBitRates(int(call.data["bit_rate"])),
        sample_rate=stt.AudioSampleRates(int(call.data["sample_rate"])),
        channel=stt.AudioChannels(int(call.data["channels"])),
    )
    if provider.check_metadata(metadata):
        audio = await hass.async_add_executor_job(path.read_bytes)
        normalized = False
    else:
        normalized_metadata = _pcm_metadata_for_provider(stt, provider, language)
        if normalized_metadata is None or not provider.check_metadata(normalized_metadata):
            raise HomeAssistantError("STT provider does not accept supplied audio and has no WAV/PCM fallback")
        metadata = normalized_metadata
        audio = await _transcode_voice_to_pcm_wav(
            hass, path, sample_rate=int(metadata.sample_rate.value), channels=int(metadata.channel.value)
        )
        normalized = True
    result = await provider.internal_async_process_audio_stream(metadata, _byte_stream(audio))
    if result.result != stt.SpeechResultState.SUCCESS or not result.text:
        raise HomeAssistantError("Home Assistant STT did not return a transcript")
    transcript = str(result.text).strip()
    response: dict[str, Any] = {
        "text": transcript,
        "stt_entity": str(entity_id),
        "language": language,
        "normalized": normalized,
        "assist_executed": False,
    }
    if call.data.get("assist", False):
        from homeassistant.components import conversation  # noqa: PLC0415

        assist_result = await conversation.async_converse(
            hass=hass,
            text=transcript,
            conversation_id=call.data.get("conversation_id"),
            context=Context(),
            language=language,
            agent_id=call.data.get("conversation_agent"),
        )
        response["assist_executed"] = True
        response["assist"] = assist_result.as_dict()
    return response
