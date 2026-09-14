from pathlib import Path


def test_release_workflow_contract() -> None:
    workflow_path = Path('.github/workflows/release.yml')
    assert workflow_path.is_file()

    text = workflow_path.read_text(encoding='utf-8')
    assert 'permissions:' in text
    assert 'contents: write' in text
    assert 'push:' in text
    assert 'branches: [main]' in text or '- main' in text
    assert 'custom_components/matrix_extended/manifest.json' in text
    assert 'CHANGELOG.md' in text
    assert 'ci/scripts/build-release.py' in text
    assert 'gh release create' in text
    assert 'matrix_extended-ha-install-v${version}.zip' in text


def test_release_workflow_is_idempotent() -> None:
    text = Path('.github/workflows/release.yml').read_text(encoding='utf-8')
    assert 'gh release view' in text
    assert 'already exists; nothing to publish' in text
