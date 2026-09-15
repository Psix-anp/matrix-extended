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


@pytest.mark.asyncio
async def test_media_source_internal_ha_url_is_authenticated_before_download() -> None:
    helpers = _load_media_test_helpers()
    mod, state = helpers.load_media()

    media_player = types.ModuleType("homeassistant.components.media_player")
    browse_media = types.ModuleType("homeassistant.components.media_player.browse_media")
    signed_calls: list[str] = []

    def async_process_play_media_url(hass, url: str) -> str:
        signed_calls.append(url)
        return f"{url}?authSig=test-signature"

    browse_media.async_process_play_media_url = async_process_play_media_url
    media_player.browse_media = browse_media
    sys.modules["homeassistant.components.media_player"] = media_player
    sys.modules["homeassistant.components.media_player.browse_media"] = browse_media

    frigate_url = (
        "http://192.168.0.103:8123/api/frigate/frigate/vod/"
        "cam1/start/1789448991/end/1789449012/index.m3u8"
    )
    state.playable = types.SimpleNamespace(
        path=None,
        url=frigate_url,
        mime_type="application/vnd.apple.mpegurl",
    )
    state.session = helpers.FakeSession(
        helpers.FakeResponse(
            chunks=(b"#EXTM3U\n",),
            headers={"Content-Type": "application/vnd.apple.mpegurl"},
        )
    )

    resolver = mod.MediaResolver(helpers.FakeHass())
    await resolver._async_from_media_source("media-source://frigate/vod/cam1")

    assert signed_calls == [frigate_url]
    assert state.session.calls[0][0] == f"{frigate_url}?authSig=test-signature"
