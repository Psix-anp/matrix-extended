from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
PREPARE_HA = ROOT / "ci" / "scripts" / "prepare-ha.sh"
HA_E2E = ROOT / "ci" / "scripts" / "ha-e2e.py"
ELEMENT_E2E = ROOT / "ci" / "scripts" / "element-e2e.py"


def test_real_stack_prepares_voice_fixture_in_allowed_ha_directory() -> None:
    text = PREPARE_HA.read_text()
    assert "allowlist_external_dirs" in text
    assert "/config/matrix-e2e-media" in text
    assert "matrix-e2e-voice.wav" in text


def test_ha_e2e_sends_encrypted_location_and_native_voice() -> None:
    text = HA_E2E.read_text()
    assert "def send_rich()" in text
    assert '"/api/services/matrix_extended/send_location"' in text
    assert "Matrix Extended E2E Location" in text
    assert "/config/matrix-e2e-media/matrix-e2e-voice.wav" in text
    assert '"voice": True' in text
    assert "Matrix Extended E2E Voice" in text


def test_element_e2e_verifies_location_and_voice_rendering() -> None:
    text = ELEMENT_E2E.read_text()
    assert 'LOCATION_TEXT = "Matrix Extended E2E Location"' in text
    assert 'VOICE_TEXT = "Matrix Extended E2E Voice"' in text
    assert 'mode == "verify-rich"' in text
    assert '"verify-rich"' in text


def test_real_stack_runs_rich_send_and_element_render_checks() -> None:
    text = WORKFLOW.read_text()
    assert "Send encrypted location and native voice through Home Assistant" in text
    assert "python ci/scripts/ha-e2e.py send-rich" in text
    assert "Verify Element renders location and native voice" in text
    assert "python ci/scripts/element-e2e.py verify-rich" in text
