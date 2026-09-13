#!/usr/bin/env python3
"""Verify Matrix Extended recovers from a live Synapse outage."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import secrets
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
HA_E2E_SCRIPT = ROOT / "ci" / "scripts" / "ha-e2e.py"
OUTBOX_ENV = ROOT / ".ci" / "outbox-env.json"


def _load_ha_e2e():
    spec = importlib.util.spec_from_file_location("matrix_extended_ha_e2e", HA_E2E_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ha-e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HA = _load_ha_e2e()


def find_matrix_state(
    states: list[dict[str, Any]],
    *,
    entity_domain: str,
    friendly_suffix: str,
) -> dict[str, Any]:
    """Find one Matrix Extended entity by domain and translated friendly-name suffix."""
    prefix = f"{entity_domain}."
    for state in states:
        entity_id = str(state.get("entity_id", ""))
        attributes = state.get("attributes") or {}
        friendly_name = str(attributes.get("friendly_name", ""))
        if (
            entity_id.startswith(prefix)
            and friendly_name.startswith("Matrix ")
            and friendly_name.endswith(friendly_suffix)
        ):
            return state
    raise LookupError(
        f"Matrix Extended {entity_domain} state ending with {friendly_suffix!r} not found"
    )


def _ha_states(token: str) -> list[dict[str, Any]]:
    states = HA._request_json(HA.HA_URL, "GET", "/api/states", token=token)
    if not isinstance(states, list):
        raise RuntimeError("Home Assistant /api/states did not return a list")
    return states


def _wait_matrix_state(
    token: str,
    *,
    entity_domain: str,
    friendly_suffix: str,
    predicate: Callable[[dict[str, Any]], bool],
    timeout: float = 75,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            state = find_matrix_state(
                _ha_states(token),
                entity_domain=entity_domain,
                friendly_suffix=friendly_suffix,
            )
        except LookupError:
            time.sleep(0.5)
            continue
        last = state
        if predicate(state):
            return state
        time.sleep(0.5)
    last_value = None if last is None else last.get("state")
    raise TimeoutError(
        f"Matrix state {friendly_suffix!r} did not reach expected value; last={last_value!r}"
    )


def _read_state() -> tuple[dict[str, Any], dict[str, Any]]:
    matrix_env = json.loads((ROOT / ".ci" / "matrix-env.json").read_text())
    ha_env = json.loads((ROOT / ".ci" / "ha-env.json").read_text())
    return matrix_env, ha_env


def _encrypted_bot_events(sync: dict[str, Any], matrix_env: dict[str, Any]) -> list[dict[str, Any]]:
    events = (
        sync.get("rooms", {})
        .get("join", {})
        .get(matrix_env["room_id"], {})
        .get("timeline", {})
        .get("events", [])
    )
    return [
        event
        for event in events
        if event.get("type") == "m.room.encrypted"
        and event.get("sender") == matrix_env["bot_user_id"]
    ]


def arm_outbox() -> None:
    """Capture a Matrix sync token and marker before the outage begins."""
    matrix_env, _ = _read_state()
    sync = HA._matrix_sync(matrix_env["user_access_token"])
    state = {
        "since": sync["next_batch"],
        "marker": "matrix-extended-outbox-" + secrets.token_hex(6),
    }
    OUTBOX_ENV.write_text(json.dumps(state, indent=2) + "\n")
    OUTBOX_ENV.chmod(0o600)
    print("Persistent outbox E2E armed")


def wait_disconnected() -> None:
    """Prove the running HA listener notices that Synapse went away."""
    _, ha_env = _read_state()
    token = ha_env["access_token"]
    connection = _wait_matrix_state(
        token,
        entity_domain="binary_sensor",
        friendly_suffix="Connection",
        predicate=lambda state: state.get("state") == "off",
    )
    error = _wait_matrix_state(
        token,
        entity_domain="sensor",
        friendly_suffix="Last error",
        predicate=lambda state: "Matrix sync:" in str(state.get("state", "")),
    )
    print(
        "Synapse outage observed by Home Assistant: "
        f"connection={connection.get('state')} error={error.get('state')}"
    )


def queue_outbox() -> None:
    """Send through HA while Synapse is down; the service must queue, not fail."""
    _, ha_env = _read_state()
    queued = json.loads(OUTBOX_ENV.read_text())
    HA._request_json(
        HA.HA_URL,
        "POST",
        "/api/services/matrix_extended/send",
        token=ha_env["access_token"],
        json_body={"message": queued["marker"]},
        timeout=60,
    )
    print("Matrix send accepted into persistent outbox while Synapse is offline")


def verify_reconnect() -> None:
    """Prove queued send, inbound listener, and outbound E2EE recover without reload."""
    matrix_env, ha_env = _read_state()
    ha_token = ha_env["access_token"]
    queued = json.loads(OUTBOX_ENV.read_text())

    queued_sync = HA._matrix_sync(
        matrix_env["user_access_token"],
        since=queued["since"],
        timeout_ms=15000,
    )
    queued_events = _encrypted_bot_events(queued_sync, matrix_env)
    if not queued_events:
        raise RuntimeError("persistent outbox did not deliver an encrypted event after reconnect")

    receive_before = find_matrix_state(
        _ha_states(ha_token),
        entity_domain="sensor",
        friendly_suffix="Last incoming event",
    ).get("state")

    inbound_marker = "matrix-extended-reconnect-in-" + secrets.token_hex(6)
    txn_id = "reconnect-" + secrets.token_hex(8)
    inbound = HA._request_json(
        HA.MATRIX_HOST_URL,
        "PUT",
        f"/_matrix/client/v3/rooms/{matrix_env['room_id']}/send/m.room.message/{txn_id}",
        token=matrix_env["user_access_token"],
        json_body={"msgtype": "m.text", "body": inbound_marker},
        timeout=30,
    )
    inbound_event_id = inbound.get("event_id")
    if not inbound_event_id:
        raise RuntimeError("Matrix reconnect inbound send returned no event_id")

    receive_after = _wait_matrix_state(
        ha_token,
        entity_domain="sensor",
        friendly_suffix="Last incoming event",
        predicate=lambda state: state.get("state") not in {
            None,
            "",
            "unknown",
            "unavailable",
            receive_before,
        },
        timeout=75,
    )
    connection = _wait_matrix_state(
        ha_token,
        entity_domain="binary_sensor",
        friendly_suffix="Connection",
        predicate=lambda state: state.get("state") == "on",
        timeout=30,
    )

    before = HA._matrix_sync(matrix_env["user_access_token"])
    outbound_marker = "matrix-extended-reconnect-out-" + secrets.token_hex(6)
    HA._request_json(
        HA.HA_URL,
        "POST",
        "/api/services/matrix_extended/send",
        token=ha_token,
        json_body={"target": [matrix_env["room_id"]], "message": outbound_marker},
        timeout=60,
    )
    after = HA._matrix_sync(
        matrix_env["user_access_token"],
        since=before["next_batch"],
        timeout_ms=10000,
    )
    encrypted = HA.find_encrypted_event(
        after,
        matrix_env["room_id"],
        matrix_env["bot_user_id"],
    )

    print(
        "Synapse reconnect verified without HA reload: "
        f"queued_event={queued_events[0].get('event_id', '<none>')} "
        f"inbound_event={inbound_event_id} "
        f"last_receive={receive_after.get('state')} "
        f"connection={connection.get('state')} "
        f"encrypted_event={encrypted.get('event_id', '<none>')}"
    )


def main() -> int:
    commands = {
        "arm-outbox": arm_outbox,
        "wait-disconnected": wait_disconnected,
        "queue-outbox": queue_outbox,
        "verify-reconnect": verify_reconnect,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(
            "usage: ha-reconnect.py {arm-outbox|wait-disconnected|queue-outbox|verify-reconnect}",
            file=sys.stderr,
        )
        return 2
    commands[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
