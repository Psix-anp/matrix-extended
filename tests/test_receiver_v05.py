from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_receiver():
    pkg_name = "matrix_extended_receiver_v05_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package

    nio = types.ModuleType("nio")
    for name in (
        "ReactionEvent",
        "RedactionEvent",
        "RoomEncryptedAudio",
        "RoomEncryptedFile",
        "RoomEncryptedImage",
        "RoomEncryptedVideo",
        "RoomMessageAudio",
        "RoomMessageEmote",
        "RoomMessageFile",
        "RoomMessageImage",
        "RoomMessageNotice",
        "RoomMessageText",
        "RoomMessageVideo",
    ):
        setattr(nio, name, type(name, (), {}))
    sys.modules["nio"] = nio

    ha = types.ModuleType("homeassistant")
    ha_core = types.ModuleType("homeassistant.core")
    ha_core.HomeAssistant = object
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.core"] = ha_core

    def load_local(name: str):
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.{name}", COMP / f"{name}.py"
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    const = load_local("const")
    load_local("incoming")

    client = types.ModuleType(f"{pkg_name}.client")

    class MatrixExtendedError(Exception):
        pass

    client.MatrixExtendedError = MatrixExtendedError
    client.MatrixAccount = object
    sys.modules[f"{pkg_name}.client"] = client

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.receiver", COMP / "receiver.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, const


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, *, blocking, target):
        self.calls.append((domain, service, data, blocking, target))


class FakeHass:
    def __init__(self):
        self.bus = FakeBus()
        self.services = FakeServices()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeStatus:
    def __init__(self):
        self.receives = 0

    def mark_receive(self):
        self.receives += 1

    def mark_error(self, _error):
        pass


class FakePolicy:
    def should_process(self, **_kwargs):
        return True


class FakeClient:
    def __init__(self):
        self.callbacks = []

    def add_event_callback(self, callback, event_filter):
        self.callbacks.append((callback, event_filter))


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def consume(self, **kwargs):
        self.calls.append(kwargs)
        return None

    async def async_save(self):
        pass


def make_account(*, registry=None):
    return types.SimpleNamespace(
        client=FakeClient(),
        incoming_policy=FakePolicy(),
        action_registry=registry,
        status=FakeStatus(),
    )


def make_room():
    room = types.SimpleNamespace(
        room_id="!home:example",
        display_name="Home alerts",
        canonical_alias="#home:example",
    )
    room.user_name = lambda user_id: "Seriy" if user_id == "@user:example" else None
    return room


def make_event(**overrides):
    data = {
        "sender": "@user:example",
        "event_id": "$event",
        "server_timestamp": 123,
        "transaction_id": None,
        "source": {"content": {}},
        "body": "hello",
        "formatted_body": None,
        "decrypted": True,
        "verified": True,
    }
    data.update(overrides)
    return types.SimpleNamespace(**data)


def make_receiver(tmp_path, *, registry=None):
    mod, const = load_receiver()
    hass = FakeHass()
    account = make_account(registry=registry)
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    return mod, const, hass, account, receiver


def test_register_adds_redaction_callback(tmp_path) -> None:
    mod, _, _, account, receiver = make_receiver(tmp_path)
    receiver.register()
    assert len(account.client.callbacks) == 4
    assert account.client.callbacks[3][1] is mod.RedactionEvent


def test_base_payload_includes_room_and_sender_metadata(tmp_path) -> None:
    _, _, _, _, receiver = make_receiver(tmp_path)
    payload = receiver._base_payload(make_room(), make_event())
    assert payload["room_name"] == "Home alerts"
    assert payload["canonical_alias"] == "#home:example"
    assert payload["sender_display_name"] == "Seriy"


@pytest.mark.asyncio
async def test_replacement_message_fires_edit_event_with_new_content(tmp_path) -> None:
    _, const, hass, account, receiver = make_receiver(tmp_path)
    event = make_event(
        body="* stale fallback",
        source={
            "content": {
                "msgtype": "m.notice",
                "body": "* stale fallback",
                "m.relates_to": {"rel_type": "m.replace", "event_id": "$original"},
                "m.new_content": {
                    "msgtype": "m.notice",
                    "body": "updated",
                    "format": "org.matrix.custom.html",
                    "formatted_body": "<b>updated</b>",
                },
            }
        },
    )
    await receiver.async_handle_text(make_room(), event)
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_EDIT
    assert payload["replaces"] == "$original"
    assert payload["message"] == "updated"
    assert payload["formatted_body"] == "<b>updated</b>"
    assert payload["msgtype"] == "notice"
    assert account.status.receives == 1


@pytest.mark.asyncio
async def test_redaction_fires_dedicated_event(tmp_path) -> None:
    _, const, hass, account, receiver = make_receiver(tmp_path)
    event = make_event(redacts="$old", reason="obsolete")
    await receiver.async_handle_redaction(make_room(), event)
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_REDACTION
    assert payload["redacts"] == "$old"
    assert payload["reason"] == "obsolete"
    assert account.status.receives == 1


@pytest.mark.asyncio
async def test_media_payload_exposes_matrix_info_metadata(tmp_path) -> None:
    _, const, hass, _, receiver = make_receiver(tmp_path)
    event = make_event(
        body="clip.mp4",
        source={
            "content": {
                "msgtype": "m.video",
                "url": "mxc://example/clip",
                "info": {
                    "mimetype": "video/mp4",
                    "size": 12345,
                    "w": 1280,
                    "h": 720,
                    "duration": 4200,
                },
            }
        },
    )
    await receiver.async_handle_media(make_room(), event)
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_MEDIA
    assert payload["size"] == 12345
    assert payload["width"] == 1280
    assert payload["height"] == 720
    assert payload["duration_ms"] == 4200
    assert payload["msgtype"] == "video"


@pytest.mark.asyncio
async def test_reaction_passes_sender_to_action_authorization(tmp_path) -> None:
    registry = FakeRegistry()
    _, _, _, _, receiver = make_receiver(tmp_path, registry=registry)
    event = make_event(key="✅", reacts_to="$target")
    await receiver.async_handle_reaction(make_room(), event)
    assert registry.calls == [
        {
            "room_id": "!home:example",
            "event_id": "$target",
            "reaction": "✅",
            "sender": "@user:example",
        }
    ]
