import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "custom_components" / "matrix_extended" / "manifest.json"
HACS = ROOT / "hacs.json"
ICON = ROOT / "custom_components" / "matrix_extended" / "brand" / "icon.png"
LICENSE = ROOT / "LICENSE"
HACS_WORKFLOW = ROOT / ".github" / "workflows" / "hacs.yml"
HASSFEST_WORKFLOW = ROOT / ".github" / "workflows" / "hassfest.yml"


def test_hacs_json_uses_supported_repository_layout():
    data = json.loads(HACS.read_text(encoding="utf-8"))
    assert data == {
        "name": "Matrix Extended",
        "content_in_root": False,
        "homeassistant": "2026.9.0",
    }


def test_manifest_has_hacs_required_metadata():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("domain", "documentation", "issue_tracker", "codeowners", "name", "version"):
        assert data.get(key)
    assert data["domain"] == "matrix_extended"
    assert data["documentation"] == "https://github.com/Psix-anp/matrix-extended"
    assert data["issue_tracker"] == "https://github.com/Psix-anp/matrix-extended/issues"
    assert "@Psix-anp" in data["codeowners"]


def test_local_brand_icon_is_a_png():
    raw = ICON.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 512


def test_repository_has_mit_license():
    assert LICENSE.read_text(encoding="utf-8").startswith("MIT License\n")


def test_public_hacs_validation_workflows_are_present_and_strict():
    hacs = HACS_WORKFLOW.read_text(encoding="utf-8")
    hassfest = HASSFEST_WORKFLOW.read_text(encoding="utf-8")

    assert "hacs/action@main" in hacs
    assert "category: integration" in hacs
    assert "ignore:" not in hacs

    assert "home-assistant/actions/hassfest@master" in hassfest
    assert "pull_request:" in hassfest
    assert "push:" in hassfest
