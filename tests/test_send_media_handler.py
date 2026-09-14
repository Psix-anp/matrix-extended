from pathlib import Path

ROOT = Path(__file__).parents[1]
MEDIA_PICKER = ROOT / "custom_components" / "matrix_extended" / "media_picker.py"


def test_send_media_registers_single_argument_home_assistant_handler() -> None:
    text = MEDIA_PICKER.read_text(encoding="utf-8")
    assert "async def handler(call: ServiceCall)" in text
    assert "await _async_send_media(hass, call)" in text
    assert "SERVICE_SEND_MEDIA,\n        handler," in text
