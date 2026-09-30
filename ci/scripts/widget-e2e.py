#!/usr/bin/env python3
"""Exercise Native Matrix Widget against real HA, Synapse and Element Web."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
MATRIX_URL = os.environ.get("MATRIX_URL", "http://127.0.0.1:8008").rstrip("/")
ELEMENT_URL = os.environ.get("ELEMENT_URL", "http://127.0.0.1:8080").rstrip("/")
WIDGET_URL = os.environ.get("WIDGET_URL", "http://127.0.0.1:8090/")
PROFILE_DIR = Path(os.environ.get("ELEMENT_PROFILE_DIR", ".ci/element-profile"))
SCREENSHOT_DIR = Path(os.environ.get("ELEMENT_SCREENSHOT_DIR", ".ci/screenshots"))
MATRIX_ENV_PATH = Path(".ci/matrix-env.json")
HA_ENV_PATH = Path(".ci/ha-env.json")
WIDGET_STATE_PATH = Path(".ci/widget-e2e.json")

PANEL_ID = "e2e_control"
PANEL_TITLE = "Matrix Control E2E"
WIDGET_EVENT_TYPE = "io.psix.matrix_extended.widget.v1"
WIDGET_SAFE_ENTITY = "switch.matrix_widget_switch"
WIDGET_DANGEROUS_ENTITY = "switch.matrix_widget_dangerous"
SAFE_TARGET = "input_boolean.matrix_control_light"
DANGEROUS_TARGET = "input_boolean.matrix_control_dangerous"
LEGACY_ENTITIES = [SAFE_TARGET, DANGEROUS_TARGET]
ROOM_NAME = "Matrix Extended E2E"


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


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
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        detail = err.read().decode(errors="replace")[:1200]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {detail}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"request failed for {method} {path}: {type(err).__name__}") from err
    return json.loads(raw or b"{}")


def _ha(token: str, method: str, path: str, body: Any | None = None) -> Any:
    return _request_json(HA_URL, method, path, token=token, json_body=body, timeout=60)


def _flow_post(token: str, flow_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
    result = _ha(token, "POST", f"/api/config/config_entries/options/flow/{flow_id}", dict(body))
    if not isinstance(result, dict):
        raise RuntimeError(f"invalid options flow response: {result}")
    return result


def _expect(result: Mapping[str, Any], *, kind: str, step: str) -> None:
    if result.get("type") != kind or result.get("step_id") != step:
        raise RuntimeError(f"expected {kind}/{step}, got: {result}")


def _wait_entry_loaded(token: str, entry_id: str, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    last = "unknown"
    while time.monotonic() < deadline:
        entries = _ha(token, "GET", "/api/config/config_entries/entry")
        rows = entries.get("result", entries.get("entries", [])) if isinstance(entries, dict) else entries
        for entry in rows:
            if entry.get("entry_id") == entry_id:
                last = str(entry.get("state"))
                if last == "loaded":
                    return
        time.sleep(0.5)
    raise TimeoutError(f"Matrix Extended entry did not load; state={last}")


def _state(token: str, entity_id: str) -> str:
    return str(_ha(token, "GET", f"/api/states/{entity_id}").get("state"))


def _wait_state(token: str, entity_id: str, expected: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last = "missing"
    while time.monotonic() < deadline:
        try:
            last = _state(token, entity_id)
        except RuntimeError:
            time.sleep(0.4)
            continue
        if last == expected:
            return
        time.sleep(0.4)
    raise TimeoutError(f"{entity_id} did not reach {expected}; last={last}")


def _set_targets_off(token: str) -> None:
    _ha(token, "POST", "/api/services/input_boolean/turn_off", {"entity_id": [SAFE_TARGET, DANGEROUS_TARGET]})
    _wait_state(token, SAFE_TARGET, "off")
    _wait_state(token, DANGEROUS_TARGET, "off")


def _configure_widget() -> dict[str, Any]:
    matrix_env = _read(MATRIX_ENV_PATH)
    ha_env = _read(HA_ENV_PATH)
    token = str(ha_env["access_token"])
    entry_id = str(ha_env["entry_id"])
    _set_targets_off(token)

    start = _ha(token, "POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
    _expect(start, kind="menu", step="init")
    flow_id = str(start["flow_id"])
    _expect(_flow_post(token, flow_id, {"next_step_id": "control_panels"}), kind="menu", step="control_panels")
    _expect(_flow_post(token, flow_id, {"next_step_id": "panel_edit"}), kind="form", step="panel_edit")
    _expect(_flow_post(token, flow_id, {"panel_id": PANEL_ID}), kind="menu", step="panel_manage")
    _expect(_flow_post(token, flow_id, {"next_step_id": "panel_edit_details"}), kind="form", step="panel_edit_details")
    _expect(
        _flow_post(token, flow_id, {
            "room_id": matrix_env["room_id"],
            "title": PANEL_TITLE,
            "enabled": True,
            "entities": [*LEGACY_ENTITIES, WIDGET_SAFE_ENTITY, WIDGET_DANGEROUS_ENTITY],
            "allowed_users": [matrix_env["user_user_id"]],
            "debounce": 0.5,
        }),
        kind="menu", step="panel_manage",
    )

    _expect(_flow_post(token, flow_id, {"next_step_id": "panel_widget"}), kind="form", step="panel_widget")
    _expect(_flow_post(token, flow_id, {"widget_enabled": True, "widget_url": WIDGET_URL}), kind="menu", step="panel_manage")
    widget_form = _flow_post(token, flow_id, {"next_step_id": "panel_widget"})
    _expect(widget_form, kind="form", step="panel_widget")
    widget_text = str(widget_form.get("description_placeholders", {}).get("widget_config") or "")
    if not widget_text:
        raise RuntimeError("Options Flow did not generate Widget configuration")
    widget_config = json.loads(widget_text)
    if not isinstance(widget_config, dict):
        raise RuntimeError("generated Widget configuration is not an object")
    serialized = json.dumps(widget_config)
    for forbidden in ("access_token", "store_key", "password"):
        if forbidden in serialized:
            raise RuntimeError(f"generated Widget configuration leaked {forbidden}")
    integration_device_id = str(widget_config.get("data", {}).get("integration_device_id") or "")
    if not integration_device_id:
        raise RuntimeError("generated Widget config has no integration_device_id")
    _expect(_flow_post(token, flow_id, {"widget_enabled": True, "widget_url": WIDGET_URL}), kind="menu", step="panel_manage")

    for entity_id, confirm in ((WIDGET_SAFE_ENTITY, []), (WIDGET_DANGEROUS_ENTITY, ["toggle"])):
        _expect(_flow_post(token, flow_id, {"next_step_id": "panel_widget_entity"}), kind="form", step="panel_widget_entity")
        _expect(_flow_post(token, flow_id, {"widget_entity_id": entity_id}), kind="form", step="panel_widget_entity")
        _expect(
            _flow_post(token, flow_id, {"widget_controls": ["toggle"], "confirm_controls": confirm}),
            kind="menu", step="panel_manage",
        )

    _expect(_flow_post(token, flow_id, {"next_step_id": "panel_save"}), kind="form", step="panel_save")
    saved = _flow_post(token, flow_id, {"panel_confirm": True})
    if saved.get("type") != "create_entry":
        raise RuntimeError(f"Widget panel save failed: {saved}")
    _wait_entry_loaded(token, entry_id)
    _set_targets_off(token)

    widget_id = str(widget_config["id"])
    content = dict(widget_config)
    content["id"] = widget_id
    content["creatorUserId"] = matrix_env["bot_user_id"]
    room = quote(str(matrix_env["room_id"]), safe="")
    state_key = quote(widget_id, safe="")
    _request_json(MATRIX_URL, "PUT", f"/_matrix/client/v3/rooms/{room}/state/im.vector.modular.widgets/{state_key}", token=matrix_env["bot_access_token"], json_body=content)
    _request_json(
        MATRIX_URL, "PUT", f"/_matrix/client/v3/rooms/{room}/state/io.element.widgets.layout/",
        token=matrix_env["bot_access_token"],
        json_body={"widgets": {widget_id: {"container": "top", "index": 0, "width": 100, "height": 55}}},
    )

    state = {
        "widget_id": widget_id,
        "widget_url": widget_config["url"],
        "integration_user_id": widget_config["data"]["integration_user_id"],
        "integration_device_id": integration_device_id,
        "panel_id": PANEL_ID,
        "room_id": matrix_env["room_id"],
    }
    _write(WIDGET_STATE_PATH, state)
    print(f"Native Widget configured: panel={PANEL_ID} widget={widget_id} integration_device_id={integration_device_id}")
    return state


def _sync(token: str, since: str | None = None, timeout_ms: int = 0) -> dict[str, Any]:
    query = {"timeout": str(timeout_ms)}
    if since:
        query["since"] = since
    return _request_json(MATRIX_URL, "GET", "/_matrix/client/v3/sync?" + urlencode(query), token=token, timeout=max(20, timeout_ms / 1000 + 10))


def _send_widget_to_device(matrix_env: Mapping[str, Any], widget_state: Mapping[str, Any], content: Mapping[str, Any]) -> None:
    event_type = quote(WIDGET_EVENT_TYPE, safe="")
    _request_json(
        MATRIX_URL, "PUT", f"/_matrix/client/v3/sendToDevice/{event_type}/{secrets.token_hex(12)}",
        token=str(matrix_env["user_access_token"]),
        json_body={"messages": {str(widget_state["integration_user_id"]): {str(widget_state["integration_device_id"]): dict(content)}}},
    )


def _wait_to_device(token: str, since: str, predicate: Callable[[dict[str, Any]], bool], *, timeout: float = 30) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout
    cursor = since
    while time.monotonic() < deadline:
        response = _sync(token, cursor, 3000)
        cursor = str(response["next_batch"])
        for event in response.get("to_device", {}).get("events", []):
            if event.get("type") != WIDGET_EVENT_TYPE:
                continue
            content = event.get("content")
            if isinstance(content, dict) and predicate(content):
                return content, cursor
    raise TimeoutError("expected Widget to-device response was not observed")


def _subscribe_snapshot(matrix_env: Mapping[str, Any], widget_state: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    user_token = str(matrix_env["user_access_token"])
    cursor = str(_sync(user_token).get("next_batch"))
    _send_widget_to_device(matrix_env, widget_state, {
        "schema": 1, "op": "subscribe", "room_id": widget_state["room_id"], "panel_id": PANEL_ID, "generation": 0,
    })
    return _wait_to_device(user_token, cursor, lambda content: content.get("op") == "state" and content.get("panel_id") == PANEL_ID)


def _backend_transport_regression() -> int:
    matrix_env = _read(MATRIX_ENV_PATH)
    widget_state = _read(WIDGET_STATE_PATH)
    ha_token = str(_read(HA_ENV_PATH)["access_token"])
    user_token = str(matrix_env["user_access_token"])
    snapshot, cursor = _subscribe_snapshot(matrix_env, widget_state)
    generation = int(snapshot["generation"])
    if generation < 1:
        raise RuntimeError(f"invalid Widget generation: {generation}")

    _set_targets_off(ha_token)
    stale_id = str(uuid4())
    _send_widget_to_device(matrix_env, widget_state, {
        "schema": 1, "op": "action", "room_id": widget_state["room_id"], "panel_id": PANEL_ID,
        "generation": generation - 1, "request_id": stale_id, "kind": "entity_control",
        "entity_id": WIDGET_SAFE_ENTITY, "control": "toggle",
    })
    stale_error, cursor = _wait_to_device(user_token, cursor, lambda content: content.get("op") == "error" and content.get("status") == "stale_generation")
    if stale_error.get("status") != "stale_generation" or _state(ha_token, SAFE_TARGET) != "off":
        raise RuntimeError("stale_generation request was not rejected fail-closed")

    duplicate_id = str(uuid4())
    action = {
        "schema": 1, "op": "action", "room_id": widget_state["room_id"], "panel_id": PANEL_ID,
        "generation": generation, "request_id": duplicate_id, "kind": "entity_control",
        "entity_id": WIDGET_SAFE_ENTITY, "control": "toggle",
    }
    _send_widget_to_device(matrix_env, widget_state, action)
    accepted, cursor = _wait_to_device(user_token, cursor, lambda content: content.get("op") == "result" and content.get("request_id") == duplicate_id)
    if accepted.get("status") != "accepted":
        raise RuntimeError(f"first duplicate test action was not accepted: {accepted}")
    _wait_state(ha_token, SAFE_TARGET, "on")
    _send_widget_to_device(matrix_env, widget_state, action)
    duplicate, _ = _wait_to_device(user_token, cursor, lambda content: content.get("op") == "result" and content.get("request_id") == duplicate_id and content.get("status") == "duplicate_request")
    if duplicate.get("status") != "duplicate_request":
        raise RuntimeError("duplicate_request was not rejected")
    _set_targets_off(ha_token)
    print("Widget backend transport regression ok: subscribe/state, stale_generation, duplicate_request, exact integration_device_id")
    return generation


def _room_url(room_id: str) -> str:
    return f"{ELEMENT_URL}/#/room/{quote(room_id, safe='!:')}"


def _dismiss_optional_dialogs(page: Page) -> None:
    for label in ("Skip", "Not now", "I'll verify later", "Continue without", "Dismiss", "Maybe later", "Ok"):
        try:
            button = page.get_by_role("button", name=re.compile(f"^{re.escape(label)}$", re.I)).first
            if button.is_visible(timeout=250):
                button.click(timeout=1000)
        except PlaywrightTimeoutError:
            pass


def _open_widget(page: Page, room_id: str, *, approve_if_prompted: bool) -> Any:
    page.goto(_room_url(room_id), wait_until="domcontentloaded", timeout=60000)
    page.get_by_text(ROOM_NAME, exact=True).first.wait_for(state="visible", timeout=60000)
    _dismiss_optional_dialogs(page)
    prompt = page.locator(".mx_WidgetCapabilitiesPromptDialog")
    try:
        prompt.wait_for(state="visible", timeout=10000 if approve_if_prompted else 2500)
    except PlaywrightTimeoutError:
        pass
    else:
        if not approve_if_prompted:
            raise RuntimeError("Widget capabilities were unexpectedly forgotten")
        prompt.get_by_role("button", name="Approve").click(timeout=5000)
    selector = 'iframe[src*="127.0.0.1:8090"]'
    page.locator(selector).first.wait_for(state="attached", timeout=60000)
    frame = page.frame_locator(selector).first
    frame.locator(".widget-shell").wait_for(state="visible", timeout=60000)
    frame.locator('.connection-status[data-state="connected"]').wait_for(state="visible", timeout=60000)
    frame.get_by_text(PANEL_TITLE, exact=True).wait_for(state="visible", timeout=30000)
    return frame


def _browser_session(*, restart: bool = False) -> None:
    matrix_env = _read(MATRIX_ENV_PATH)
    token = str(_read(HA_ENV_PATH)["access_token"])
    _set_targets_off(token)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True, viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            frame = _open_widget(page, str(matrix_env["room_id"]), approve_if_prompted=not restart)
            safe = frame.locator(f'button[data-entity="{WIDGET_SAFE_ENTITY}"][data-control="toggle"]')
            safe.wait_for(state="visible", timeout=30000)
            safe.click()
            _wait_state(token, SAFE_TARGET, "on", timeout=30)
            if not restart:
                dangerous = frame.locator(f'button[data-entity="{WIDGET_DANGEROUS_ENTITY}"][data-control="toggle"]')
                dangerous.wait_for(state="visible", timeout=30000)
                dangerous.click()
                dialog = frame.locator('[role="dialog"]')
                dialog.wait_for(state="visible", timeout=30000)
                if _state(token, DANGEROUS_TARGET) != "off":
                    raise RuntimeError("confirmation_required Widget control executed before approval")
                dialog.locator('button[data-confirm="true"]').click()
                _wait_state(token, DANGEROUS_TARGET, "on", timeout=30)
            screenshot = "05-element-widget-after-ha-restart.png" if restart else "04-element-native-widget.png"
            page.screenshot(path=str(SCREENSHOT_DIR / screenshot), full_page=False)
            print("Element Widget restart E2E ok: resubscribed and executed HA action" if restart else "Element Widget E2E ok: capability approval, real iframe, safe action, confirmation_required action and HA state round-trip")
        except Exception:
            page.screenshot(path=str(SCREENSHOT_DIR / ("failure-native-widget-restart.png" if restart else "failure-native-widget-initial.png")), full_page=False)
            raise
        finally:
            context.close()
    _set_targets_off(token)


def _verify_recovery() -> None:
    matrix_env = _read(MATRIX_ENV_PATH)
    widget_state = _read(WIDGET_STATE_PATH)
    ha_token = str(_read(HA_ENV_PATH)["access_token"])
    user_token = str(matrix_env["user_access_token"])
    _wait_state(ha_token, SAFE_TARGET, "off", timeout=30)
    snapshot, cursor = _subscribe_snapshot(matrix_env, widget_state)
    generation = int(snapshot["generation"])
    entities = {item.get("entity_id"): item for item in snapshot.get("entities", []) if isinstance(item, dict)}
    safe = entities.get(WIDGET_SAFE_ENTITY)
    if not isinstance(safe, dict) or safe.get("state") != "off":
        raise RuntimeError(f"recovered Widget snapshot is not current: {safe}")

    deadline = time.monotonic() + 2.5
    extra_states = 0
    while time.monotonic() < deadline:
        response = _sync(user_token, cursor, 700)
        cursor = str(response["next_batch"])
        for event in response.get("to_device", {}).get("events", []):
            if event.get("type") == WIDGET_EVENT_TYPE and event.get("content", {}).get("op") == "state":
                extra_states += 1
    if extra_states:
        raise RuntimeError(f"Widget recovery snapshot storm detected: {extra_states} extra states")

    stale_id = str(uuid4())
    _send_widget_to_device(matrix_env, widget_state, {
        "schema": 1, "op": "action", "room_id": widget_state["room_id"], "panel_id": PANEL_ID,
        "generation": generation - 1, "request_id": stale_id, "kind": "entity_control",
        "entity_id": WIDGET_SAFE_ENTITY, "control": "toggle",
    })
    error, _ = _wait_to_device(user_token, cursor, lambda content: content.get("op") == "error" and content.get("status") == "stale_generation")
    if error.get("status") != "stale_generation" or _state(ha_token, SAFE_TARGET) != "off":
        raise RuntimeError("stale Widget action executed after reconnect")
    print("Widget recovery ok: one current snapshot, no replay storm, stale action rejected")


def main() -> int:
    modes = {"configure", "verify", "verify-recovery", "verify-restart"}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print("usage: widget-e2e.py {configure|verify|verify-recovery|verify-restart}", file=sys.stderr)
        return 2
    mode = sys.argv[1]
    if mode == "configure":
        _configure_widget(); _backend_transport_regression()
    elif mode == "verify":
        _browser_session(restart=False)
    elif mode == "verify-recovery":
        _verify_recovery()
    else:
        _browser_session(restart=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
