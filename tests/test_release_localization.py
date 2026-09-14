from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _manifest_version() -> str:
    manifest = json.loads(
        (ROOT / "custom_components/matrix_extended/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return manifest["version"]


def _release_body(path: Path, version: str) -> str:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## {re.escape(version)}(?:\s+—[^\n]*)?\n(?P<body>.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"{path.name} has no notes for {version}"
    body = match.group("body").strip()
    assert body, f"{path.name} has empty notes for {version}"
    return body


def test_current_release_has_english_and_russian_changelog_entries() -> None:
    version = _manifest_version()
    assert _release_body(ROOT / "CHANGELOG.md", version)
    assert _release_body(ROOT / "CHANGELOG.ru.md", version)


def test_release_workflow_publishes_bilingual_notes() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "CHANGELOG.ru.md" in workflow
    assert "## English" in workflow
    assert "## Русский" in workflow
    assert "Backfill Russian notes into an existing release" in workflow
