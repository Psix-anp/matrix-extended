from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PATH = ROOT / "custom_components" / "matrix_extended" / "delivery.py"


def load():
    assert PATH.exists(), "delivery.py implementation is absent"
    spec = importlib.util.spec_from_file_location("matrix_extended_delivery", PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_delivery_event_record_for_text_media_and_location() -> None:
    mod = load()
    assert mod.delivery_event_record(
        room_id="!room:example",
        event_id="$text",
        kind="text",
    ) == {
        "room_id": "!room:example",
        "event_id": "$text",
        "kind": "text",
    }
    assert mod.delivery_event_record(
        room_id="!room:example",
        event_id="$media",
        kind="media",
        media_index=2,
    ) == {
        "room_id": "!room:example",
        "event_id": "$media",
        "kind": "media",
        "media_index": 2,
    }
    assert mod.delivery_event_record(
        room_id="!room:example",
        event_id="$location",
        kind="location",
    ) == {
        "room_id": "!room:example",
        "event_id": "$location",
        "kind": "location",
    }


def test_delivery_event_record_rejects_bad_shape() -> None:
    mod = load()
    with pytest.raises(ValueError, match="kind"):
        mod.delivery_event_record(room_id="!r:x", event_id="$e", kind="file")
    with pytest.raises(ValueError, match="media_index"):
        mod.delivery_event_record(room_id="!r:x", event_id="$e", kind="text", media_index=0)
    with pytest.raises(ValueError, match="media_index"):
        mod.delivery_event_record(room_id="!r:x", event_id="$e", kind="location", media_index=0)
    with pytest.raises(ValueError, match="media_index"):
        mod.delivery_event_record(room_id="!r:x", event_id="$e", kind="media", media_index=-1)


def test_delivery_lifecycle_payload_is_stable_and_json_safe() -> None:
    mod = load()
    events = [
        mod.delivery_event_record(room_id="!room:example", event_id="$e", kind="text")
    ]
    assert mod.delivery_lifecycle_payload(
        account_id="entry",
        delivery_id="abc123",
        status="sent",
        events=events,
    ) == {
        "account_id": "entry",
        "delivery_id": "abc123",
        "status": "sent",
        "events": events,
        "error": None,
    }


def test_delivery_lifecycle_supports_all_states_and_rejects_unknown() -> None:
    mod = load()
    for status in ("sent", "queued", "failed", "dropped"):
        payload = mod.delivery_lifecycle_payload(
            account_id="entry",
            delivery_id="id",
            status=status,
            error="boom" if status in {"failed", "dropped"} else None,
        )
        assert payload["status"] == status
    with pytest.raises(ValueError, match="status"):
        mod.delivery_lifecycle_payload(
            account_id="entry",
            delivery_id="id",
            status="retrying",
        )
