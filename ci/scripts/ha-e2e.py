#!/usr/bin/env python3
"""Drive a real Home Assistant container against the disposable Synapse server."""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
MATRIX_HOST_URL = os.environ.get("MATRIX_HOST_URL", "http://127.0.0.1:8008").rstrip("/")
MATRIX_HA_URL = os.environ.get("MATRIX_HA_URL", "http://synapse:8008").rstrip("/")
CLIENT_ID = os.environ.get("HA_CLIENT_ID", "http://127.0.0.1:8123/")
LOCATION_TEXT = "Matrix Extended E2E Location"
VOICE_TEXT = "Matrix Extended E2E Voice"
VOICE_PATH = "/config/matrix-e2e-media/matrix-e2e-voice.wav"


def _request_json(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: Any | None = None,
    form_body: dict[str, str] | None = None,
    timeout: float = 20,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        body = err.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {body}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"connection error for {method} {path}: {type(err).__name__}") from err
    return json.loads(raw or b"{}")


def find_matrix_entry(entries: Any) -> dict[str, Any]:
    """Return the Matrix Extended entry from an HA config-entry response."""
    if isinstance(entries, dict):
        entries = entries.get("result", entries.get("entries", []))
    for entry in entries:
        if entry.get("domain") == "matrix_extended":
            return entry
    raise LookupError("Matrix Extended config entry not found")


def _room_timeline(sync: dict[str, Any], room_id: str) -> list[dict[str, Any]]:
    return (
        sync.get("rooms", {})
        .get("join", {})
        .get(room_id, {})
        .get("timeline", {})
        .get("events", [])
    )


def find_encrypted_event(sync: dict[str, Any], room_id: str, sender: str) -> dict[str, Any]:
    """Find an encrypted room event from the expected sender."""
    for event in _room_timeline(sync, room_id):
        if event.get("type") == "m.room.encrypted" and event.get("sender") == sender:
            return event
    raise LookupError(f"no encrypted event from {sender} in {room_id}")


def _encrypted_event_count(sync: dict[str, Any], room_id: str, sender: str) -> int:
    return sum(
        1
        for event in _room_timeline(sync, room_id)
        if event.get("type") == "m.room.encrypted" and event.get("sender") == sender
    )


def _wait_for_encrypted_events(
    token: str,
    *,
    since: str,
    room_id: str,
    sender: str,
    expected_count: int,
    timeout: float = 20,
) -> int:
    """Accumulate encrypted events across incremental sync batches."""
    deadline = time.monotonic() + timeout
    total = 0
    while time.monotonic() < deadline:
        sync = _matrix_sync(token, since=since, timeout_ms=3000)
        since = sync["next_batch"]
        total += _encrypted_event_count(sync, room_id, sender)
        if total >= expected_count:
            return total
    raise TimeoutError(
        f"expected {expected_count} encrypted events from {sender} in {room_id}; got {total}"
    )


def _wait_entry_loaded(token: str, *, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state = "missing"
    while time.monotonic() < deadline:
        entries = _request_json(
            HA_URL,
            "GET",
            "/api/config/config_entries/entry",
            token=token,
        )
        try:
            entry = find_matrix_entry(entries)
        except LookupError:
            time.sleep(0.5)
            continue
        last_state = str(entry.get("state"))
        if last_state == "loaded":
            return entry
        time.sleep(0.5)
    raise TimeoutError(f"Matrix Extended entry did not load; last_state={last_state}")


def _create_ha_admin() -> str:
    password = secrets.token_urlsafe(24)
    onboarding = _request_json(
        HA_URL,
        "POST",
        "/api/onboarding/users",
        json_body={
            "name": "Matrix Extended E2E",
            "username": "matrix-e2e-admin",
            "password": password,
            "client_id": CLIENT_ID,
            "language": "en",
        },
    )
    token = _request_json(
        HA_URL,
        "POST",
        "/auth/token",
        form_body={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": onboarding["auth_code"],
        },
    )
    return token["access_token"]


def _create_matrix_entry(token: str, matrix_env: dict[str, Any], bot_password: str) -> dict[str, Any]:
    flow = _request_json(
        HA_URL,
        "POST",
        "/api/config/config_entries/flow",
        token=token,
        json_body={"handler": "matrix_extended"},
    )
    if flow.get("type") != "form":
        raise RuntimeError(f"unexpected config flow start result: {flow.get('type')}")
    result = _request_json(
        HA_URL,
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        token=token,
        json_body={
            "homeserver": MATRIX_HA_URL,
            "user_id": matrix_env["bot_user_id"],
            "password": bot_password,
            "default_room": matrix_env["room_id"],
            "verify_ssl": False,
            "require_e2ee": True,
            "incoming_enabled": True,
            "allowed_users": [matrix_env["user_user_id"]],
            "allowed_rooms": [matrix_env["room_id"]],
            "download_incoming_media": True,
        },
        timeout=60,
    )
    if result.get("type") != "create_entry":
        raise RuntimeError(f"Matrix config flow failed: type={result.get('type')} errors={result.get('errors')}")
    return result["result"]


def _matrix_sync(token: str, *, since: str | None = None, timeout_ms: int = 0) -> dict[str, Any]:
    query = {"timeout": str(timeout_ms)}
    if since:
        query["since"] = since
    return _request_json(
        MATRIX_HOST_URL,
        "GET",
        "/_matrix/client/v3/sync?" + urlencode(query),
        token=token,
        timeout=max(20, timeout_ms / 1000 + 10),
    )


def _matrix_react(matrix_env: dict[str, Any], event_id: str, reaction: str) -> str:
    room_id = quote(matrix_env["room_id"], safe="")
    txn_id = secrets.token_hex(8)
    result = _request_json(
        MATRIX_HOST_URL,
        "PUT",
        f"/_matrix/client/v3/rooms/{room_id}/send/m.reaction/{txn_id}",
        token=matrix_env["user_access_token"],
        json_body={
            "m.relates_to": {
                "rel_type": "m.annotation",
                "event_id": event_id,
                "key": reaction,
            }
        },
        timeout=30,
    )
    reaction_event_id = result.get("event_id")
    if not reaction_event_id:
        raise RuntimeError("Matrix reaction response has no event_id")
    return str(reaction_event_id)


def _matrix_redact(matrix_env: dict[str, Any], event_id: str) -> None:
    room_id = quote(matrix_env["room_id"], safe="")
    redacts = quote(event_id, safe="")
    txn_id = secrets.token_hex(8)
    _request_json(
        MATRIX_HOST_URL,
        "PUT",
        f"/_matrix/client/v3/rooms/{room_id}/redact/{redacts}/{txn_id}",
        token=matrix_env["user_access_token"],
        json_body={"reason": "Matrix Extended one-shot E2E replay"},
        timeout=30,
    )


def _ha_state(token: str, entity_id: str) -> str:
    state = _request_json(HA_URL, "GET", f"/api/states/{entity_id}", token=token)
    return str(state.get("state"))


def _wait_ha_state(token: str, entity_id: str, expected: str, *, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_state = "missing"
    while time.monotonic() < deadline:
        try:
            last_state = _ha_state(token, entity_id)
        except RuntimeError:
            time.sleep(0.5)
            continue
        if last_state == expected:
            return
        time.sleep(0.5)
    raise TimeoutError(f"{entity_id} did not reach {expected}; last_state={last_state}")


def setup_send_reload() -> None:
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    matrix_passwords = json.loads(Path(".ci/matrix-passwords.json").read_text())
    ha_token = _create_ha_admin()
    created = _create_matrix_entry(ha_token, matrix_env, matrix_passwords["bot_password"])
    entry = _wait_entry_loaded(ha_token, timeout=90)
    entry_id = entry.get("entry_id") or created.get("entry_id")
    if not entry_id:
        raise RuntimeError("Matrix Extended config entry has no entry_id")

    before = _matrix_sync(matrix_env["user_access_token"])
    marker = "matrix-extended-ha-e2e-" + secrets.token_hex(6)
    _request_json(
        HA_URL,
        "POST",
        "/api/services/matrix_extended/send",
        token=ha_token,
        json_body={
            "target": [matrix_env["room_id"]],
            "message": marker,
            "actions": [
                {
                    "reaction": "✅",
                    "service": "counter.increment",
                    "target": {"entity_id": "counter.matrix_reaction"},
                }
            ],
        },
        timeout=60,
    )
    after = _matrix_sync(
        matrix_env["user_access_token"],
        since=before["next_batch"],
        timeout_ms=10000,
    )
    event = find_encrypted_event(after, matrix_env["room_id"], matrix_env["bot_user_id"])

    _request_json(
        HA_URL,
        "POST",
        f"/api/config/config_entries/entry/{entry_id}/reload",
        token=ha_token,
        json_body={},
        timeout=60,
    )
    _wait_entry_loaded(ha_token, timeout=90)

    out = Path(".ci/ha-env.json")
    out.write_text(
        json.dumps(
            {
                "access_token": ha_token,
                "entry_id": entry_id,
                "matrix_event_id": event.get("event_id"),
            },
            indent=2,
        )
        + "\n"
    )
    out.chmod(0o600)
    print(f"Home Assistant Matrix E2E ready: entry={entry_id} encrypted_event={event.get('event_id', '<none>')}")


def send_rich() -> None:
    state = json.loads(Path(".ci/ha-env.json").read_text())
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    before = _matrix_sync(matrix_env["user_access_token"])

    _request_json(
        HA_URL,
        "POST",
        "/api/services/matrix_extended/send_location",
        token=state["access_token"],
        json_body={
            "target": [matrix_env["room_id"]],
            "latitude": 52.3676,
            "longitude": 4.9041,
            "description": LOCATION_TEXT,
        },
        timeout=60,
    )
    _request_json(
        HA_URL,
        "POST",
        "/api/services/matrix_extended/send",
        token=state["access_token"],
        json_body={
            "target": [matrix_env["room_id"]],
            "media": [
                {
                    "path": VOICE_PATH,
                    "type": "audio",
                    "filename": "matrix-e2e-voice.wav",
                    "caption": VOICE_TEXT,
                    "duration_ms": 600,
                    "voice": True,
                }
            ],
        },
        timeout=60,
    )

    encrypted = _wait_for_encrypted_events(
        matrix_env["user_access_token"],
        since=before["next_batch"],
        room_id=matrix_env["room_id"],
        sender=matrix_env["bot_user_id"],
        expected_count=2,
        timeout=20,
    )
    print(
        "Home Assistant rich Matrix E2E sent: "
        f"location={LOCATION_TEXT!r} voice={VOICE_TEXT!r} encrypted_events={encrypted}"
    )


def verify_restart() -> None:
    state = json.loads(Path(".ci/ha-env.json").read_text())
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    entry = _wait_entry_loaded(state["access_token"], timeout=120)
    if entry.get("entry_id") != state["entry_id"]:
        raise RuntimeError("Matrix Extended entry changed across HA restart")

    event_id = state.get("matrix_event_id")
    if not event_id:
        raise RuntimeError("reaction test event id is missing")
    _wait_ha_state(state["access_token"], "counter.matrix_reaction", "0", timeout=30)
    reaction_event_id = _matrix_react(matrix_env, event_id, "✅")
    _wait_ha_state(state["access_token"], "counter.matrix_reaction", "1", timeout=30)

    # Matrix forbids duplicate annotations from one sender while the first
    # annotation exists. Redact it, then rebuild the config entry from Store
    # before sending the same reaction again. If consumption was not persisted,
    # the action would be restored and the counter would reach 2.
    _matrix_redact(matrix_env, reaction_event_id)
    _request_json(
        HA_URL,
        "POST",
        f"/api/config/config_entries/entry/{state['entry_id']}/reload",
        token=state["access_token"],
        json_body={},
        timeout=60,
    )
    _wait_entry_loaded(state["access_token"], timeout=90)
    _matrix_react(matrix_env, event_id, "✅")
    time.sleep(3)
    final_state = _ha_state(state["access_token"], "counter.matrix_reaction")
    if final_state != "1":
        raise RuntimeError(f"reaction action was not one-shot after restart; counter={final_state}")

    print(
        f"Home Assistant restart verified: entry={state['entry_id']} "
        "persistent_reaction_action=one-shot"
    )


def main() -> int:
    modes = {"setup-send-reload", "send-rich", "verify-restart"}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print(
            "usage: ha-e2e.py {setup-send-reload|send-rich|verify-restart}",
            file=sys.stderr,
        )
        return 2
    if sys.argv[1] == "setup-send-reload":
        setup_send_reload()
    elif sys.argv[1] == "send-rich":
        send_rich()
    else:
        verify_restart()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())