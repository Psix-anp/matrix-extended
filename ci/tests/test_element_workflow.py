from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_element_start_does_not_recreate_running_synapse() -> None:
    text = WORKFLOW.read_text()
    assert "docker compose -f compose.test.yml up -d --no-deps element" in text


def test_v051_real_stack_keeps_recovery_and_adds_command_voice_gate() -> None:
    text = WORKFLOW.read_text()
    assert "Verify encrypted safe commands and automatic voice Assist" in text
    assert "python ci/scripts/matrix-command-e2e.py" in text
    assert "Stop Synapse while Home Assistant stays running" in text
    assert "Verify queued delivery, inbound listener, and encrypted outbound recovery without HA reload" in text
    assert text.index("Verify encrypted safe commands and automatic voice Assist") < text.index(
        "Stop Synapse while Home Assistant stays running"
    )
