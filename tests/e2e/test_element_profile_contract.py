from pathlib import Path


SCRIPT = Path("ci/scripts/element-e2e.py")


def test_element_reuses_one_authenticated_session_for_all_post_login_ui_checks() -> None:
    source = SCRIPT.read_text()

    assert "PROFILE_REOPEN_SETTLE_SECONDS" not in source
    assert 'mode == "verify-message-rich"' in source
    assert 'modes = {"login", "verify-message-rich"}' in source
    assert 'mode == "verify-rich"' not in source
    assert 'mode == "final"' not in source
