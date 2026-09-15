from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
MEDIA_BEHAVIOR = ROOT / "tests" / "test_media_behavior.py"


def _load_media_test_helpers():
    spec = importlib.util.spec_from_file_location(
        "matrix_extended_test_media_behavior_helpers", MEDIA_BEHAVIOR
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _install_play_media_url_signer() -> list[str]:
    media_player = types.ModuleType("homeassistant.components.media_player")
    browse_media = types.ModuleType("homeassistant.components.media_player.browse_media")
    signed_calls: list[str] = []

    def async_process_play_media_url(hass, url: str) -> str:
        signed_calls.append(url)
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}authSig=test-signature"

    browse_media.async_process_play_media_url = async_process_play_media_url
    media_player.browse_media = browse_media
    sys.modules["homeassistant.components.media_player"] = media_player
    sys.modules["homeassistant.components.media_player.browse_media"] = browse_media
    return signed_calls


@pytest.mark.asyncio
async def test_media_source_internal_ha_url_is_authenticated_before_download() -> None:
    helpers = _load_media_test_helpers()
    mod, state = helpers.load_media()
    signed_calls = _install_play_media_url_signer()

    protected_url = "http://192.168.0.103:8123/api/protected/photo.jpg"
    state.playable = types.SimpleNamespace(
        path=None,
        url=protected_url,
        mime_type="image/jpeg",
    )
    state.session = helpers.FakeSession(
        helpers.FakeResponse(
            chunks=(b"jpeg",),
            headers={"Content-Type": "image/jpeg"},
        )
    )

    resolver = mod.MediaResolver(helpers.FakeHass())
    await resolver._async_from_media_source("media-source://protected/photo")

    assert signed_calls == [protected_url]
    assert state.session.calls[0][0] == f"{protected_url}?authSig=test-signature"


@pytest.mark.asyncio
async def test_frigate_vod_media_source_uses_recording_mp4_proxy() -> None:
    helpers = _load_media_test_helpers()
    mod, state = helpers.load_media()
    signed_calls = _install_play_media_url_signer()

    frigate_hls_url = (
        "http://192.168.0.103:8123/api/frigate/frigate/vod/"
        "cam1/start/1789448991/end/1789449012/index.m3u8"
    )
    expected_mp4_url = (
        "http://192.168.0.103:8123/api/frigate/frigate/recording/"
        "cam1/start/1789448991/end/1789449012"
    )
    state.playable = types.SimpleNamespace(
        path=None,
        url=frigate_hls_url,
        mime_type="application/x-mpegURL",
    )
    state.session = helpers.FakeSession(
        helpers.FakeResponse(
            chunks=(b"mp4-data",),
            headers={"Content-Type": "video/mp4"},
        )
    )

    resolver = mod.MediaResolver(helpers.FakeHass())
    resolved = await resolver._async_from_media_source(
        "media-source://frigate/frigate/event/clips/cam1/event-id"
    )

    assert signed_calls == [expected_mp4_url]
    assert state.session.calls[0][0] == f"{expected_mp4_url}?authSig=test-signature"
    assert resolved.content_type == "video/mp4"
    assert resolved.media_type == "video"
    assert resolved.filename.endswith(".mp4")
