from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "wait-http.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("wait_http", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_wait_retries_transient_connection_reset(monkeypatch):
    module = _load_module()
    attempts = iter([ConnectionResetError(104, "reset by peer"), _Response()])

    def fake_urlopen(url, timeout=5):
        result = next(attempts)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    module.wait("http://127.0.0.1:8008/_matrix/client/versions", timeout=1, interval=0)
