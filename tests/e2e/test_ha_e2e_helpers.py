from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "ha-e2e.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ha_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_find_matrix_entry_returns_matching_domain():
    module = _load_module()
    entries = [
        {"entry_id": "one", "domain": "sun", "state": "loaded"},
        {"entry_id": "mx", "domain": "matrix_extended", "state": "loaded"},
    ]
    assert module.find_matrix_entry(entries)["entry_id"] == "mx"


def test_find_encrypted_event_filters_room_and_sender():
    module = _load_module()
    sync = {
        "rooms": {
            "join": {
                "!room:matrix.test": {
                    "timeline": {
                        "events": [
                            {"type": "m.room.message", "sender": "@ha_bot:matrix.test"},
                            {"type": "m.room.encrypted", "sender": "@other:matrix.test"},
                            {
                                "type": "m.room.encrypted",
                                "sender": "@ha_bot:matrix.test",
                                "event_id": "$encrypted",
                            },
                        ]
                    }
                }
            }
        }
    }
    event = module.find_encrypted_event(sync, "!room:matrix.test", "@ha_bot:matrix.test")
    assert event["event_id"] == "$encrypted"
