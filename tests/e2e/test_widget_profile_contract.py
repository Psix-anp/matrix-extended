from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_real_stack_uses_current_stable_versions() -> None:
    compose = text("compose.test.yml")
    workflow = text(".github/workflows/test.yml")
    for version in ("2026.9.4", "1.161.0", "1.12.30"):
        assert version in compose
        assert version in workflow
    for stale in ("2026.9.2", "1.160.0", "1.12.26"):
        assert stale not in compose
        assert stale not in workflow


def test_real_stack_hosts_and_tests_the_static_widget() -> None:
    compose = text("compose.test.yml")
    workflow = text(".github/workflows/test.yml")
    assert "widget:" in compose
    assert "127.0.0.1:8090" in compose
    assert "widget/dist" in compose
    assert "Build Native Matrix Widget" in workflow
    assert "widget-e2e.py" in workflow
    assert "Wait for Matrix Widget" in workflow


def test_widget_e2e_contract_covers_roundtrip_and_reconnect() -> None:
    source = text("ci/scripts/widget-e2e.py")
    for token in (
        "confirmation_required",
        "stale_generation",
        "duplicate_request",
        "matrix_widget_switch",
        "matrix_widget_dangerous",
        "integration_device_id",
        "widget_url",
    ):
        assert token in source


def test_release_builder_and_workflows_include_widget_archive() -> None:
    build = text("ci/scripts/build-release.py")
    tests = text(".github/workflows/test.yml")
    release = text(".github/workflows/release.yml")
    expected = "matrix_extended-widget-v${version}.zip"
    assert "build_widget_release" in build
    assert expected in tests
    assert expected in release
    assert "matrix_extended-widget-v${version}.zip.sha256" in tests
    assert "matrix_extended-widget-v${version}.zip.sha256" in release
