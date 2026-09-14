from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_executor():
    pkg_name = "matrix_extended_camera_command_v051_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    for name in ("commands", "content"):
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{name}", COMP / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    media_module = types.ModuleType(f"{pkg_name}.media")
    media_module.MediaResolver = FakeMediaResolver
    sys.modules[f"{pkg_name}.media"] = media_module

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.command_executor", COMP / "command_executor.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, sys.modules[f"{pkg_name}.commands"]


class FakeMediaResolver:
    calls: list[dict] = []
    error: Exception | None = None

    def __init__(self, _hass) -> None:
        pass

    async def async_resolve(self, item):
        type(self).calls.append(dict(item))
        if type(self).error is not None:
            raise type(self).error
        return types.SimpleNamespace(
            data=b"jpeg-bytes",
            filename="gate.jpg",
            content_type="image/jpeg",
            size=len(b"jpeg-bytes"),
            width=640,
            height=480,
            duration_ms=None,
        )


class FakeClient:
    def __init__(self, *, encrypted=True) -> None:
        self.encrypted = encrypted
        self.uploads = []
        self.sent = []

    async def async_prepare_rooms(self, rooms):
        return [types.SimpleNamespace(room_id=room, encrypted=self.encrypted) for room in rooms]

    async def async_upload(self, data, *, filename, content_type, encrypt):
        self.uploads.append((data, filename, content_type, encrypt))
        return types.SimpleNamespace(
            mxc_uri="mxc://example/gate",
            encrypted_file={"url": "mxc://example/encrypted-gate", "key": {"k": "secret"}},
        )

    async def async_send_prepared(self, rooms, content, *, tx_ids=None):
        self.sent.append((rooms, content, tx_ids))
        return ["$image" for _ in rooms]


class FakeHass:
    pass


def camera_command(commands, *, progress=False):
    return commands.CommandRegistry().register(
        {
            "id": "camera_gate",
            "trigger": "camera gate",
            "progress": progress,
            "handler": {
                "type": "camera_snapshot",
                "entity_id": "camera.gate",
                "caption": "Gate camera",
            },
        }
    )


@pytest.mark.asyncio
async def test_camera_command_uses_only_registered_entity_and_sends_encrypted_image() -> None:
    FakeMediaResolver.calls.clear()
    FakeMediaResolver.error = None
    mod, commands = load_executor()
    client = FakeClient(encrypted=True)
    executor = mod.CommandExecutor(FakeHass(), types.SimpleNamespace(client=client))

    result = await executor.async_execute(
        camera_command(commands),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id="$thread",
    )

    assert result.status == "success"
    assert result.handler_type == "camera_snapshot"
    assert FakeMediaResolver.calls == [{"entity_id": "camera.gate", "type": "image"}]
    assert client.uploads == [(b"jpeg-bytes", "gate.jpg", "image/jpeg", True)]
    assert len(client.sent) == 1
    content = client.sent[0][1]
    assert content["msgtype"] == "m.image"
    assert content["body"] == "Gate camera"
    assert "file" in content
    assert "url" not in content


@pytest.mark.asyncio
async def test_camera_resolution_failure_is_bounded_failed_result() -> None:
    FakeMediaResolver.calls.clear()
    FakeMediaResolver.error = RuntimeError("camera unavailable secret-token=" + "x" * 500)
    mod, commands = load_executor()
    client = FakeClient(encrypted=True)
    executor = mod.CommandExecutor(FakeHass(), types.SimpleNamespace(client=client))

    result = await executor.async_execute(
        camera_command(commands),
        room_id="!home:example.org",
        sender="@owner:example.org",
        source_event_id="$command",
        thread_id=None,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert len(result.error) <= 200
    assert "x" * 100 not in result.error
    assert client.uploads == []
    assert client.sent == []


def test_malicious_camera_suffix_is_not_a_registered_command() -> None:
    _, commands = load_executor()
    registry = commands.CommandRegistry()
    registry.register(
        {
            "id": "camera_gate",
            "trigger": "camera gate",
            "handler": {
                "type": "camera_snapshot",
                "entity_id": "camera.gate",
                "caption": "Gate camera",
            },
        }
    )
    assert registry.match(
        "!camera gate camera.other",
        sender="@owner:example.org",
        room_id="!home:example.org",
    ) is None
