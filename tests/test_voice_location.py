from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "matrix_extended" / "content.py"


def load_module():
    spec = importlib.util.spec_from_file_location("matrix_extended_content_voice_location", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_voice_audio_adds_native_matrix_voice_metadata() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="audio",
        mxc_uri="mxc://example/voice",
        filename="voice.ogg",
        content_type="audio/ogg",
        size=1024,
        duration_ms=4200,
        voice=True,
    )
    assert content["msgtype"] == "m.audio"
    assert content["org.matrix.msc3245.voice"] == {}
    assert content["org.matrix.msc1767.audio"] == {"duration": 4200}


def test_voice_flag_rejects_non_audio_media() -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="voice"):
        mod.build_media_content(
            media_type="file",
            mxc_uri="mxc://example/file",
            filename="voice.ogg",
            content_type="audio/ogg",
            size=1024,
            voice=True,
        )


def test_location_content_uses_stable_m_location_and_geo_uri() -> None:
    mod = load_module()
    content = mod.build_location_content(
        latitude=51.5008,
        longitude=-0.1247,
        description="Big Ben",
        thread_id="$thread",
    )
    assert content == {
        "msgtype": "m.location",
        "body": "Big Ben",
        "geo_uri": "geo:51.5008,-0.1247",
        "m.relates_to": {"event_id": "$thread", "rel_type": "m.thread"},
    }


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181)],
)
def test_location_content_validates_coordinate_ranges(latitude: float, longitude: float) -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="latitude|longitude"):
        mod.build_location_content(
            latitude=latitude,
            longitude=longitude,
            description="invalid",
        )
