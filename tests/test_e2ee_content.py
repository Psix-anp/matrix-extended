from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CONTENT_PATH = ROOT / "custom_components" / "matrix_extended" / "content.py"
MANIFEST_PATH = ROOT / "custom_components" / "matrix_extended" / "manifest.json"
STATUS_PATH = ROOT / "custom_components" / "matrix_extended" / "status.py"


def load_module(path: Path, name: str):
    assert path.exists(), f"{path.name} implementation is absent"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def encrypted_file() -> dict:
    return {
        "url": "mxc://example/encrypted",
        "v": "v2",
        "key": {
            "alg": "A256CTR",
            "ext": True,
            "k": "key",
            "key_ops": ["encrypt", "decrypt"],
            "kty": "oct",
        },
        "iv": "iv",
        "hashes": {"sha256": "hash"},
    }


def test_encrypted_media_uses_file_not_url(encrypted_file: dict) -> None:
    mod = load_module(CONTENT_PATH, "matrix_extended_content_e2ee")
    content = mod.build_media_content(
        media_type="image",
        encrypted_file=encrypted_file,
        filename="door.jpg",
        content_type="image/jpeg",
        size=123,
        width=640,
        height=480,
    )
    assert content["file"] == encrypted_file
    assert "url" not in content
    assert content["info"]["mimetype"] == "image/jpeg"


def test_encrypted_thumbnail_uses_thumbnail_file(encrypted_file: dict) -> None:
    mod = load_module(CONTENT_PATH, "matrix_extended_content_e2ee_thumb")
    thumb = dict(encrypted_file)
    thumb["url"] = "mxc://example/thumb"
    content = mod.build_media_content(
        media_type="video",
        encrypted_file=encrypted_file,
        filename="clip.mp4",
        content_type="video/mp4",
        size=456,
        thumbnail_encrypted_file=thumb,
        thumbnail_info={"mimetype": "image/jpeg", "size": 12, "w": 160, "h": 90},
    )
    assert content["info"]["thumbnail_file"] == thumb
    assert "thumbnail_url" not in content["info"]


def test_media_requires_exactly_one_plain_or_encrypted_source(encrypted_file: dict) -> None:
    mod = load_module(CONTENT_PATH, "matrix_extended_content_e2ee_validation")
    with pytest.raises(ValueError, match="exactly one"):
        mod.build_media_content(
            media_type="file",
            filename="x.bin",
            content_type="application/octet-stream",
            size=1,
        )
    with pytest.raises(ValueError, match="exactly one"):
        mod.build_media_content(
            media_type="file",
            mxc_uri="mxc://example/plain",
            encrypted_file=encrypted_file,
            filename="x.bin",
            content_type="application/octet-stream",
            size=1,
        )


def test_manifest_installs_matrix_nio_e2e_dependencies_explicitly() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["version"] == "0.5.1"
    requirements = set(manifest["requirements"])
    assert "matrix-nio[e2e]==0.26.0" in requirements
    assert "atomicwrites~=1.4" in requirements
    assert "cachetools>=5.3" in requirements
    assert "peewee~=3.14" in requirements
    assert "vodozemac>=0.9.0.post2" in requirements


def test_runtime_status_tracks_success_error_and_encryption() -> None:
    mod = load_module(STATUS_PATH, "matrix_extended_status")
    status = mod.MatrixRuntimeStatus()
    calls: list[int] = []
    remove = status.add_listener(lambda: calls.append(1))

    status.mark_connected(default_room_encrypted=True)
    assert status.connected is True
    assert status.default_room_encrypted is True
    assert status.last_error is None

    status.mark_send_success()
    assert status.last_send is not None
    assert status.connected is True

    status.mark_error("network down")
    assert status.connected is False
    assert status.last_error == "network down"

    remove()
    status.mark_error("ignored")
    assert len(calls) == 3


def test_audio_rejects_encrypted_thumbnail(encrypted_file: dict) -> None:
    mod = load_module(CONTENT_PATH, "matrix_extended_content_e2ee_audio_thumb")
    with pytest.raises(ValueError, match="thumbnail"):
        mod.build_media_content(
            media_type="audio",
            mxc_uri="mxc://example/audio",
            filename="alarm.ogg",
            content_type="audio/ogg",
            size=10,
            thumbnail_encrypted_file=encrypted_file,
        )


def test_runtime_status_initial_and_receive_states() -> None:
    mod = load_module(STATUS_PATH, "matrix_extended_status_receive")
    status = mod.MatrixRuntimeStatus()
    assert status.connected is False
    assert status.last_receive is None
    status.mark_receive()
    assert status.connected is True
    assert status.last_receive is not None
    assert status.last_error is None


def test_runtime_status_error_can_preserve_connected_state() -> None:
    mod = load_module(STATUS_PATH, "matrix_extended_status_connected_error")
    status = mod.MatrixRuntimeStatus()
    status.mark_error("partial failure", connected=True)
    assert status.connected is True
    assert status.last_error == "partial failure"
