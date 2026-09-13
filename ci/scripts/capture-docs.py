#!/usr/bin/env python3
"""Create a disposable Matrix Extended HA fixture and capture real UI screenshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HA_URL = os.environ.get("HA_URL", "http://127.0.0.1:8123").rstrip("/")
MATRIX_HA_URL = os.environ.get("MATRIX_HA_URL", "http://synapse:8008").rstrip("/")
CLIENT_ID = f"{HA_URL}/"
AUTH_FILE = Path(".ci/docs-auth.json")
IMAGE_DIR = Path("docs/images")


def request_json(
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
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        data = urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(HA_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except HTTPError as err:
        body = err.read().decode(errors="replace")[:1200]
        raise RuntimeError(f"HTTP {err.code} for {method} {path}: {body}") from err
    except (URLError, OSError) as err:
        raise RuntimeError(f"connection error for {method} {path}: {err}") from err


def wait_matrix_entry_loaded(token: str, timeout: float = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = "missing"
    while time.monotonic() < deadline:
        entries = request_json("GET", "/api/config/config_entries/entry", token=token)
        if isinstance(entries, dict):
            entries = entries.get("result", entries.get("entries", []))
        for entry in entries:
            if entry.get("domain") == "matrix_extended":
                last = str(entry.get("state"))
                if last == "loaded":
                    return entry
        time.sleep(0.5)
    raise TimeoutError(f"Matrix Extended entry did not load; last_state={last}")


def setup_fixture() -> None:
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    matrix_passwords = json.loads(Path(".ci/matrix-passwords.json").read_text())
    username = "matrix-docs-admin"
    password = secrets.token_urlsafe(24)

    onboarding = request_json(
        "POST",
        "/api/onboarding/users",
        json_body={
            "name": "Matrix Extended Demo",
            "username": username,
            "password": password,
            "client_id": CLIENT_ID,
            "language": "ru",
        },
    )
    token_data = request_json(
        "POST",
        "/auth/token",
        form_body={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": onboarding["auth_code"],
        },
    )
    token = token_data["access_token"]

    flow = request_json(
        "POST",
        "/api/config/config_entries/flow",
        token=token,
        json_body={"handler": "matrix_extended"},
    )
    result = request_json(
        "POST",
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        token=token,
        json_body={
            "homeserver": MATRIX_HA_URL,
            "user_id": matrix_env["bot_user_id"],
            "password": matrix_passwords["bot_password"],
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
        raise RuntimeError(f"Matrix config flow failed: {result}")
    entry = wait_matrix_entry_loaded(token)

    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(
        json.dumps(
            {
                "username": username,
                "password": password,
                "access_token": token,
                "entry_id": entry["entry_id"],
            },
            indent=2,
        )
        + "\n"
    )
    AUTH_FILE.chmod(0o600)
    print(f"Documentation fixture ready: entry={entry['entry_id']}")


def _login(page: Any, username: str, password: str) -> None:
    page.goto(f"{HA_URL}/?storeToken=true", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    if "/auth/" not in page.url:
        return

    user = page.locator('input[name="username"]')
    pwd = page.locator('input[name="password"]')
    if user.count() == 0:
        user = page.locator('input[type="text"]').first
    if pwd.count() == 0:
        pwd = page.locator('input[type="password"]').first
    user.fill(username)
    pwd.fill(password)

    submit = page.locator('button[type="submit"]')
    if submit.count() == 0:
        submit = page.get_by_role("button", name=re.compile("log in|войти", re.I))
    submit.first.click()
    page.wait_for_url(re.compile(r"^http://127\.0\.0\.1:8123/(?!auth/)"), timeout=30000)
    page.wait_for_timeout(1500)


def _shot(page: Any, name: str, *, full_page: bool = False) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(IMAGE_DIR / name), full_page=full_page)
    print(f"captured {name}: {page.url}")


def _fill_first_search(page: Any, text: str) -> bool:
    candidates = [
        page.get_by_placeholder(re.compile("search|поиск", re.I)),
        page.locator('input[type="search"]'),
    ]
    for candidate in candidates:
        if candidate.count():
            candidate.first.fill(text)
            page.wait_for_timeout(1200)
            return True
    return False


def capture() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as err:  # pragma: no cover - CI dependency guard
        raise RuntimeError("playwright is required for documentation capture") from err

    auth = json.loads(AUTH_FILE.read_text())
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            locale="ru-RU",
            color_scheme="dark",
            device_scale_factor=1,
        )
        page = context.new_page()
        _login(page, auth["username"], auth["password"])

        # Integration overview: the screenshot must contain the real integration card.
        page.goto(f"{HA_URL}/config/integrations", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        matrix = page.get_by_text("Matrix Extended", exact=False)
        if matrix.count() == 0:
            raise RuntimeError("Matrix Extended card was not rendered on integrations page")
        matrix.first.scroll_into_view_if_needed()
        _shot(page, "matrix-extended-integrations.png")

        # Integration detail page with the live config entry and status.
        page.goto(
            f"{HA_URL}/config/integrations/integration/matrix_extended",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(2200)
        _shot(page, "matrix-extended-entry.png")

        # Options flow: security/E2EE/allowlist/routing fields rendered by HA itself.
        configure = page.get_by_role(
            "button", name=re.compile("configure|настроить|параметры", re.I)
        )
        if configure.count():
            configure.first.click()
            page.wait_for_timeout(1800)
            _shot(page, "matrix-extended-options.png")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # Entity registry: diagnostics and room/default-room entities from this integration.
        page.goto(f"{HA_URL}/config/entities", wait_until="domcontentloaded")
        page.wait_for_timeout(2200)
        _fill_first_search(page, "Matrix")
        _shot(page, "matrix-extended-entities.png")

        # The real setup form, useful for README/HACS installation documentation.
        page.goto(
            f"{HA_URL}/config/integrations/dashboard/add?domain=matrix_extended",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(2200)
        _shot(page, "matrix-extended-config-flow.png")

        browser.close()

    images = sorted(IMAGE_DIR.glob("matrix-extended-*.png"))
    if len(images) < 4:
        raise RuntimeError(f"expected at least 4 documentation screenshots, got {len(images)}")
    print(f"Documentation capture complete: {len(images)} screenshots")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"setup", "capture"}:
        print("usage: capture-docs.py {setup|capture}", file=sys.stderr)
        return 2
    if sys.argv[1] == "setup":
        setup_fixture()
    else:
        capture()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
