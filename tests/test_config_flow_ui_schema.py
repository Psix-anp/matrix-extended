from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
CONFIG_FLOW = ROOT / "custom_components" / "matrix_extended" / "config_flow.py"
CONST = ROOT / "custom_components" / "matrix_extended" / "const.py"
SERVICES = ROOT / "custom_components" / "matrix_extended" / "services.yaml"


def test_config_flow_uses_serializable_home_assistant_selectors() -> None:
    source = CONFIG_FLOW.read_text()

    # HA 2026.9+ serializes config-flow schemas for the frontend using probatio.
    # These validator shapes are not serializable there and caused a HTTP 500
    # before the first form could be rendered.
    assert ": cv.url" not in source
    assert "vol.All(cv.ensure_list, [cv.string])" not in source

    assert "TextSelectorType.URL" in source
    assert "TextSelectorType.PASSWORD" in source
    assert "TextSelectorConfig(multiple=True)" in source


def test_options_flow_exposes_bounded_incoming_media_retention() -> None:
    source = CONFIG_FLOW.read_text()
    const = CONST.read_text()
    for marker in (
        'CONF_INCOMING_MEDIA_RETENTION_DAYS: Final = "incoming_media_retention_days"',
        'CONF_INCOMING_MEDIA_MAX_MB: Final = "incoming_media_max_mb"',
        'SERVICE_PURGE_MEDIA: Final = "purge_media"',
    ):
        assert marker in const

    assert "CONF_INCOMING_MEDIA_RETENTION_DAYS" in source
    assert "CONF_INCOMING_MEDIA_MAX_MB" in source
    assert "NumberSelector" in source
    assert "min=0" in source
    assert "max=365" in source
    assert "min=16" in source
    assert "max=4096" in source


def test_services_yaml_declares_manual_media_purge() -> None:
    text = SERVICES.read_text()
    assert "purge_media:" in text
    assert "removed file and byte counts" in text
    assert "config_entry:" in text
    assert "integration: matrix_extended" in text
