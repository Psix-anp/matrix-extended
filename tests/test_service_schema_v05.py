from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_v05_constants_expose_message_and_delivery_contract() -> None:
    text = (COMP / "const.py").read_text()
    for marker in (
        'ATTR_MSGTYPE: Final = "msgtype"',
        'ATTR_MENTION_USERS: Final = "mention_users"',
        'ATTR_MENTION_ROOM: Final = "mention_room"',
        'FORMAT_MARKDOWN: Final = "markdown"',
        'EVENT_DELIVERY: Final = "matrix_extended_delivery"',
    ):
        assert marker in text


def test_send_service_supports_response_markdown_mentions_and_action_controls() -> None:
    source = (COMP / "__init__.py").read_text()
    assert "SupportsResponse.OPTIONAL" in source
    assert "FORMAT_MARKDOWN" in source
    assert "ATTR_MSGTYPE" in source
    assert "ATTR_MENTION_USERS" in source
    assert "ATTR_MENTION_ROOM" in source
    assert 'vol.Optional("expires_in")' in source
    assert 'vol.Optional("max_uses")' in source
    assert 'vol.Optional("allowed_users")' in source
    assert "render_markdown" in source
    assert "build_mentions" in source
    assert "EVENT_DELIVERY" in source


def test_services_yaml_documents_v05_fields() -> None:
    text = (COMP / "services.yaml").read_text()
    for marker in (
        "msgtype:",
        "mention_users:",
        "mention_room:",
        "markdown",
        "expires_in",
        "max_uses",
        "allowed_users",
    ):
        assert marker in text
