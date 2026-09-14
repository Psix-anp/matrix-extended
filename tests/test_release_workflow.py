from pathlib import Path


def test_release_workflow_contract() -> None:
    workflow_path = Path('.github/workflows/release.yml')
    assert workflow_path.is_file()

    text = workflow_path.read_text(encoding='utf-8')
    assert 'permissions:' in text
    assert 'contents: write' in text
    assert 'workflow_run:' in text
    assert 'Matrix Extended tests' in text
    assert 'types: [completed]' in text
    assert 'branches: [main]' in text
    assert "conclusion == 'success'" in text
    assert 'github.event.workflow_run.head_sha' in text
    assert 'custom_components/matrix_extended/manifest.json' in text
    assert 'CHANGELOG.md' in text
    assert 'CHANGELOG.ru.md' in text
    assert 'ci/scripts/build-release.py' in text
    assert 'gh release create' in text
    assert 'matrix_extended-ha-install-v${version}.zip' in text


def test_release_workflow_is_idempotent_and_can_backfill_russian_notes() -> None:
    text = Path('.github/workflows/release.yml').read_text(encoding='utf-8')
    assert 'gh release view' in text
    assert "steps.existing.outputs.exists == 'true'" in text
    assert 'Backfill Russian notes into an existing release' in text
    assert "grep -q '^## Русский$'" in text
    assert 'gh release edit' in text
    assert "steps.existing.outputs.exists != 'true'" in text
