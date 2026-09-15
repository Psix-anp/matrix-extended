from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
VALUE_HELPER = ROOT / "custom_components" / "matrix_extended" / "media_picker_value.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "matrix_extended_media_picker_value_v057", VALUE_HELPER
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_send_media_url_source_normalizes_to_existing_media_shape() -> None:
    mod = _load_module()
    item = mod.send_media_source_to_media_item(
        url="https://example.com/event.mp4",
        media_type="video",
        filename="event.mp4",
        caption="Garage",
    )
    assert item == {
        "url": "https://example.com/event.mp4",
        "type": "video",
        "filename": "event.mp4",
        "caption": "Garage",
    }


def test_send_media_entity_source_normalizes_to_existing_media_shape() -> None:
    mod = _load_module()
    item = mod.send_media_source_to_media_item(
        entity_id="image.cam2_car",
        media_type="auto",
    )
    assert item == {"entity_id": "image.cam2_car", "type": "auto"}


def test_send_media_media_picker_remains_backward_compatible() -> None:
    mod = _load_module()
    item = mod.send_media_source_to_media_item(
        media_picker={
            "media_content_id": "media-source://frigate/frigate/event/clips/cam1/id",
            "media_content_type": "video/mp4",
        },
        caption="Clip",
    )
    assert item == {
        "media_source": "media-source://frigate/frigate/event/clips/cam1/id",
        "type": "auto",
        "caption": "Clip",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {
            "url": "https://example.com/a.jpg",
            "entity_id": "image.camera",
        },
        {
            "url": "https://example.com/a.jpg",
            "media_picker": {"media_content_id": "media-source://image/image.camera"},
        },
    ],
)
def test_send_media_requires_exactly_one_source(kwargs) -> None:
    mod = _load_module()
    with pytest.raises(ValueError, match="exactly one"):
        mod.send_media_source_to_media_item(**kwargs)
