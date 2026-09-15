from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
MEDIA_BEHAVIOR = ROOT / "tests" / "test_media_behavior.py"


def _load_media_test_helpers():
    spec = importlib.util.spec_from_file_location(
        "matrix_extended_test_media_behavior_helpers_v057", MEDIA_BEHAVIOR
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.asyncio
async def test_image_media_source_fetches_single_image_entity_frame() -> None:
    helpers = _load_media_test_helpers()
    mod, state = helpers.load_media()
    state.playable = type(
        "Playable",
        (),
        {
            "path": None,
            "url": "/api/image_proxy_stream/image.cam2_car",
            "mime_type": "image/jpeg",
        },
    )()

    resolver = mod.MediaResolver(helpers.FakeHass())
    resolved = await resolver._async_from_media_source(
        "media-source://image/image.cam2_car"
    )

    assert resolved.data == state.image_result.content
    assert resolved.content_type == state.image_result.content_type
    assert resolved.media_type == "image"
    assert resolved.filename == "cam2_car.png"
    assert state.session.calls == []
