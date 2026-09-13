from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "matrix_extended" / "content.py"


def load_module():
    assert MODULE_PATH.exists(), "content.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_content", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_text_html_thread_content() -> None:
    mod = load_module()
    content = mod.build_text_content(
        "Door opened",
        formatted_body="<b>Door opened</b>",
        thread_id="$thread",
    )
    assert content == {
        "msgtype": "m.text",
        "body": "Door opened",
        "format": "org.matrix.custom.html",
        "formatted_body": "<b>Door opened</b>",
        "m.relates_to": {"event_id": "$thread", "rel_type": "m.thread"},
    }


def test_text_supports_notice_and_mentions() -> None:
    mod = load_module()
    content = mod.build_text_content(
        "Alarm",
        msgtype="notice",
        mentions=mod.build_mentions(
            [" @alice:example.org ", "@alice:example.org", "@bob:example.org"],
            room=True,
        ),
    )
    assert content["msgtype"] == "m.notice"
    assert content["m.mentions"] == {
        "user_ids": ["@alice:example.org", "@bob:example.org"],
        "room": True,
    }


def test_emote_is_supported_and_invalid_msgtype_rejected() -> None:
    mod = load_module()
    assert mod.build_text_content("waves", msgtype="emote")["msgtype"] == "m.emote"
    with pytest.raises(ValueError, match="msgtype"):
        mod.build_text_content("bad", msgtype="location")


def test_markdown_renderer_escapes_html_and_formats_safe_subset() -> None:
    mod = load_module()
    rendered = mod.render_markdown(
        "<script>x</script> **Bold** *italic* `a < b` [HA](https://home-assistant.io)\nnext"
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;x&lt;/script&gt;" in rendered
    assert "<strong>Bold</strong>" in rendered
    assert "<em>italic</em>" in rendered
    assert "<code>a &lt; b</code>" in rendered
    assert '<a href="https://home-assistant.io">HA</a>' in rendered
    assert "<br>next" in rendered


def test_markdown_renderer_does_not_create_unsafe_links() -> None:
    mod = load_module()
    rendered = mod.render_markdown("[bad](javascript:alert(1))")
    assert "javascript:" not in rendered
    assert "[bad]" in rendered


def test_build_mentions_omits_empty_metadata_and_rejects_empty_ids() -> None:
    mod = load_module()
    assert mod.build_mentions([], room=False) == {}
    with pytest.raises(ValueError, match="Matrix user ID"):
        mod.build_mentions(["   "])


def test_reply_and_edit_preserve_msgtype() -> None:
    mod = load_module()
    reply = mod.build_reply_content(
        "Acknowledged",
        reply_to="$original",
        msgtype="notice",
        mentions={"user_ids": ["@alice:example.org"]},
    )
    assert reply["msgtype"] == "m.notice"
    assert reply["m.mentions"] == {"user_ids": ["@alice:example.org"]}

    edit = mod.build_edit_content(
        "updated",
        event_id="$original",
        msgtype="emote",
    )
    assert edit["msgtype"] == "m.emote"
    assert edit["m.new_content"]["msgtype"] == "m.emote"


def test_image_caption_preserves_original_filename() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="image",
        mxc_uri="mxc://example/image",
        filename="front-door.jpg",
        content_type="image/jpeg",
        size=1234,
        caption="Person at the door",
        width=1920,
        height=1080,
    )
    assert content["msgtype"] == "m.image"
    assert content["body"] == "Person at the door"
    assert content["filename"] == "front-door.jpg"
    assert content["info"] == {
        "mimetype": "image/jpeg",
        "size": 1234,
        "w": 1920,
        "h": 1080,
    }


def test_video_thumbnail_and_duration() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="video",
        mxc_uri="mxc://example/video",
        filename="clip.mp4",
        content_type="video/mp4",
        size=5000,
        duration_ms=4200,
        width=1280,
        height=720,
        thumbnail_mxc_uri="mxc://example/thumb",
        thumbnail_info={"mimetype": "image/jpeg", "size": 321, "w": 320, "h": 180},
    )
    assert content["msgtype"] == "m.video"
    assert content["info"]["duration"] == 4200
    assert content["info"]["thumbnail_url"] == "mxc://example/thumb"
    assert content["info"]["thumbnail_info"]["w"] == 320


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("image/png", "image"),
        ("video/mp4", "video"),
        ("audio/ogg", "audio"),
        ("application/pdf", "file"),
        (None, "file"),
    ],
)
def test_infer_media_type(mime: str | None, expected: str) -> None:
    mod = load_module()
    assert mod.infer_media_type(mime) == expected


def test_validate_media_item_requires_exactly_one_source() -> None:
    mod = load_module()
    assert mod.validate_media_item_shape({"entity_id": "camera.door"})["entity_id"] == "camera.door"
    with pytest.raises(ValueError, match="exactly one source"):
        mod.validate_media_item_shape({"url": "https://a", "path": "/tmp/a.jpg"})
    with pytest.raises(ValueError, match="exactly one source"):
        mod.validate_media_item_shape({"caption": "nothing"})


def test_validate_media_size_rejects_oversize() -> None:
    mod = load_module()
    assert mod.validate_media_size(128, 128) == 128
    with pytest.raises(ValueError, match="too large"):
        mod.validate_media_size(129, 128)


def test_audio_rejects_thumbnail_metadata() -> None:
    mod = load_module()
    with pytest.raises(ValueError, match="thumbnail"):
        mod.build_media_content(
            media_type="audio",
            mxc_uri="mxc://example/audio",
            filename="alarm.ogg",
            content_type="audio/ogg",
            size=512,
            thumbnail_mxc_uri="mxc://example/thumb",
            thumbnail_info={"mimetype": "image/jpeg", "size": 10, "w": 4, "h": 4},
        )


def test_media_size_zero_is_valid_and_negative_is_rejected() -> None:
    mod = load_module()
    assert mod.validate_media_size(0, 128) == 0
    with pytest.raises(ValueError, match="negative"):
        mod.validate_media_size(-1, 128)


def test_media_content_size_zero_is_valid_and_negative_is_rejected() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="file",
        mxc_uri="mxc://example/empty",
        filename="empty.bin",
        content_type="application/octet-stream",
        size=0,
    )
    assert content["info"]["size"] == 0
    with pytest.raises(ValueError, match="negative"):
        mod.build_media_content(
            media_type="file",
            mxc_uri="mxc://example/bad",
            filename="bad.bin",
            content_type="application/octet-stream",
            size=-1,
        )


def test_media_without_caption_or_format_omits_optional_caption_fields() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="image",
        mxc_uri="mxc://example/image",
        filename="door.jpg",
        content_type="image/jpeg",
        size=10,
    )
    assert content["body"] == "door.jpg"
    assert "filename" not in content
    assert "format" not in content
    assert "formatted_body" not in content


def test_formatted_media_caption_sets_filename_and_format() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="image",
        mxc_uri="mxc://example/image",
        filename="door.jpg",
        content_type="image/jpeg",
        size=10,
        caption="Door",
        formatted_caption="<b>Door</b>",
    )
    assert content["filename"] == "door.jpg"
    assert content["format"] == "org.matrix.custom.html"
    assert content["formatted_body"] == "<b>Door</b>"


def test_duration_only_applies_to_video_or_audio_and_when_present() -> None:
    mod = load_module()
    image = mod.build_media_content(
        media_type="image",
        mxc_uri="mxc://example/image",
        filename="door.jpg",
        content_type="image/jpeg",
        size=10,
        duration_ms=1234,
    )
    assert "duration" not in image["info"]
    video = mod.build_media_content(
        media_type="video",
        mxc_uri="mxc://example/video",
        filename="clip.mp4",
        content_type="video/mp4",
        size=10,
    )
    assert "duration" not in video["info"]


def test_thumbnail_info_requires_an_actual_thumbnail() -> None:
    mod = load_module()
    content = mod.build_media_content(
        media_type="video",
        mxc_uri="mxc://example/video",
        filename="clip.mp4",
        content_type="video/mp4",
        size=10,
        thumbnail_info={"mimetype": "image/jpeg", "size": 1},
    )
    assert "thumbnail_info" not in content["info"]
    with_thumb = mod.build_media_content(
        media_type="video",
        mxc_uri="mxc://example/video",
        filename="clip.mp4",
        content_type="video/mp4",
        size=10,
        thumbnail_mxc_uri="mxc://example/thumb",
    )
    assert "thumbnail_info" not in with_thumb["info"]
