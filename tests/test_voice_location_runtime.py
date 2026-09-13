from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def test_voice_and_location_constants_exist() -> None:
    const = (COMP / "const.py").read_text()
    assert 'SERVICE_SEND_LOCATION: Final = "send_location"' in const
    assert 'EVENT_LOCATION: Final = "matrix_extended_location"' in const


def test_voice_is_wired_through_send_media_runtime() -> None:
    source = (COMP / "__init__.py").read_text()
    assert 'vol.Optional("voice", default=False)' in source
    assert 'voice=bool(item.get("voice", False))' in source


def test_location_service_is_registered_and_can_resolve_ha_entity() -> None:
    source = (COMP / "__init__.py").read_text()
    for marker in (
        "SERVICE_SEND_LOCATION",
        "build_location_content",
        "hass.states.get",
        "latitude",
        "longitude",
    ):
        assert marker in source


def test_receiver_exposes_incoming_location_and_voice_metadata() -> None:
    receiver = (COMP / "receiver.py").read_text()
    assert "RoomMessageLocation" in receiver
    assert "EVENT_LOCATION" in receiver
    assert '"voice"' in receiver
    assert "org.matrix.msc3245.voice" in receiver


def test_services_yaml_documents_voice_and_location() -> None:
    services = (COMP / "services.yaml").read_text()
    assert "voice:" in services
    assert "send_location:" in services
    assert "latitude:" in services
    assert "longitude:" in services
