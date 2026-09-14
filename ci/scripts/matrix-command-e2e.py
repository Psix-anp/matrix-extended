#!/usr/bin/env python3
"""Exercise v0.5.1 Matrix -> HA paths against the disposable encrypted room."""

from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nio import (
    AsyncClient,
    AsyncClientConfig,
    LoginResponse,
    RoomSendResponse,
    UploadResponse,
)

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
VOICE_PATH = Path(".ci/ha-config/matrix-e2e-media/matrix-e2e-voice.wav")
RESULT_PATH = Path(".ci/v051-e2e.json")


def _request_json(
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
    req = Request(HA_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        body = err.read().decode(errors="replace")[:1000]
        raise RuntimeError(f"HA HTTP {err.code} for {method} {path}: {body}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"HA request failed for {method} {path}: {type(err).__name__}") from err
    return json.loads(raw or b"{}")


def _state(token: str, entity_id: str) -> str:
    value = _request_json("GET", f"/api/states/{entity_id}", token=token)
    return str(value.get("state"))


def _wait_state(
    token: str, entity_id: str, expected: str, *, timeout: float = 30
) -> None:
    deadline = time.monotonic() + timeout
    last = "missing"
    while time.monotonic() < deadline:
        try:
            last = _state(token, entity_id)
        except RuntimeError:
            time.sleep(0.5)
            continue
        if last == expected:
            return
        time.sleep(0.5)
    raise TimeoutError(f"{entity_id} did not reach {expected}; last_state={last}")


def _service(token: str, domain: str, service: str, data: dict[str, Any]) -> Any:
    return _request_json(
        "POST",
        f"/api/services/{domain}/{service}",
        token=token,
        json_body=data,
        timeout=60,
    )


def _configure_voice_options(
    token: str, entry_id: str, matrix_env: dict[str, str]
) -> None:
    flow = _request_json(
        "POST",
        "/api/config/config_entries/options/flow",
        token=token,
        json_body={"handler": entry_id},
    )
    if flow.get("type") != "form":
        raise RuntimeError(f"unexpected Matrix options flow start: {flow}")
    result = _request_json(
        "POST",
        f"/api/config/config_entries/options/flow/{flow['flow_id']}",
        token=token,
        json_body={
            "require_e2ee": True,
            "incoming_enabled": True,
            "allowed_users": [matrix_env["user_user_id"]],
            "allowed_rooms": [matrix_env["room_id"]],
            "download_incoming_media": True,
            "incoming_media_retention_days": 7,
            "incoming_media_max_mb": 256,
            "routing_profiles": {},
            "voice_assist_enabled": True,
            "voice_assist_stt_entity": "stt.demo_stt",
            "voice_assist_language": "en",
            "voice_assist_reply_mode": "text",
            "voice_assist_allowed_users": [matrix_env["user_user_id"]],
            "voice_assist_allowed_rooms": [matrix_env["room_id"]],
        },
        timeout=60,
    )
    if result.get("type") != "create_entry":
        raise RuntimeError(f"Matrix options flow failed: {result}")
    _request_json(
        "POST",
        f"/api/config/config_entries/entry/{entry_id}/reload",
        token=token,
        json_body={},
        timeout=60,
    )


def _register_commands(token: str, matrix_env: dict[str, str]) -> None:
    common = {
        "allowed_users": [matrix_env["user_user_id"]],
        "allowed_rooms": [matrix_env["room_id"]],
        "progress": True,
    }
    _service(
        token,
        "matrix_extended",
        "register_command",
        {
            "id": "e2e_command",
            "trigger": "test switch on",
            "handler_type": "service",
            "service": "input_boolean.turn_on",
            "target": {"entity_id": "input_boolean.matrix_command_target"},
            **common,
        },
    )
    _service(
        token,
        "matrix_extended",
        "register_command",
        {
            "id": "e2e_denied",
            "trigger": "denied switch on",
            "handler_type": "service",
            "service": "input_boolean.turn_on",
            "target": {"entity_id": "input_boolean.matrix_denied_target"},
            "allowed_users": ["@nobody:matrix.test"],
            "allowed_rooms": [matrix_env["room_id"]],
            "progress": True,
        },
    )
    _service(
        token,
        "matrix_extended",
        "register_command",
        {
            "id": "e2e_camera",
            "trigger": "camera e2e",
            "handler_type": "camera_snapshot",
            "entity_id": "camera.demo_camera",
            "caption": "Matrix Extended E2E camera",
            **common,
        },
    )


async def _send_text(client: AsyncClient, room_id: str, body: str) -> str:
    response = await client.room_send(
        room_id,
        "m.room.message",
        {"msgtype": "m.text", "body": body},
        tx_id=secrets.token_hex(8),
        ignore_unverified_devices=True,
    )
    if not isinstance(response, RoomSendResponse):
        raise RuntimeError(f"encrypted Matrix send failed: {response}")
    return response.event_id


async def _send_voice(client: AsyncClient, room_id: str) -> str:
    audio = VOICE_PATH.read_bytes()
    upload, encrypted_file = await client.upload(
        io.BytesIO(audio),
        content_type="audio/wav",
        filename="matrix-e2e-inbound-voice.wav",
        encrypt=True,
        filesize=len(audio),
    )
    if not isinstance(upload, UploadResponse) or not encrypted_file:
        raise RuntimeError(f"encrypted voice upload failed: {upload}")
    file_info = dict(encrypted_file)
    file_info["url"] = upload.content_uri
    response = await client.room_send(
        room_id,
        "m.room.message",
        {
            "msgtype": "m.audio",
            "body": "matrix-e2e-inbound-voice.wav",
            "info": {
                "mimetype": "audio/wav",
                "size": len(audio),
                "duration": 600,
            },
            "file": file_info,
            "org.matrix.msc3245.voice": {},
            "org.matrix.msc1767.audio": {"duration": 600},
        },
        tx_id=secrets.token_hex(8),
        ignore_unverified_devices=True,
    )
    if not isinstance(response, RoomSendResponse):
        raise RuntimeError(f"encrypted Matrix voice send failed: {response}")
    return response.event_id


def _content(event: Any) -> dict[str, Any]:
    source = getattr(event, "source", {})
    if not isinstance(source, dict):
        return {}
    content = source.get("content", {})
    return content if isinstance(content, dict) else {}


async def _wait_bot_event(
    client: AsyncClient,
    *,
    room_id: str,
    bot_user_id: str,
    predicate: Callable[[dict[str, Any], Any], bool],
    description: str,
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sync = await client.sync(timeout=3000)
        room = sync.rooms.join.get(room_id)
        if room is None:
            continue
        for event in room.timeline.events:
            if getattr(event, "sender", None) != bot_user_id:
                continue
            content = _content(event)
            if predicate(content, event):
                return
    raise TimeoutError(f"did not observe decrypted bot event: {description}")


async def _exercise() -> None:
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    passwords = json.loads(Path(".ci/matrix-passwords.json").read_text())
    ha_env = json.loads(Path(".ci/ha-env.json").read_text())
    ha_token = ha_env["access_token"]
    entry_id = ha_env["entry_id"]

    # The built-in pinned HA demo integration supplies deterministic camera/STT
    # entities without adding test code to Matrix Extended itself.
    _wait_state(ha_token, "camera.demo_camera", "idle", timeout=60)
    _wait_state(ha_token, "stt.demo_stt", "unknown", timeout=60)

    _register_commands(ha_token, matrix_env)
    _configure_voice_options(ha_token, entry_id, matrix_env)

    _service(
        ha_token,
        "input_boolean",
        "turn_off",
        {"entity_id": [
            "input_boolean.matrix_command_target",
            "input_boolean.matrix_denied_target",
        ]},
    )
    _service(ha_token, "light", "turn_off", {"entity_id": "light.kitchen_lights"})
    _wait_state(ha_token, "input_boolean.matrix_command_target", "off")
    _wait_state(ha_token, "input_boolean.matrix_denied_target", "off")
    _wait_state(ha_token, "light.kitchen_lights", "off")

    store = Path(".ci/nio-v051-sender")
    store.mkdir(parents=True, exist_ok=True)
    client = AsyncClient(
        matrix_env["homeserver"],
        matrix_env["user_user_id"],
        store_path=str(store),
        config=AsyncClientConfig(
            encryption_enabled=True,
            store_sync_tokens=True,
        ),
    )
    try:
        login = await client.login(
            passwords["user_password"],
            device_name="Matrix Extended v0.5.1 E2E",
        )
        if not isinstance(login, LoginResponse):
            raise RuntimeError(f"Matrix E2E sender login failed: {login}")
        await client.sync(timeout=3000, full_state=True)
        room = client.rooms.get(matrix_env["room_id"])
        if room is None or not room.encrypted:
            raise RuntimeError("Matrix E2E room is not loaded as encrypted")

        await _send_text(client, matrix_env["room_id"], "!test switch on")
        _wait_state(ha_token, "input_boolean.matrix_command_target", "on", timeout=30)
        await _wait_bot_event(
            client,
            room_id=matrix_env["room_id"],
            bot_user_id=matrix_env["bot_user_id"],
            predicate=lambda content, _event: (
                isinstance(content.get("m.new_content"), dict)
                and content["m.new_content"].get("body") == "✅ Done"
            ),
            description="safe-command progress edit",
        )

        await _send_text(client, matrix_env["room_id"], "!denied switch on")
        await asyncio.sleep(3)
        if _state(ha_token, "input_boolean.matrix_denied_target") != "off":
            raise RuntimeError("command-specific user allowlist did not fail closed")

        await _send_text(client, matrix_env["room_id"], "!camera e2e")
        await _wait_bot_event(
            client,
            room_id=matrix_env["room_id"],
            bot_user_id=matrix_env["bot_user_id"],
            predicate=lambda content, _event: content.get("msgtype") == "m.image",
            description="encrypted camera snapshot",
            timeout=40,
        )

        await _send_voice(client, matrix_env["room_id"])
        _wait_state(ha_token, "light.kitchen_lights", "on", timeout=45)
        await _wait_bot_event(
            client,
            room_id=matrix_env["room_id"],
            bot_user_id=matrix_env["bot_user_id"],
            predicate=lambda content, _event: (
                content.get("msgtype") == "m.text"
                and bool(str(content.get("body") or "").strip())
                and content.get("m.relates_to", {}).get("rel_type") != "m.replace"
            ),
            description="automatic Voice Assist text reply",
            timeout=45,
        )
    finally:
        await client.close()

    RESULT_PATH.write_text(
        json.dumps(
            {
                "safe_command": "ok",
                "unauthorized_command": "blocked",
                "camera_snapshot": "ok",
                "voice_assist": "ok",
            },
            indent=2,
        )
        + "\n"
    )
    print("v0.5.1 encrypted command/camera/Voice Assist E2E verified")


def main() -> int:
    asyncio.run(_exercise())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
