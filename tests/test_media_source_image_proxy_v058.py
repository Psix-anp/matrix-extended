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
        "matrix_extended_test_media_behavior_helpers_v058", MEDIA_BEHAVIOR
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_resolved_image_proxy_stream_uses_native_image_entity_frame() -> None:
    helpers = _load_media_test_helpers()
    mod, state = helpers.load_media()
    state.playable = types.SimpleNamespace(
        path=None,
        url=(
            "http://192.168.0.103:8123/api/image_proxy_stream/"
            "image.cam2_motorcycle?authSig=test-signature"
        ),
        mime_type="image/jpeg",
    )
    state.session = helpers.FakeSession(
        helpers.FakeResponse(error=RuntimeError("stream endpoint must not be downloaded"))
    )

    resolver = mod.MediaResolver(helpers.FakeHass())
    resolved = await resolver._async_from_media_source(
        "media-source://provider/noncanonical-image-selection"
    )

    assert resolved.media_type == "image"
    assert resolved.filename.startswith("cam2_motorcycle")
    assert resolved.data == state.image_result.content
    assert state.session.calls == []


def test_image_proxy_stream_entity_parser_handles_signed_absolute_and_relative_urls() -> None:
    helpers = _load_media_test_helpers()
    mod, _ = helpers.load_media()

    assert (
        mod._image_entity_from_proxy_stream_url(
            "http://ha.local/api/image_proxy_stream/image.cam2_car?authSig=abc"
        )
        == "image.cam2_car"
    )
    assert (
        mod._image_entity_from_proxy_stream_url(
            "/api/image_proxy_stream/image.cam2_motorcycle?authSig=abc"
        )
        == "image.cam2_motorcycle"
    )
    assert mod._image_entity_from_proxy_stream_url("/api/image_proxy/image.cam2_car") is None
    assert mod._image_entity_from_proxy_stream_url("/api/image_proxy_stream/camera.front") is None
