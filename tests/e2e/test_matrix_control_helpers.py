from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "matrix-control-e2e.py"


def load_helpers():
    assert SCRIPT.is_file(), "matrix-control-e2e.py is not implemented yet"
    spec = importlib.util.spec_from_file_location("matrix_control_e2e_helpers_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_find_panel_root_requires_matching_panel_metadata_and_sender() -> None:
    mod = load_helpers()
    events = [
        {
            "event_id": "$wrong",
            "type": "m.room.message",
            "sender": "@bot:matrix.test",
            "content": {
                "msgtype": "m.text",
                "body": "Wrong panel",
                "io.psix.matrix_extended.panel": {"schema": 1, "panel_id": "other"},
            },
        },
        {
            "event_id": "$root",
            "type": "m.room.message",
            "sender": "@bot:matrix.test",
            "content": {
                "msgtype": "m.text",
                "body": "Matrix control panel",
                "io.psix.matrix_extended.panel": {"schema": 1, "panel_id": "e2e"},
            },
        },
    ]

    event = mod.find_panel_root(events, panel_id="e2e", sender="@bot:matrix.test")

    assert event["event_id"] == "$root"


def test_is_panel_edit_accepts_only_m_replace_for_original_root() -> None:
    mod = load_helpers()
    good = {
        "event_id": "$edit",
        "type": "m.room.message",
        "content": {
            "msgtype": "m.text",
            "body": "* updated",
            "m.relates_to": {"rel_type": "m.replace", "event_id": "$root"},
            "m.new_content": {"msgtype": "m.text", "body": "updated"},
        },
    }
    wrong_root = {
        **good,
        "content": {
            **good["content"],
            "m.relates_to": {"rel_type": "m.replace", "event_id": "$different"},
        },
    }

    assert mod.is_panel_edit(good, "$root") is True
    assert mod.is_panel_edit(wrong_root, "$root") is False


@pytest.mark.parametrize("target", ["$root", "$other-root"])
def test_panel_root_helpers_reject_edits_with_panel_metadata(target: str) -> None:
    mod = load_helpers()
    spec = importlib.util.spec_from_file_location(
        "matrix_control_content_test",
        ROOT / "custom_components" / "matrix_extended" / "content.py",
    )
    assert spec and spec.loader
    content = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(content)
    marker = {mod.PANEL_METADATA_KEY: {"schema": 1, "panel_id": mod.PANEL_ID}}
    edit = {
        "event_id": "$edit",
        "type": "m.room.message",
        "sender": "@bot:matrix.test",
        "content": content.build_edit_content(
            "Light: on", event_id=target, extra_content=marker
        ),
    }
    root = {
        "event_id": "$root",
        "type": "m.room.message",
        "sender": "@bot:matrix.test",
        "content": content.build_text_content("Light: off", extra_content=marker),
    }

    assert mod.is_panel_edit(edit, target) is True
    assert mod._is_panel_root(edit, sender="@bot:matrix.test") is False
    assert mod._is_panel_root(root, sender="@bot:matrix.test") is True
    assert mod.find_panel_root(
        [edit, root], panel_id=mod.PANEL_ID, sender="@bot:matrix.test"
    )["event_id"] == "$root"
    with pytest.raises(LookupError):
        mod.find_panel_root(
            [edit], panel_id=mod.PANEL_ID, sender="@bot:matrix.test"
        )


def test_find_confirmation_reply_is_bound_to_root_and_action_label() -> None:
    mod = load_helpers()
    events = [
        {
            "event_id": "$unrelated",
            "type": "m.room.message",
            "sender": "@bot:matrix.test",
            "content": {
                "msgtype": "m.text",
                "body": "⚠️ Confirm: Open garage",
                "m.relates_to": {"m.in_reply_to": {"event_id": "$other"}},
            },
        },
        {
            "event_id": "$confirm",
            "type": "m.room.message",
            "sender": "@bot:matrix.test",
            "content": {
                "msgtype": "m.text",
                "body": "⚠️ Confirm: Dangerous target",
                "m.relates_to": {"m.in_reply_to": {"event_id": "$root"}},
            },
        },
    ]

    event = mod.find_confirmation_reply(
        events,
        root_event_id="$root",
        action_label="Dangerous target",
        sender="@bot:matrix.test",
    )

    assert event["event_id"] == "$confirm"


def test_real_ha_fixture_exposes_control_targets() -> None:
    source = (ROOT / "ci" / "scripts" / "prepare-ha.sh").read_text(encoding="utf-8")
    assert "matrix_control_light:" in source
    assert "matrix_control_dangerous:" in source


def test_real_stack_workflow_exercises_full_control_lifecycle() -> None:
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    for command in (
        "matrix-control-e2e.py verify",
        "matrix-control-e2e.py outage-flips",
        "matrix-control-e2e.py verify-recovery",
        "matrix-control-e2e.py verify-restart-repair",
    ):
        assert command in workflow, command
