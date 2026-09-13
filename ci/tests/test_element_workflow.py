from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def test_element_start_does_not_recreate_running_synapse() -> None:
    text = WORKFLOW.read_text()
    assert "docker compose -f compose.test.yml up -d --no-deps element" in text
