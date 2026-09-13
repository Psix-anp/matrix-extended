from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
PREPARE_HA = ROOT / "ci" / "scripts" / "prepare-ha.sh"
HA_E2E = ROOT / "ci" / "scripts" / "ha-e2e.py"
ELEMENT_E2E = ROOT / "ci" / "scripts" / "element-e2e.py"
ELEMENT_CONFIG = ROOT / "ci" / "element" / "config.json"


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
    assert '"latitude": 52.3676' in text
    assert '"longitude": 4.9041' in text
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


def test_element_location_locator_uses_native_location_map_component() -> None:
    text = ELEMENT_E2E.read_text()
    assert '.mx_MLocationBody' in text
    assert '.mx_MLocationBody_map' in text
    assert 're.compile(rf"{re.escape(LOCATION_TEXT)}$")' not in text
    assert 'get_by_text(LOCATION_TEXT, exact=True)' not in text


def test_real_stack_uses_one_post_login_element_session_for_text_and_rich() -> None:
    text = WORKFLOW.read_text()
    assert "Verify Element decrypts text and renders rich Matrix events" in text
    assert "python ci/scripts/element-e2e.py verify-message-rich" in text
    assert "python ci/scripts/ha-e2e.py send-rich" not in text
    assert "python ci/scripts/element-e2e.py verify-rich" not in text
    assert "python ci/scripts/element-e2e.py final" not in text


def test_element_demo_config_has_public_map_style_for_static_location() -> None:
    text = ELEMENT_CONFIG.read_text()
    assert '"map_style_url": "https://tiles.openfreemap.org/styles/liberty"' in text


def test_showcase_screenshot_dismisses_sections_tip_and_hides_only_ci_trust_warning() -> None:
    text = ELEMENT_E2E.read_text()
    assert '"Ok"' in text
    assert "def _prepare_showcase_screenshot(" in text
    assert '.mx_EventTile [data-testid="e2e-padlock"]' in text
    assert ".mx_EventTile_e2eIcon_warning" not in text
    assert "Unable to load map" in text
    assert "wait_for(state=\"hidden\"" in text
