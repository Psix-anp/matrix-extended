#!/usr/bin/env python3
"""Exercise Native Matrix Control against the disposable HA/Synapse stack."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Iterable, Mapping
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nio import AsyncClient, AsyncClientConfig, LoginResponse, RoomSendResponse, SyncResponse

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
STATE_PATH = Path(".ci/matrix-control-state.json")
STORE_PATH = Path(".ci/nio-matrix-control")
MATRIX_ENV_PATH = Path(".ci/matrix-env.json")
MATRIX_PASSWORDS_PATH = Path(".ci/matrix-passwords.json")
HA_ENV_PATH = Path(".ci/ha-env.json")
PANEL_ID = "e2e_control"
PANEL_METADATA_KEY = "io.psix.matrix_extended.panel"
PANEL_SCHEMA = 1
LIGHT_ENTITY = "input_boolean.matrix_control_light"
DANGEROUS_ENTITY = "input_boolean.matrix_control_dangerous"
LIGHT_ACTION_LABEL = "Toggle light"
DANGEROUS_ACTION_LABEL = "Dangerous target"


def _content(event: Mapping[str, Any]) -> Mapping[str, Any]:
    content = event.get("content")
    return content if isinstance(content, Mapping) else {}


def find_panel_root(
    events: Iterable[Mapping[str, Any]],
    *,
    panel_id: str,
    sender: str,
) -> Mapping[str, Any]:
    """Find one decrypted panel root from the expected Matrix sender."""
    for event in events:
        if event.get("type") != "m.room.message" or event.get("sender") != sender:
            continue
        content = _content(event)
        relation = content.get("m.relates_to")
        if isinstance(relation, Mapping) and relation.get("rel_type") == "m.replace":
            continue
        marker = content.get(PANEL_METADATA_KEY)
        if (
            isinstance(marker, Mapping)
            and marker.get("schema") == PANEL_SCHEMA
            and marker.get("panel_id") == panel_id
        ):
            return event
    raise LookupError(f"no panel root for {panel_id} from {sender}")


def is_panel_edit(event: Mapping[str, Any], root_event_id: str) -> bool:
    """Return whether one decrypted event edits the original panel root."""
    if event.get("type") != "m.room.message":
        return False
    relation = _content(event).get("m.relates_to")
    return (
        isinstance(relation, Mapping)
        and relation.get("rel_type") == "m.replace"
        and relation.get("event_id") == root_event_id
    )


def find_confirmation_reply(
    events: Iterable[Mapping[str, Any]],
    *,
    root_event_id: str,
    action_label: str,
    sender: str,
) -> Mapping[str, Any]:
    """Find the same-root dangerous-action confirmation reply."""
    expected = f"⚠️ Confirm: {action_label}"
    for event in events:
        if event.get("type") != "m.room.message" or event.get("sender") != sender:
            continue
        content = _content(event)
        if content.get("body") != expected:
            continue
        relation = content.get("m.relates_to")
        if not isinstance(relation, Mapping):
            continue
        reply = relation.get("m.in_reply_to")
        if isinstance(reply, Mapping) and reply.get("event_id") == root_event_id:
            return event
    raise LookupError(
        f"no confirmation reply for {action_label} bound to {root_event_id}"
    )


def _is_panel_root(event: Mapping[str, Any], *, sender: str) -> bool:
    if event.get("type") != "m.room.message" or event.get("sender") != sender:
        return False
    content = _content(event)
    relation = content.get("m.relates_to")
    # Edits retain panel metadata, but their event IDs are not new roots.
    if isinstance(relation, Mapping) and relation.get("rel_type") == "m.replace":
        return False
    marker = content.get(PANEL_METADATA_KEY)
    return (
        isinstance(marker, Mapping)
        and marker.get("schema") == PANEL_SCHEMA
        and marker.get("panel_id") == PANEL_ID
    )


def _edit_body(event: Mapping[str, Any]) -> str:
    new_content = _content(event).get("m.new_content")
    if not isinstance(new_content, Mapping):
        return ""
    return str(new_content.get("body") or "")


def _request_json(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: Any | None = None,
    timeout: float = 30,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        body = err.read().decode(errors="replace")[:1200]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {body}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"request failed for {method} {path}: {type(err).__name__}") from err
    return json.loads(raw or b"{}")


def _ha_request(
    method: str,
    path: str,
    *,
    token: str,
    json_body: Any | None = None,
    timeout: float = 30,
) -> Any:
    return _request_json(
        HA_URL,
        method,
        path,
        token=token,
        json_body=json_body,
        timeout=timeout,
    )


def _matrix_request(
    matrix_env: Mapping[str, str],
    method: str,
    path: str,
    *,
    token: str,
    json_body: Any | None = None,
) -> Any:
    return _request_json(
        matrix_env["homeserver"].rstrip("/"),
        method,
        path,
        token=token,
        json_body=json_body,
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def _write_state(state: Mapping[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(dict(state), indent=2) + "\n", encoding="utf-8")
    STATE_PATH.chmod(0o600)


def _ha_state(token: str, entity_id: str) -> str:
    value = _ha_request("GET", f"/api/states/{entity_id}", token=token)
    return str(value.get("state"))


def _wait_ha_state(
    token: str,
    entity_id: str,
    expected: str,
    *,
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    last = "missing"
    while time.monotonic() < deadline:
        try:
            last = _ha_state(token, entity_id)
        except RuntimeError:
            time.sleep(0.4)
            continue
        if last == expected:
            return
        time.sleep(0.4)
    raise TimeoutError(f"{entity_id} did not reach {expected}; last={last}")


def _ha_service(token: str, domain: str, service: str, data: Mapping[str, Any]) -> Any:
    return _ha_request(
        "POST",
        f"/api/services/{domain}/{service}",
        token=token,
        json_body=dict(data),
        timeout=60,
    )


def _expect_flow(result: Mapping[str, Any], *, kind: str, step_id: str) -> None:
    if result.get("type") != kind or result.get("step_id") != step_id:
        raise RuntimeError(f"unexpected options flow result for {step_id}: {result}")


def _start_options_flow(token: str, entry_id: str) -> dict[str, Any]:
    result = _ha_request(
        "POST",
        "/api/config/config_entries/options/flow",
        token=token,
        json_body={"handler": entry_id},
    )
    _expect_flow(result, kind="menu", step_id="init")
    return result


def _flow_post(token: str, flow_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
    result = _ha_request(
        "POST",
        f"/api/config/config_entries/options/flow/{flow_id}",
        token=token,
        json_body=dict(body),
        timeout=60,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"invalid options flow response: {result}")
    return result


def _configure_panel(
    token: str,
    entry_id: str,
    matrix_env: Mapping[str, str],
) -> None:
    flow = _start_options_flow(token, entry_id)
    flow_id = str(flow["flow_id"])
    panel_menu = _flow_post(token, flow_id, {"next_step_id": "control_panels"})
    _expect_flow(panel_menu, kind="menu", step_id="control_panels")
    panel_form = _flow_post(token, flow_id, {"next_step_id": "panel_add"})
    _expect_flow(panel_form, kind="form", step_id="panel_add")
    panel_draft = _flow_post(
        token,
        flow_id,
        {
            "panel_id": PANEL_ID,
            "room_id": matrix_env["room_id"],
            "title": "Matrix Control E2E",
            "enabled": True,
            "entities": [LIGHT_ENTITY, DANGEROUS_ENTITY],
            "allowed_users": [matrix_env["user_user_id"]],
            "debounce": 0.5,
        },
    )
    _expect_flow(panel_draft, kind="menu", step_id="panel_manage")

    for action in (
        {
            "id": "light_toggle",
            "reaction": "💡",
            "label": LIGHT_ACTION_LABEL,
            "service": "input_boolean.toggle",
            "target": {"entity_id": [LIGHT_ENTITY]},
            "data": "",
            "confirmation_required": False,
        },
        {
            "id": "dangerous_on",
            "reaction": "🔓",
            "label": DANGEROUS_ACTION_LABEL,
            "service": "input_boolean.turn_on",
            "target": {"entity_id": [DANGEROUS_ENTITY]},
            "data": "",
            "confirmation_required": True,
        },
    ):
        action_form = _flow_post(token, flow_id, {"next_step_id": "panel_action_add"})
        _expect_flow(action_form, kind="form", step_id="panel_action_add")
        action_result = _flow_post(token, flow_id, action)
        _expect_flow(action_result, kind="menu", step_id="panel_manage")

    save_form = _flow_post(token, flow_id, {"next_step_id": "panel_save"})
    _expect_flow(save_form, kind="form", step_id="panel_save")
    saved = _flow_post(token, flow_id, {"panel_confirm": True})
    if saved.get("type") != "create_entry":
        raise RuntimeError(f"control panel options save failed: {saved}")
    _ha_request(
        "POST",
        f"/api/config/config_entries/entry/{entry_id}/reload",
        token=token,
        json_body={},
        timeout=60,
    )


def _repair_panel(token: str, entry_id: str, *, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        flow = _start_options_flow(token, entry_id)
        flow_id = str(flow["flow_id"])
        menu = _flow_post(token, flow_id, {"next_step_id": "control_panels"})
        _expect_flow(menu, kind="menu", step_id="control_panels")
        form = _flow_post(token, flow_id, {"next_step_id": "panel_repair"})
        _expect_flow(form, kind="form", step_id="panel_repair")
        last = _flow_post(token, flow_id, {"panel_id": PANEL_ID})
        if last.get("type") == "menu" and last.get("step_id") == "control_panels":
            return
        errors = last.get("errors", {}) if isinstance(last, Mapping) else {}
        if errors.get("base") not in {"panel_not_needs_repair", None}:
            raise RuntimeError(f"control panel Repair failed: {last}")
        time.sleep(0.75)
    raise TimeoutError(f"control panel never became repairable: {last}")


def _event_dict(event: Any) -> dict[str, Any]:
    source = getattr(event, "source", {})
    result = dict(source) if isinstance(source, Mapping) else {}
    event_id = getattr(event, "event_id", None)
    sender = getattr(event, "sender", None)
    if event_id:
        result.setdefault("event_id", str(event_id))
    if sender:
        result.setdefault("sender", str(sender))
    if "type" not in result:
        name = type(event).__name__
        if name.startswith("RoomMessage"):
            result["type"] = "m.room.message"
        elif "Redaction" in name:
            result["type"] = "m.room.redaction"
        elif "Reaction" in name:
            result["type"] = "m.reaction"
    return result


def _new_client(matrix_env: Mapping[str, str], *, device_id: str | None = None) -> AsyncClient:
    STORE_PATH.mkdir(parents=True, exist_ok=True)
    return AsyncClient(
        matrix_env["homeserver"],
        matrix_env["user_user_id"],
        device_id=device_id,
        store_path=str(STORE_PATH),
        config=AsyncClientConfig(encryption_enabled=True, store_sync_tokens=True),
    )


async def _login_control_client(
    matrix_env: Mapping[str, str], passwords: Mapping[str, str]
) -> tuple[AsyncClient, dict[str, Any]]:
    client = _new_client(matrix_env)
    login = await client.login(
        passwords["user_password"],
        device_name="Matrix Extended Native Control E2E",
    )
    if not isinstance(login, LoginResponse):
        await client.close()
        raise RuntimeError(f"Matrix control recipient login failed: {login}")
    if client.should_upload_keys:
        await client.keys_upload()
    response = await client.sync(
        timeout=3000,
        full_state=True,
        sync_filter={"room": {"timeline": {"limit": 0}}},
    )
    if not isinstance(response, SyncResponse):
        await client.close()
        raise RuntimeError(f"initial Matrix control sync failed: {response}")
    if client.should_query_keys:
        await client.keys_query()
    room = client.rooms.get(matrix_env["room_id"])
    if room is None or not room.encrypted:
        await client.close()
        raise RuntimeError("Matrix control E2E room is not loaded as encrypted")
    state = {
        "access_token": login.access_token,
        "device_id": login.device_id,
        "next_batch": response.next_batch,
    }
    return client, state


def _restore_control_client(
    matrix_env: Mapping[str, str], state: Mapping[str, Any]
) -> AsyncClient:
    client = _new_client(matrix_env, device_id=str(state["device_id"]))
    client.restore_login(
        user_id=matrix_env["user_user_id"],
        device_id=str(state["device_id"]),
        access_token=str(state["access_token"]),
    )
    return client


async def _sync_events(
    client: AsyncClient,
    *,
    room_id: str,
    since: str | None,
    timeout_ms: int = 3000,
) -> tuple[list[dict[str, Any]], str]:
    response = await client.sync(timeout=timeout_ms, since=since)
    if not isinstance(response, SyncResponse):
        raise RuntimeError(f"Matrix control sync failed: {response}")
    room = response.rooms.join.get(room_id)
    events = [] if room is None else [_event_dict(event) for event in room.timeline.events]
    return events, response.next_batch


async def _wait_matrix_event(
    client: AsyncClient,
    state: dict[str, Any],
    *,
    room_id: str,
    predicate: Callable[[Mapping[str, Any]], bool],
    description: str,
    timeout: float = 30,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    seen: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        events, next_batch = await _sync_events(
            client,
            room_id=room_id,
            since=state.get("next_batch"),
            timeout_ms=min(3000, max(500, int((deadline - time.monotonic()) * 1000))),
        )
        state["next_batch"] = next_batch
        seen.extend(events)
        matches = [event for event in events if predicate(event)]
        if matches:
            return matches[0], seen
    raise TimeoutError(f"did not observe Matrix control event: {description}")


async def _collect_for(
    client: AsyncClient,
    state: dict[str, Any],
    *,
    room_id: str,
    seconds: float,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + seconds
    seen: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        events, next_batch = await _sync_events(
            client,
            room_id=room_id,
            since=state.get("next_batch"),
            timeout_ms=min(1000, max(250, int(remaining * 1000))),
        )
        state["next_batch"] = next_batch
        seen.extend(events)
    return seen


async def _send_reaction(
    client: AsyncClient,
    room_id: str,
    event_id: str,
    reaction: str,
) -> str:
    response = await client.room_send(
        room_id,
        "m.reaction",
        {
            "m.relates_to": {
                "rel_type": "m.annotation",
                "event_id": event_id,
                "key": reaction,
            }
        },
        tx_id=secrets.token_hex(8),
        ignore_unverified_devices=True,
    )
    if not isinstance(response, RoomSendResponse):
        raise RuntimeError(f"Matrix control reaction failed: {response}")
    return response.event_id


def _assert_pinned(matrix_env: Mapping[str, str], access_token: str, root_event_id: str) -> None:
    room = quote(matrix_env["room_id"], safe="")
    state = _matrix_request(
        matrix_env,
        "GET",
        f"/_matrix/client/v3/rooms/{room}/state/m.room.pinned_events/",
        token=access_token,
    )
    pins = state.get("pinned", []) if isinstance(state, Mapping) else []
    if root_event_id not in pins:
        raise RuntimeError(f"control panel root is not pinned: {pins}")


def _grant_redaction_power(matrix_env: Mapping[str, str]) -> None:
    room = quote(matrix_env["room_id"], safe="")
    path = f"/_matrix/client/v3/rooms/{room}/state/m.room.power_levels/"
    current = _matrix_request(
        matrix_env,
        "GET",
        path,
        token=matrix_env["bot_access_token"],
    )
    if not isinstance(current, dict):
        raise RuntimeError(f"invalid power-level state: {current}")
    users = dict(current.get("users", {}))
    redact_level = int(current.get("redact", 50) or 50)
    users[matrix_env["user_user_id"]] = max(
        int(users.get(matrix_env["user_user_id"], 0) or 0),
        redact_level,
        50,
    )
    current["users"] = users
    _matrix_request(
        matrix_env,
        "PUT",
        path,
        token=matrix_env["bot_access_token"],
        json_body=current,
    )


async def _verify() -> None:
    matrix_env = _read_json(MATRIX_ENV_PATH)
    passwords = _read_json(MATRIX_PASSWORDS_PATH)
    ha_env = _read_json(HA_ENV_PATH)
    ha_token = str(ha_env["access_token"])
    entry_id = str(ha_env["entry_id"])
    room_id = str(matrix_env["room_id"])
    bot_user_id = str(matrix_env["bot_user_id"])

    _ha_service(
        ha_token,
        "input_boolean",
        "turn_off",
        {"entity_id": [LIGHT_ENTITY, DANGEROUS_ENTITY]},
    )
    _wait_ha_state(ha_token, LIGHT_ENTITY, "off")
    _wait_ha_state(ha_token, DANGEROUS_ENTITY, "off")

    client, state = await _login_control_client(matrix_env, passwords)
    try:
        # Let the bot's long-poll listener observe this fresh recipient device
        # before panel creation starts a new encrypted Megolm session.
        await asyncio.sleep(1.0)
        _configure_panel(ha_token, entry_id, matrix_env)

        root, seen = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: _is_panel_root(event, sender=bot_user_id),
            description="encrypted control panel root",
            timeout=40,
        )
        root_event_id = str(root["event_id"])
        roots = [event for event in seen if _is_panel_root(event, sender=bot_user_id)]
        if len(roots) != 1:
            raise RuntimeError(f"expected one control root, got {len(roots)}")
        _assert_pinned(matrix_env, str(state["access_token"]), root_event_id)

        _ha_service(ha_token, "input_boolean", "turn_on", {"entity_id": LIGHT_ENTITY})
        _wait_ha_state(ha_token, LIGHT_ENTITY, "on")
        edit_on, _ = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id)
            and f"{LIGHT_ENTITY}: on" in _edit_body(event),
            description="same-root state edit to light on",
        )
        if not is_panel_edit(edit_on, root_event_id):
            raise RuntimeError("live state update did not target original root")

        _ha_service(ha_token, "input_boolean", "turn_off", {"entity_id": LIGHT_ENTITY})
        _wait_ha_state(ha_token, LIGHT_ENTITY, "off")
        await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id)
            and f"{LIGHT_ENTITY}: off" in _edit_body(event),
            description="light reset edit",
        )

        await _send_reaction(client, room_id, root_event_id, "💡")
        _wait_ha_state(ha_token, LIGHT_ENTITY, "on", timeout=30)
        await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id)
            and f"{LIGHT_ENTITY}: on" in _edit_body(event),
            description="low-risk reaction reflected by actual HA state",
        )

        await _send_reaction(client, room_id, root_event_id, "🔓")
        confirmation, _ = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: (
                event.get("sender") == bot_user_id
                and _content(event).get("body")
                == f"⚠️ Confirm: {DANGEROUS_ACTION_LABEL}"
            ),
            description="dangerous action confirmation reply",
        )
        confirmation = dict(
            find_confirmation_reply(
                [confirmation],
                root_event_id=root_event_id,
                action_label=DANGEROUS_ACTION_LABEL,
                sender=bot_user_id,
            )
        )
        if _ha_state(ha_token, DANGEROUS_ENTITY) != "off":
            raise RuntimeError("dangerous action executed before confirmation")
        await _send_reaction(client, room_id, str(confirmation["event_id"]), "✅")
        _wait_ha_state(ha_token, DANGEROUS_ENTITY, "on", timeout=30)
        await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id)
            and f"{DANGEROUS_ENTITY}: on" in _edit_body(event),
            description="confirmed dangerous action reflected by HA state",
        )

        state.update(
            {
                "root_event_id": root_event_id,
                "panel_id": PANEL_ID,
                "room_id": room_id,
                "bot_user_id": bot_user_id,
            }
        )
        _write_state(state)
        print(
            "Native Matrix Control verify ok: encrypted root, pin, same-root edits, "
            "low-risk reaction and dangerous confirmation"
        )
    finally:
        await client.close()


def _outage_flips() -> None:
    state = _read_json(STATE_PATH)
    ha_env = _read_json(HA_ENV_PATH)
    ha_token = str(ha_env["access_token"])
    # Synapse is intentionally unavailable here. Separate transitions ensure
    # the panel manager has opportunities to observe and coalesce each state.
    for desired in ("off", "on", "off"):
        _ha_service(
            ha_token,
            "input_boolean",
            "turn_on" if desired == "on" else "turn_off",
            {"entity_id": LIGHT_ENTITY},
        )
        _wait_ha_state(ha_token, LIGHT_ENTITY, desired)
        time.sleep(0.8)
    state["expected_outage_state"] = "off"
    _write_state(state)
    print("Native Matrix Control outage flips queued/coalesced to final state=off")


async def _verify_recovery() -> None:
    matrix_env = _read_json(MATRIX_ENV_PATH)
    state = _read_json(STATE_PATH)
    root_event_id = str(state["root_event_id"])
    room_id = str(state["room_id"])
    expected = str(state["expected_outage_state"])
    client = _restore_control_client(matrix_env, state)
    try:
        first, seen = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id),
            description="first control edit after Synapse recovery",
            timeout=40,
        )
        if f"{LIGHT_ENTITY}: {expected}" not in _edit_body(first):
            raise RuntimeError(
                "first recovered panel edit did not contain final coalesced state: "
                + _edit_body(first)
            )
        extra = await _collect_for(client, state, room_id=room_id, seconds=3.0)
        edits = [
            event
            for event in [*seen, *extra]
            if is_panel_edit(event, root_event_id)
        ]
        if len(edits) != 1:
            raise RuntimeError(f"panel recovery edit storm detected: {len(edits)} edits")
        _write_state(state)
        print("Native Matrix Control recovery ok: latest state only, no edit storm")
    finally:
        await client.close()


async def _verify_restart_repair() -> None:
    matrix_env = _read_json(MATRIX_ENV_PATH)
    ha_env = _read_json(HA_ENV_PATH)
    state = _read_json(STATE_PATH)
    ha_token = str(ha_env["access_token"])
    entry_id = str(ha_env["entry_id"])
    room_id = str(state["room_id"])
    bot_user_id = str(state["bot_user_id"])
    root_event_id = str(state["root_event_id"])
    client = _restore_control_client(matrix_env, state)
    try:
        # A post-restart state transition must still edit the original root.
        _ha_service(ha_token, "input_boolean", "turn_on", {"entity_id": LIGHT_ENTITY})
        _wait_ha_state(ha_token, LIGHT_ENTITY, "on")
        restart_edit, seen = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: is_panel_edit(event, root_event_id)
            and f"{LIGHT_ENTITY}: on" in _edit_body(event),
            description="post-HA-restart edit targeting original root",
            timeout=40,
        )
        if not is_panel_edit(restart_edit, root_event_id):
            raise RuntimeError("HA restart changed the control root identity")
        duplicate_roots = [
            event
            for event in seen
            if _is_panel_root(event, sender=bot_user_id)
            and event.get("event_id") != root_event_id
        ]
        if duplicate_roots:
            raise RuntimeError("HA restart created a duplicate control root")

        # The authorized test user needs room redaction power only for this
        # explicit real-stack lifecycle check.
        _grant_redaction_power(matrix_env)
        response = await client.room_redact(
            room_id,
            root_event_id,
            reason="Matrix Extended Native Control E2E repair check",
        )
        if getattr(response, "event_id", None) is None:
            raise RuntimeError(f"control root redaction failed: {response}")
        await asyncio.sleep(2.0)

        _ha_service(ha_token, "input_boolean", "turn_off", {"entity_id": LIGHT_ENTITY})
        _wait_ha_state(ha_token, LIGHT_ENTITY, "off")
        before_repair = await _collect_for(client, state, room_id=room_id, seconds=2.5)
        if any(_is_panel_root(event, sender=bot_user_id) for event in before_repair):
            raise RuntimeError("redacted control root was replaced automatically")
        if any(is_panel_edit(event, root_event_id) for event in before_repair):
            raise RuntimeError("needs_repair panel kept editing its redacted root")

        _repair_panel(ha_token, entry_id, timeout=20)
        new_root_event, repair_seen = await _wait_matrix_event(
            client,
            state,
            room_id=room_id,
            predicate=lambda event: _is_panel_root(event, sender=bot_user_id)
            and event.get("event_id") != root_event_id,
            description="explicit Repair replacement root",
            timeout=40,
        )
        new_root_id = str(new_root_event["event_id"])
        after_repair = await _collect_for(client, state, room_id=room_id, seconds=2.0)
        replacement_roots = [
            event
            for event in [*repair_seen, *after_repair]
            if _is_panel_root(event, sender=bot_user_id)
            and event.get("event_id") != root_event_id
        ]
        unique_ids = {str(event.get("event_id")) for event in replacement_roots}
        if unique_ids != {new_root_id}:
            raise RuntimeError(f"Repair created unexpected roots: {sorted(unique_ids)}")
        _assert_pinned(matrix_env, str(state["access_token"]), new_root_id)
        state["root_event_id"] = new_root_id
        _write_state(state)
        print(
            "Native Matrix Control restart/repair ok: original root reused after restart; "
            "redaction entered needs_repair; explicit Repair created exactly one new root"
        )
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("verify", "outage-flips", "verify-recovery", "verify-restart-repair"),
    )
    args = parser.parse_args()
    if args.mode == "verify":
        asyncio.run(_verify())
    elif args.mode == "outage-flips":
        _outage_flips()
    elif args.mode == "verify-recovery":
        asyncio.run(_verify_recovery())
    else:
        asyncio.run(_verify_restart_repair())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
