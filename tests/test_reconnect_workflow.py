from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_synapse_recovery_restarts_existing_container() -> None:
    """Recovery must preserve the stopped Synapse container and its file ownership."""
    text = WORKFLOW.read_text()
    marker = "- name: Start Synapse again"
    assert marker in text
    recovery = text.split(marker, 1)[1].split("- name:", 1)[0]
    assert "docker compose -f compose.test.yml start synapse" in recovery
    assert "up -d synapse" not in recovery
