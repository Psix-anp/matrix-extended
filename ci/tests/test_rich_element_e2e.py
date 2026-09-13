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


def test_ha_e2e_waits_for_both_encrypted_rich_events_across_sync_batches() -> None:
    text = HA_E2E.read_text()
    assert "def _wait_for_encrypted_events(" in text
    assert "expected_count=2" in text
    assert "since = sync[\"next_batch\"]" in text
    assert "total += _encrypted_event_count(" in text


def test_element_e2e_verifies_text_then_sends_and_renders_rich_in_one_session() -> None:
    text = ELEMENT_E2E.read_text()
    assert 'LOCATION_TEXT = "Matrix Extended E2E Location"' in text
    assert 'VOICE_TEXT = "Matrix Extended E2E Voice"' in text
    assert 'mode == "verify-message-rich"' in text
    assert 'subprocess.run(' in text
    assert '"ci/scripts/ha-e2e.py", "send-rich"' in text
    assert '.mx_MVoiceMessageBody' in text
    assert '03-element-location-and-voice.png' in text


def test_element_location_locator_accepts_element_caption_prefix() -> None:
    text = ELEMENT_E2E.read_text()
    assert 're.compile(rf"{re.escape(LOCATION_TEXT)}$")' in text
    assert 'get_by_text(LOCATION_TEXT, exact=True)' not in text


def test_real_stack_uses_one_post_login_element_session_for_text_and_rich() -> None:
    text = WORKFLOW.read_text()
    assert "Verify Element decrypts text and renders rich Matrix events" in text
    assert "python ci/scripts/element-e2e.py verify-message-rich" in text
    assert "python ci/scripts/ha-e2e.py send-rich" not in text
    assert "python ci/scripts/element-e2e.py verify-rich" not in text
    assert "python ci/scripts/element-e2e.py final" not in text
