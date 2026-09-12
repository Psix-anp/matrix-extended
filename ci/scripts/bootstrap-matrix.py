#!/usr/bin/env python3
"""Bootstrap disposable Matrix users and an encrypted room for E2E tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RequestFn = Callable[..., dict[str, Any]]


def _registration_mac(
    *, nonce: str, username: str, password: str, shared_secret: str, admin: bool = False
) -> str:
    mac = hmac.new(shared_secret.encode(), digestmod=hashlib.sha1)
    for value in (nonce, username, password):
        mac.update(value.encode())
        mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    return mac.hexdigest()


def make_http_request(homeserver: str) -> RequestFn:
    base = homeserver.rstrip("/")

    def request(
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = Request(base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=20) as response:
                raw = response.read()
        except HTTPError as err:
            raise RuntimeError(f"Matrix request failed: {method} {path} -> HTTP {err.code}") from err
        except URLError as err:
            raise RuntimeError(f"Matrix request failed: {method} {path} -> connection error") from err
        return json.loads(raw or b"{}")

    return request


def _register_user(
    request: RequestFn,
    *,
    username: str,
    password: str,
    shared_secret: str,
) -> dict[str, Any]:
    nonce = request("GET", "/_synapse/admin/v1/register")["nonce"]
    body = {
        "nonce": nonce,
        "username": username,
        "password": password,
        "admin": False,
        "mac": _registration_mac(
            nonce=nonce,
            username=username,
            password=password,
            shared_secret=shared_secret,
        ),
    }
    return request("POST", "/_synapse/admin/v1/register", json_body=body)


def bootstrap_matrix(
    *,
    request: RequestFn,
    homeserver: str,
    server_name: str,
    shared_secret: str,
    bot_password: str,
    user_password: str,
    output_path: Path,
) -> dict[str, str]:
    """Create test users and one encrypted room without logging credentials."""
    bot = _register_user(
        request,
        username="ha_bot",
        password=bot_password,
        shared_secret=shared_secret,
    )
    user = _register_user(
        request,
        username="ha_user",
        password=user_password,
        shared_secret=shared_secret,
    )

    alias_localpart = "matrix-extended-e2e"
    room_alias = f"#{alias_localpart}:{server_name}"
    room = request(
        "POST",
        "/_matrix/client/v3/createRoom",
        token=bot["access_token"],
        json_body={
            "room_alias_name": alias_localpart,
            "visibility": "private",
            "preset": "private_chat",
            "name": "Matrix Extended E2E",
            "initial_state": [
                {
                    "type": "m.room.encryption",
                    "state_key": "",
                    "content": {"algorithm": "m.megolm.v1.aes-sha2"},
                }
            ],
        },
    )
    room_id = room["room_id"]
    request(
        "POST",
        f"/_matrix/client/v3/rooms/{room_id}/invite",
        token=bot["access_token"],
        json_body={"user_id": user["user_id"]},
    )
    request(
        "POST",
        f"/_matrix/client/v3/join/{room_id}",
        token=user["access_token"],
        json_body={},
    )

    result = {
        "homeserver": homeserver,
        "bot_user_id": bot["user_id"],
        "bot_access_token": bot["access_token"],
        "user_user_id": user["user_id"],
        "user_access_token": user["access_token"],
        "room_id": room_id,
        "room_alias": room_alias,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n")
    output_path.chmod(0o600)
    print(f"Matrix bootstrap ready: bot={bot['user_id']} user={user['user_id']} room={room_id}")
    return result


def write_password_bundle(path: Path, *, bot_password: str, user_password: str) -> None:
    """Persist disposable Matrix passwords for the HA E2E step without logging them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"bot_password": bot_password, "user_password": user_password},
            indent=2,
        )
        + "\n"
    )
    path.chmod(0o600)


def main() -> int:
    homeserver = os.environ.get("MATRIX_HOMESERVER", "http://127.0.0.1:8008")
    server_name = os.environ.get("MATRIX_SERVER_NAME", "matrix.test")
    shared_secret = os.environ.get("MATRIX_REGISTRATION_SHARED_SECRET")
    if not shared_secret:
        print("MATRIX_REGISTRATION_SHARED_SECRET is required", file=sys.stderr)
        return 2
    output = Path(os.environ.get("MATRIX_ENV_OUTPUT", ".ci/matrix-env.json"))
    password_output = Path(
        os.environ.get("MATRIX_PASSWORD_OUTPUT", ".ci/matrix-passwords.json")
    )
    bot_password = os.environ.get("MATRIX_BOT_PASSWORD", secrets.token_urlsafe(24))
    user_password = os.environ.get("MATRIX_USER_PASSWORD", secrets.token_urlsafe(24))
    write_password_bundle(
        password_output, bot_password=bot_password, user_password=user_password
    )
    bootstrap_matrix(
        request=make_http_request(homeserver),
        homeserver=homeserver,
        server_name=server_name,
        shared_secret=shared_secret,
        bot_password=bot_password,
        user_password=user_password,
        output_path=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
