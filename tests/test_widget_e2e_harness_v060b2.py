from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import types
from urllib.error import HTTPError

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "ci" / "scripts" / "widget-e2e.py"


def _load_widget_e2e():
    playwright = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.Page = object
    sync_api.TimeoutError = TimeoutError
    sync_api.sync_playwright = lambda: None
    playwright.sync_api = sync_api
    sys.modules.setdefault("playwright", playwright)
    sys.modules.setdefault("playwright.sync_api", sync_api)

    spec = importlib.util.spec_from_file_location("widget_e2e_harness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_request_json_retries_matrix_429_using_retry_after_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_widget_e2e()
    calls = 0
    sleeps: list[float] = []

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"errcode":"M_LIMIT_EXCEEDED","retry_after_ms":25}'),
            )
        return _Response(b'{"ok":true}')

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", sleeps.append)

    result = module._request_json("http://matrix.test", "PUT", "/state/widget", json_body={"id": "widget"})

    assert result == {"ok": True}
    assert calls == 2
    assert sleeps == [0.025]


def test_request_json_keeps_non_rate_limit_http_errors_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_widget_e2e()
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"errcode":"M_FORBIDDEN"}'),
        )

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=r"HTTP 403 for PUT /state/widget"):
        module._request_json("http://matrix.test", "PUT", "/state/widget", json_body={"id": "widget"})

    assert calls == 1
