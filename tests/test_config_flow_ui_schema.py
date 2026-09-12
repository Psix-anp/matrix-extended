from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
CONFIG_FLOW = ROOT / "custom_components" / "matrix_extended" / "config_flow.py"


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
