from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from contextlib import redirect_stdout

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "bootstrap-matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("matrix_bootstrap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, *, token=None, json_body=None):
        self.calls.append((method, path, token, json_body))
        if path == "/_synapse/admin/v1/register":
            if method == "GET":
                return {"nonce": "nonce-1"}
            username = json_body["username"]
            return {
                "user_id": f"@{username}:matrix.test",
                "access_token": f"secret-{username}-token",
            }
        if path == "/_matrix/client/v3/createRoom":
            assert token == "secret-ha_bot-token"
            assert json_body["initial_state"] == [
                {
                    "type": "m.room.encryption",
                    "state_key": "",
                    "content": {"algorithm": "m.megolm.v1.aes-sha2"},
                }
            ]
            return {"room_id": "!room:matrix.test"}
        if path == "/_matrix/client/v3/rooms/!room:matrix.test/invite":
            assert token == "secret-ha_bot-token"
            assert json_body == {"user_id": "@ha_user:matrix.test"}
            return {}
        if path == "/_matrix/client/v3/join/!room:matrix.test":
            assert token == "secret-ha_user-token"
            return {"room_id": "!room:matrix.test"}
        raise AssertionError(f"unexpected request: {method} {path}")


def test_bootstrap_contract_and_no_secret_output(tmp_path):
    module = _load_module()
    transport = FakeTransport()
    out = io.StringIO()
    with redirect_stdout(out):
        result = module.bootstrap_matrix(
            request=transport,
            homeserver="http://127.0.0.1:8008",
            server_name="matrix.test",
            shared_secret="registration-secret",
            bot_password="bot-password",
            user_password="user-password",
            output_path=tmp_path / "matrix-env.json",
        )

    assert set(result) == {
        "homeserver",
        "bot_user_id",
        "bot_access_token",
        "user_user_id",
        "user_access_token",
        "room_id",
        "room_alias",
    }
    assert result["room_id"] == "!room:matrix.test"
    assert result["room_alias"] == "#matrix-extended-e2e:matrix.test"
    text = out.getvalue()
    assert "secret-ha_bot-token" not in text
    assert "secret-ha_user-token" not in text
    assert "bot-password" not in text
    assert "user-password" not in text

    saved = (tmp_path / "matrix-env.json").read_text()
    assert "secret-ha_bot-token" in saved
    assert (tmp_path / "matrix-env.json").stat().st_mode & 0o777 == 0o600


def test_password_bundle_is_private(tmp_path):
    module = _load_module()
    path = tmp_path / "matrix-passwords.json"
    module.write_password_bundle(path, bot_password="bot-pass", user_password="user-pass")
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_text() == '{\n  "bot_password": "bot-pass",\n  "user_password": "user-pass"\n}\n'
