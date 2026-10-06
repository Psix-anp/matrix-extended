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


def test_widget_browser_checks_do_not_reuse_the_e2ee_element_profile() -> None:
    text = WORKFLOW.read_text()
    assert "ELEMENT_PROFILE_DIR: .ci/element-widget-profile" in text
    assert "ELEMENT_PROFILE_DIR: .ci/element-widget-restart-profile" in text
    assert "Login dedicated Element session for Native Matrix Widget" in text
    assert "Login fresh Element session for Widget restart verification" in text
    assert "python ci/scripts/widget-e2e.py verify-restart" not in text
    assert text.index("Login dedicated Element session for Native Matrix Widget") < text.index(
        "Verify Native Matrix Widget in Element"
    )
    assert text.index("Login fresh Element session for Widget restart verification") < text.index(
        "Verify Native Matrix Widget reconnects after Home Assistant restart"
    )


def test_element_login_dismisses_new_device_identity_prompt_before_room_wait() -> None:
    source = (ROOT / "ci" / "scripts" / "element-e2e.py").read_text()
    assert "Confirm your digital identity" in source
    assert ".mx_Dialog_cancelButton" in source
    login = source.split("def _login", 1)[1].split("def _open_room", 1)[0]
    assert "_wait_for_room_ready(page)" in login
