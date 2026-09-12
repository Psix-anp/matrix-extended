from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_manifest_bumped_to_v03() -> None:
    manifest = json.loads((COMP / "manifest.json").read_text())
    assert manifest["version"] == "0.4.2"


def test_v03_services_are_declared() -> None:
    text = (COMP / "services.yaml").read_text()
    for service in ("reply:", "react:", "edit:", "redact:"):
        assert service in text


def test_v03_has_listener_and_incoming_event_names() -> None:
    init = (COMP / "__init__.py").read_text()
    client = (COMP / "client.py").read_text()
    assert "async_start_listener" in client
    assert "EVENT_MESSAGE" in init
    assert "EVENT_REPLY" in init
    assert "EVENT_REACTION" in init
    assert "EVENT_MEDIA" in init


def test_v03_config_exposes_incoming_allowlists() -> None:
    const = (COMP / "const.py").read_text()
    config = (COMP / "config_flow.py").read_text()
    for key in ("CONF_INCOMING_ENABLED", "CONF_ALLOWED_USERS", "CONF_ALLOWED_ROOMS"):
        assert key in const
        assert key in config
