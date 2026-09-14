#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")


def request_json(
    method: str,
    path: str,
    token: str,
    body: dict | None = None,
):
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(HA_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            return json.loads(response.read() or b"[]")
    except HTTPError as err:
        payload = err.read().decode(errors="replace")[:1200]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {payload}") from err


def load_env() -> tuple[dict, dict]:
    ha_env = json.loads(Path(".ci/ha-env.json").read_text())
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    return ha_env, matrix_env


def verify_send_media() -> None:
    ha_env, matrix_env = load_env()
    request_json(
        "POST",
        "/api/services/matrix_extended/send_media",
        ha_env["access_token"],
        {
            "target": [matrix_env["room_id"]],
            "media_picker": {
                "media_content_id": "media-source://media_source/local/matrix-e2e-voice.wav",
                "media_content_type": "audio/wav",
            },
            "caption": "Matrix Extended graphical media picker E2E",
        },
    )
    print("matrix_extended.send_media executed successfully in real Home Assistant")


def verify_last_receive() -> None:
    ha_env, matrix_env = load_env()
    states = request_json("GET", "/api/states", ha_env["access_token"])
    expected_reacts_to = ha_env["matrix_event_id"]
    matches = []
    for state in states:
        entity_id = str(state.get("entity_id", ""))
        attributes = state.get("attributes") or {}
        if not entity_id.startswith("sensor."):
            continue
        if state.get("state") != "reaction":
            continue
        if attributes.get("room_id") != matrix_env["room_id"]:
            continue
        if attributes.get("sender") != matrix_env["user_user_id"]:
            continue
        if attributes.get("reaction") != "✅":
            continue
        if attributes.get("reacts_to") != expected_reacts_to:
            continue
        if not attributes.get("received_at"):
            continue
        matches.append(state)

    if len(matches) != 1:
        summary = [
            {
                "entity_id": state.get("entity_id"),
                "state": state.get("state"),
                "attributes": state.get("attributes"),
            }
            for state in states
            if str(state.get("entity_id", "")).startswith("sensor.")
            and (state.get("attributes") or {}).get("room_id") == matrix_env["room_id"]
        ]
        raise RuntimeError(
            "rich last incoming event sensor was not updated by the Matrix reaction; "
            f"candidates={summary}"
        )

    state = matches[0]
    print(
        "rich last incoming event sensor verified: "
        f"{state['entity_id']} state={state['state']} sender={matrix_env['user_user_id']}"
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"send-media", "last-receive"}:
        print("usage: verify-runtime.py {send-media|last-receive}", file=sys.stderr)
        return 2
    if sys.argv[1] == "send-media":
        verify_send_media()
    else:
        verify_last_receive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
