from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
CONTENT = ROOT / "custom_components" / "matrix_extended" / "content.py"


def load():
    spec = importlib.util.spec_from_file_location("matrix_extended_v03_content", CONTENT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reply_content_targets_original_event() -> None:
    mod = load()
    content = mod.build_reply_content(
        "Yes",
        reply_to="$original",
        formatted_body="<b>Yes</b>",
    )
    assert content["msgtype"] == "m.text"
    assert content["body"] == "Yes"
    assert content["formatted_body"] == "<b>Yes</b>"
    assert content["m.relates_to"] == {
        "m.in_reply_to": {"event_id": "$original"}
    }


def test_reply_can_also_be_part_of_thread() -> None:
    mod = load()
    content = mod.build_reply_content(
        "Done",
        reply_to="$replyto",
        thread_id="$thread",
    )
    assert content["m.relates_to"] == {
        "event_id": "$thread",
        "rel_type": "m.thread",
        "m.in_reply_to": {"event_id": "$replyto"},
    }


def test_edit_content_has_replacement_and_new_content() -> None:
    mod = load()
    content = mod.build_edit_content(
        "Download 47%",
        event_id="$old",
        formatted_body="<b>Download 47%</b>",
    )
    assert content["msgtype"] == "m.text"
    assert content["body"] == "* Download 47%"
    assert content["m.relates_to"] == {
        "rel_type": "m.replace",
        "event_id": "$old",
    }
    assert content["m.new_content"] == {
        "msgtype": "m.text",
        "body": "Download 47%",
        "format": "org.matrix.custom.html",
        "formatted_body": "<b>Download 47%</b>",
    }


def test_reaction_content_is_annotation() -> None:
    mod = load()
    assert mod.build_reaction_content("$event", "📷") == {
        "m.relates_to": {
            "rel_type": "m.annotation",
            "event_id": "$event",
            "key": "📷",
        }
    }
