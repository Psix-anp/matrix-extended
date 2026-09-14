from pathlib import Path

import yaml


def test_release_workflow_contract() -> None:
    workflow_path = Path('.github/workflows/release.yml')
    assert workflow_path.is_file()

    workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
    assert workflow['permissions']['contents'] == 'write'
    assert 'push' in workflow['on']
    assert workflow['on']['push']['branches'] == ['main']

    jobs = workflow['jobs']
    release = jobs['release']
    steps = release['steps']
    rendered = '\n'.join(str(step) for step in steps)
    assert 'custom_components/matrix_extended/manifest.json' in rendered
    assert 'CHANGELOG.md' in rendered
    assert 'ci/scripts/build-release.py' in rendered
    assert 'gh release create' in rendered
    assert 'matrix_extended-ha-install-v${version}.zip' in rendered
    assert '--verify-tag' not in rendered


def test_release_workflow_is_idempotent() -> None:
    text = Path('.github/workflows/release.yml').read_text(encoding='utf-8')
    assert 'gh release view' in text
    assert 'already exists; nothing to publish' in text
