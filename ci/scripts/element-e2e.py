#!/usr/bin/env python3
"""Exercise a real Element Web session against the disposable Matrix stack."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

ELEMENT_URL = os.environ.get("ELEMENT_URL", "http://127.0.0.1:8080").rstrip("/")
PROFILE_DIR = Path(os.environ.get("ELEMENT_PROFILE_DIR", ".ci/element-profile"))
SCREENSHOT_DIR = Path(os.environ.get("ELEMENT_SCREENSHOT_DIR", ".ci/screenshots"))
ROOM_NAME = "Matrix Extended E2E"
MESSAGE_RE = re.compile(r"matrix-extended-ha-e2e-[0-9a-f]+")
LOCATION_TEXT = "Matrix Extended E2E Location"
VOICE_TEXT = "Matrix Extended E2E Voice"


def _state() -> tuple[dict[str, str], dict[str, str]]:
    matrix_env = json.loads(Path(".ci/matrix-env.json").read_text())
    passwords = json.loads(Path(".ci/matrix-passwords.json").read_text())
    return matrix_env, passwords


def _room_url(room_id: str) -> str:
    return f"{ELEMENT_URL}/#/room/{quote(room_id, safe='!:')}"


def _dismiss_optional_dialogs(page: Page) -> None:
    for label in (
        "Skip",
        "Not now",
        "I'll verify later",
        "Continue without",
        "Dismiss",
        "Maybe later",
        "Ok",
    ):
        try:
            button = page.get_by_role("button", name=re.compile(f"^{re.escape(label)}$", re.I)).first
            if button.is_visible(timeout=300):
                button.click(timeout=1000)
        except PlaywrightTimeoutError:
            pass


def _prepare_showcase_screenshot(page: Page) -> None:
    """Remove CI-only visual noise without changing the crypto test itself."""
    _dismiss_optional_dialogs(page)
    map_error = page.get_by_text("Unable to load map", exact=False).first
    try:
        map_error.wait_for(state="hidden", timeout=30000)
    except PlaywrightTimeoutError as err:
        raise RuntimeError("Element location map did not finish loading") from err
    page.add_style_tag(
        content=".mx_EventTile_e2eIcon_warning { display: none !important; }"
    )
    page.wait_for_timeout(500)


def _username_input(page: Page):
    return page.locator(
        'input[name="username"], #mx_Login_field_username, input[autocomplete="username"]'
    ).first


def _password_input(page: Page):
    return page.locator(
        'input[name="password"], #mx_Login_field_password, input[autocomplete="current-password"]'
    ).first


def _login(page: Page, user_id: str, password: str) -> None:
    page.goto(f"{ELEMENT_URL}/#/login", wait_until="domcontentloaded", timeout=60000)
    username = _username_input(page)
    try:
        username.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        sign_in = page.get_by_role("link", name=re.compile(r"sign in|log in", re.I)).first
        if not sign_in.is_visible(timeout=1000):
            sign_in = page.get_by_role("button", name=re.compile(r"sign in|log in", re.I)).first
        sign_in.click(timeout=5000)
        username.wait_for(state="visible", timeout=15000)

    username.fill(user_id)
    password_input = _password_input(page)
    password_input.wait_for(state="visible", timeout=10000)
    password_input.fill(password)
    submit = page.locator('button[type="submit"]').first
    if not submit.is_visible(timeout=1000):
        submit = page.get_by_role("button", name=re.compile(r"sign in|log in", re.I)).first
    submit.click(timeout=5000)
    page.get_by_text(ROOM_NAME, exact=True).first.wait_for(state="visible", timeout=60000)
    _dismiss_optional_dialogs(page)


def _open_room(page: Page, room_id: str) -> None:
    page.goto(_room_url(room_id), wait_until="domcontentloaded", timeout=60000)
    page.get_by_text(ROOM_NAME, exact=True).first.wait_for(state="visible", timeout=60000)
    _dismiss_optional_dialogs(page)


def _message(page: Page):
    return page.get_by_text(MESSAGE_RE).last


def _screenshot(page: Page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / name), full_page=False)


def _send_rich_from_ha() -> None:
    subprocess.run(
        [sys.executable, "ci/scripts/ha-e2e.py", "send-rich"],
        check=True,
    )


def run(mode: str) -> None:
    matrix_env, passwords = _state()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=1,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            if mode == "login":
                _login(page, matrix_env["user_user_id"], passwords["user_password"])
                _open_room(page, matrix_env["room_id"])
                _screenshot(page, "01-element-encrypted-room-ready.png")
                print("Element E2E recipient device is logged in and room is ready")
                return

            _open_room(page, matrix_env["room_id"])
            message = _message(page)
            message.wait_for(state="visible", timeout=60000)
            message.scroll_into_view_if_needed()

            if mode == "verify-message-rich":
                _screenshot(page, "02-element-decrypted-ha-message.png")
                print("Element decrypted the Home Assistant E2EE message")

                # Keep this authenticated Element/crypto session alive while HA sends
                # the rich events. Reopening the same persistent browser profile a
                # third time proved unreliable in CI even though Matrix delivery was
                # already successful.
                _send_rich_from_ha()

                location = page.get_by_text(
                    re.compile(rf"{re.escape(LOCATION_TEXT)}$")
                ).last
                location.wait_for(state="visible", timeout=60000)
                location.scroll_into_view_if_needed()
                voice = page.locator(".mx_MVoiceMessageBody").last
                voice.wait_for(state="visible", timeout=60000)
                voice.scroll_into_view_if_needed()
                page.wait_for_timeout(1000)
                _prepare_showcase_screenshot(page)
                _screenshot(page, "03-element-location-and-voice.png")
                voice_text = page.get_by_text(VOICE_TEXT, exact=True).last
                if voice_text.count() and voice_text.is_visible(timeout=1000):
                    print("Element rendered native voice with the E2E caption")
                print("Element rendered encrypted Matrix location and native voice")
                return

            raise ValueError(f"unknown mode: {mode}")
        except Exception:
            _screenshot(page, f"failure-{mode}.png")
            raise
        finally:
            context.close()


def main() -> int:
    modes = {"login", "verify-message-rich"}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        print(
            "usage: element-e2e.py {login|verify-message-rich}",
            file=sys.stderr,
        )
        return 2
    run(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
