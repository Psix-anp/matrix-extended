from pathlib import Path


SCRIPT = Path("ci/scripts/element-e2e.py")


def test_reused_element_profile_has_settle_delay_before_browser_launch() -> None:
    source = SCRIPT.read_text()

    assert "PROFILE_REOPEN_SETTLE_SECONDS" in source
    assert "if mode != \"login\":" in source
    assert "time.sleep(PROFILE_REOPEN_SETTLE_SECONDS)" in source
