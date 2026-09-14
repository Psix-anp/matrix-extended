#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")


def request_json(path: str, token: str):
    req = Request(
        HA_URL + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read() or b"[]")


def main() -> int:
    ha_env = json.loads(Path(".ci/ha-env.json").read_text())
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    states = request_json("/api/states", ha_env["access_token"])
    notify_states = [state for state in states if str(state.get("entity_id", "")).startswith("notify.")]
    if not notify_states:
        raise RuntimeError("Matrix Extended registered no notify entities")

    room_id = matrix_env["room_id"]
    room_entities = [
        state
        for state in notify_states
        if state.get("attributes", {}).get("room_id") == room_id
    ]
    if not room_entities:
        ids = [state.get("entity_id") for state in notify_states]
        raise RuntimeError(
            f"Matrix Extended registered no room-specific notify entity for {room_id}; notify entities={ids}"
        )

    print(
        "Matrix notify entities verified: "
        + ", ".join(str(state.get("entity_id")) for state in notify_states)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
