from pathlib import Path


ROOT = Path(__file__).parents[1]
MANAGER = ROOT / "custom_components" / "matrix_extended" / "control_panel_manager.py"


def test_real_ha_state_tracker_runs_panel_callback_on_event_loop() -> None:
    """Prevent HA from dispatching panel state callbacks to an executor thread."""
    source = MANAGER.read_text(encoding="utf-8")

    assert "HassJobType.Callback" in source
    assert "job_type=HassJobType.Callback" in source
