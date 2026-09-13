#!/usr/bin/env python3
"""Send real Matrix Extended messages for documentation screenshots."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HA_URL = "http://127.0.0.1:8123"
CLIENT_ID = f"{HA_URL}/"


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: Any | None = None,
    form_body: dict[str, str] | None = None,
    timeout: float = 30,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode()
    elif form_body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(form_body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(HA_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as err:
        body = err.read().decode(errors="replace")[:1200]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {body}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"connection error for {method} {path}: {err}") from err
    return json.loads(raw or b"{}")


def ha_access_token(username: str, password: str) -> str:
    flow = request(
        "POST",
        "/auth/login_flow",
        json_body={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
        },
    )
    result = request(
        "POST",
        f"/auth/login_flow/{flow['flow_id']}",
        json_body={
            "client_id": CLIENT_ID,
            "username": username,
            "password": password,
        },
    )
    auth_code = result.get("result")
    if not auth_code:
        raise RuntimeError(f"Home Assistant login did not return auth code: {result}")
    token = request(
        "POST",
        "/auth/token",
        form_body={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": auth_code,
        },
    )
    return str(token["access_token"])


def send(token: str, payload: dict[str, Any]) -> None:
    request(
        "POST",
        "/api/services/matrix_extended/send",
        token=token,
        json_body=payload,
        timeout=60,
    )


def main() -> int:
    auth = json.loads(Path(".ci/docs-auth.json").read_text())
    matrix = json.loads(Path(".ci/matrix-env.json").read_text())
    token = ha_access_token(auth["username"], auth["password"])
    room_id = matrix["room_id"]

    # Give the integration one sync cycle to discover the newly logged-in
    # Element X device before the first encrypted documentation message.
    time.sleep(5)

    send(
        token,
        {
            "target": [room_id],
            "message": "🔐 Matrix Extended — E2EE активно",
        },
    )
    send(
        token,
        {
            "target": [room_id],
            "message": "🚪 Входная дверь открыта\nДом • уведомление Home Assistant",
            "actions": [
                {
                    "reaction": "✅",
                    "service": "counter.increment",
                    "target": {"entity_id": "counter.matrix_reaction"},
                }
            ],
        },
    )
    send(
        token,
        {
            "target": [room_id],
            "message": "📦 Резервная копия: 20%",
            "notification_key": "docs-backup-progress",
        },
    )
    time.sleep(1)
    send(
        token,
        {
            "target": [room_id],
            "message": "📦 Резервная копия: 100% — готово",
            "notification_key": "docs-backup-progress",
        },
    )
    send(
        token,
        {
            "target": [room_id],
            "media": [
                {
                    "url": "http://127.0.0.1:8123/local/matrix-demo-image.jpg",
                    "type": "image",
                    "filename": "front-door.jpg",
                    "caption": "📷 Снимок с камеры",
                    "width": 640,
                    "height": 360,
                }
            ],
        },
    )
    send(
        token,
        {
            "target": [room_id],
            "media": [
                {
                    "url": "http://127.0.0.1:8123/local/matrix-demo-video.mp4",
                    "type": "video",
                    "filename": "front-door.mp4",
                    "caption": "🎬 Видео с камеры",
                    "width": 640,
                    "height": 360,
                    "duration_ms": 3000,
                    "thumbnail": {
                        "url": "http://127.0.0.1:8123/local/matrix-demo-image.jpg",
                        "type": "image",
                        "filename": "front-door-preview.jpg",
                        "width": 640,
                        "height": 360,
                    },
                }
            ],
        },
    )
    send(
        token,
        {
            "target": [room_id],
            "media": [
                {
                    "url": "http://127.0.0.1:8123/local/matrix-demo-voice.ogg",
                    "type": "audio",
                    "filename": "voice.ogg",
                    "caption": "🎙️ Голосовое сообщение",
                    "duration_ms": 3100,
                    "voice": True,
                    "waveform": [
                        80,
                        160,
                        260,
                        420,
                        680,
                        920,
                        720,
                        480,
                        300,
                        180,
                        120,
                        240,
                        460,
                        760,
                        1024,
                        860,
                        620,
                        400,
                        220,
                        140,
                        200,
                        360,
                        580,
                        840,
                        700,
                        500,
                        320,
                        180,
                        120,
                        80,
                    ],
                }
            ],
        },
    )
    print("Documentation text, image, video, and native voice messages sent through matrix_extended.send")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
