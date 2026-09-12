from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "incoming.py"


def load():
    assert PATH.exists(), "incoming.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_incoming", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_relations_reads_reply_and_thread() -> None:
    mod = load()
    source = {
        "content": {
            "m.relates_to": {
                "rel_type": "m.thread",
                "event_id": "$thread",
                "m.in_reply_to": {"event_id": "$parent"},
            }
        }
    }
    assert mod.extract_relations(source) == ("$parent", "$thread")


def test_authorization_requires_both_user_and_room_when_configured() -> None:
    mod = load()
    policy = mod.IncomingPolicy(
        allowed_users={"@seriy:example"},
        allowed_rooms={"!home:example"},
    )
    assert policy.allows("@seriy:example", "!home:example") is True
    assert policy.allows("@other:example", "!home:example") is False
    assert policy.allows("@seriy:example", "!other:example") is False


def test_own_device_echo_is_rejected_but_same_user_other_device_is_allowed() -> None:
    mod = load()
    policy = mod.IncomingPolicy(
        allowed_users={"@seriy:example"},
        allowed_rooms={"!home:example"},
    )
    assert policy.should_process(
        sender="@seriy:example",
        room_id="!home:example",
        transaction_id="tx-from-this-device",
    ) is False
    assert policy.should_process(
        sender="@seriy:example",
        room_id="!home:example",
        transaction_id=None,
    ) is True


def test_safe_filename_strips_path_components() -> None:
    mod = load()
    assert mod.safe_filename("../../door clip.mp4") == "door clip.mp4"
    assert mod.safe_filename("") == "matrix-media.bin"
