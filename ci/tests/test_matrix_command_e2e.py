from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "ci" / "scripts" / "matrix-command-e2e.py"


def test_matrix_sender_bootstraps_e2ee_without_decrypting_old_timeline() -> None:
    text = SCRIPT.read_text()
    upload = text.index("if client.should_upload_keys:")
    initial_sync = text.index("await client.sync(", upload)
    assert upload < initial_sync
    assert '"timeline": {"limit": 0}' in text
    assert "sync_filter=initial_sync_filter" in text
