from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


def load_receiver():
    pkg_name = "matrix_extended_receiver_testpkg"
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
        "RoomMessageUnknown",
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
    incoming = load_local("incoming")

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
    return mod, const, MatrixExtendedError


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, payload):
        self.events.append((event_type, payload))


class FakeServices:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def async_call(self, domain, service, data, *, blocking, target):
        self.calls.append((domain, service, data, blocking, target))
        if self.error is not None:
            raise self.error


class FakeHass:
    def __init__(self, service_error: Exception | None = None):
        self.bus = FakeBus()
        self.services = FakeServices(service_error)

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeStatus:
    def __init__(self):
        self.receives = 0
        self.errors = []

    def mark_receive(self):
        self.receives += 1

    def mark_error(self, error):
        self.errors.append(error)


class FakePolicy:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def should_process(self, **kwargs):
        self.calls.append(kwargs)
        return self.allowed


class FakeClient:
    def __init__(self):
        self.callbacks = []
        self.downloads = []
        self.download_result = (b"abc", "image/jpeg", "response.jpg")

    def add_event_callback(self, callback, event_filter):
        self.callbacks.append((callback, event_filter))

    async def async_download_media(self, mxc_uri, *, encrypted_file=None):
        self.downloads.append((mxc_uri, encrypted_file))
        result = self.download_result
        if isinstance(result, Exception):
            raise result
        return result


class FakeRegistry:
    def __init__(self, action=None):
        self.action = action
        self.calls = []
        self.saves = 0

    def consume(self, **kwargs):
        self.calls.append(kwargs)
        return self.action

    async def async_save(self):
        self.saves += 1


class Action:
    def __init__(self, service="light.turn_on", target=None, data=None):
        self.service = service
        self.target = target or {}
        self.data = data or {}


def make_account(*, allowed=True, registry=None):
    return types.SimpleNamespace(
        client=FakeClient(),
        incoming_policy=FakePolicy(allowed),
        action_registry=registry,
        status=FakeStatus(),
    )


def make_room():
    return types.SimpleNamespace(room_id="!home:example")


def make_event(**overrides):
    data = {
        "sender": "@user:example",
        "event_id": "$event",
        "server_timestamp": 123,
        "transaction_id": None,
        "source": {"content": {}},
        "body": "hello",
        "formatted_body": None,
        "decrypted": False,
        "verified": False,
    }
    data.update(overrides)
    return types.SimpleNamespace(**data)


def test_register_wires_all_callback_groups(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    receiver = mod.MatrixInboundReceiver(
        hass,
        entry_id="entry",
        account=account,
        incoming_dir=str(tmp_path),
        download_media=False,
    )
    receiver.register()
    assert len(account.client.callbacks) == 5
    assert account.client.callbacks[0][1] == mod._TEXT_EVENTS
    assert account.client.callbacks[1][1] is mod.ReactionEvent
    assert account.client.callbacks[2][1] == mod._MEDIA_EVENTS
    assert account.client.callbacks[3][1] is mod.RedactionEvent
    assert account.client.callbacks[4][1] is mod.RoomMessageUnknown


def test_allowed_requires_policy_and_passes_sender_room_transaction(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account(allowed=True)
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    event = make_event(transaction_id="tx1")
    assert receiver._allowed(make_room(), event) is True
    assert account.incoming_policy.calls == [{
        "sender": "@user:example",
        "room_id": "!home:example",
        "transaction_id": "tx1",
    }]
    account.incoming_policy = None
    assert receiver._allowed(make_room(), event) is False


def test_base_payload_defaults_and_relations(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    event = make_event(source={"content": {"m.relates_to": {"m.in_reply_to": {"event_id": "$parent"}, "rel_type": "m.thread", "event_id": "$thread"}}})
    delattr(event, "decrypted")
    delattr(event, "verified")
    payload = receiver._base_payload(make_room(), event)
    assert payload["account_id"] == "entry"
    assert payload["encrypted"] is False
    assert payload["verified"] is False
    assert payload["reply_to"] == "$parent"
    assert payload["thread_id"] == "$thread"


@pytest.mark.asyncio
async def test_text_denied_is_ignored_and_allowed_message_is_fired(tmp_path) -> None:
    mod, const, _ = load_receiver()
    hass = FakeHass()
    denied = make_account(allowed=False)
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=denied, incoming_dir=str(tmp_path), download_media=False)
    await receiver.async_handle_text(make_room(), make_event())
    assert hass.bus.events == []
    assert denied.status.receives == 0

    allowed = make_account(allowed=True)
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=allowed, incoming_dir=str(tmp_path), download_media=False)
    await receiver.async_handle_text(make_room(), make_event(body="hello", formatted_body="<b>hello</b>"))
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_MESSAGE
    assert payload["message"] == "hello"
    assert payload["formatted_body"] == "<b>hello</b>"
    assert allowed.status.receives == 1


@pytest.mark.asyncio
async def test_text_reply_uses_reply_event_type(tmp_path) -> None:
    mod, const, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    event = make_event(source={"content": {"m.relates_to": {"m.in_reply_to": {"event_id": "$parent"}}}})
    await receiver.async_handle_text(make_room(), event)
    assert hass.bus.events[-1][0] == const.EVENT_REPLY


@pytest.mark.asyncio
async def test_reaction_without_action_and_with_action(tmp_path) -> None:
    mod, const, _ = load_receiver()
    hass = FakeHass()
    account = make_account(registry=None)
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    event = make_event(key="✅", reacts_to="$target")
    await receiver.async_handle_reaction(make_room(), event)
    assert hass.bus.events[-1][0] == const.EVENT_REACTION
    assert hass.bus.events[-1][1]["action_executed"] is False
    assert hass.services.calls == []

    registry = FakeRegistry(Action(target={}, data={"brightness_pct": 50}))
    account2 = make_account(registry=registry)
    receiver2 = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account2, incoming_dir=str(tmp_path), download_media=False)
    await receiver2.async_handle_reaction(make_room(), event)
    payload = hass.bus.events[-1][1]
    assert payload["action_executed"] is True
    assert payload["action_service"] == "light.turn_on"
    assert registry.calls == [{"room_id": "!home:example", "event_id": "$target", "reaction": "✅", "sender": "@user:example"}]
    assert hass.services.calls[-1] == ("light", "turn_on", {"brightness_pct": 50}, True, None)


@pytest.mark.asyncio
async def test_reaction_action_failure_is_bounded_and_does_not_crash_receiver(tmp_path) -> None:
    mod, const, _ = load_receiver()
    hass = FakeHass(RuntimeError("token=abc123 " + "x" * 500))
    registry = FakeRegistry(Action())
    account = make_account(registry=registry)
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)

    await receiver.async_handle_reaction(
        make_room(), make_event(key="💡", reacts_to="$target")
    )

    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_REACTION
    assert payload["action_executed"] is False
    assert "abc123" not in payload["action_error"]
    assert "token=<redacted>" in payload["action_error"]
    assert len(payload["action_error"]) <= 200


@pytest.mark.asyncio
async def test_media_without_download_fires_metadata_only(tmp_path) -> None:
    mod, const, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    event = make_event(
        body="caption",
        source={"content": {"msgtype": "m.image", "url": "mxc://ex/img", "filename": "../door.jpg", "info": {"mimetype": "image/jpeg"}}},
    )
    await receiver.async_handle_media(make_room(), event)
    event_type, payload = hass.bus.events[-1]
    assert event_type == const.EVENT_MEDIA
    assert payload["media_type"] == "image"
    assert payload["filename"] == "door.jpg"
    assert payload["content_type"] == "image/jpeg"
    assert payload["mxc_uri"] == "mxc://ex/img"
    assert payload["local_path"] is None
    assert payload["download_error"] is None
    assert account.client.downloads == []


@pytest.mark.asyncio
async def test_encrypted_media_downloads_locally_and_uses_response_fallbacks(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    account.client.download_result = (b"abc", "image/jpeg", "response.jpg")
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=True)
    encrypted = {"url": "mxc://ex/cipher", "key": {"k": "x"}}
    event = make_event(
        body=None,
        source={"content": {"msgtype": "m.image", "file": encrypted, "info": {}}},
    )
    await receiver.async_handle_media(make_room(), event)
    payload = hass.bus.events[-1][1]
    assert account.client.downloads == [("mxc://ex/cipher", encrypted)]
    assert payload["filename"] == "response.jpg"
    assert payload["content_type"] == "image/jpeg"
    assert payload["local_path"] is not None
    assert Path(payload["local_path"]).read_bytes() == b"abc"


@pytest.mark.asyncio
async def test_media_download_error_is_reported_without_crashing(tmp_path) -> None:
    mod, _, MatrixExtendedError = load_receiver()
    hass = FakeHass()
    account = make_account()
    account.client.download_result = MatrixExtendedError("download failed")
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=True)
    event = make_event(source={"content": {"msgtype": "m.file", "url": "mxc://ex/file"}})
    await receiver.async_handle_media(make_room(), event)
    payload = hass.bus.events[-1][1]
    assert payload["local_path"] is None
    assert "download failed" in payload["download_error"]


@pytest.mark.asyncio
async def test_listener_error_updates_status(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=False)
    await receiver.async_listener_error(RuntimeError("boom"))
    assert account.status.errors == ["Matrix sync: boom"]


@pytest.mark.asyncio
async def test_incoming_media_exact_size_limit_is_allowed(tmp_path) -> None:
    mod, _, _ = load_receiver()
    mod.MAX_INCOMING_MEDIA_BYTES = 3
    hass = FakeHass()
    account = make_account()
    account.client.download_result = (b"abc", "application/octet-stream", "response.bin")
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=True)
    event = make_event(source={"content": {"msgtype": "m.file", "url": "mxc://ex/file", "filename": "keep.bin"}})
    await receiver.async_handle_media(make_room(), event)
    payload = hass.bus.events[-1][1]
    assert payload["download_error"] is None
    assert Path(payload["local_path"]).read_bytes() == b"abc"


@pytest.mark.asyncio
async def test_response_filename_does_not_replace_explicit_matrix_filename(tmp_path) -> None:
    mod, _, _ = load_receiver()
    hass = FakeHass()
    account = make_account()
    account.client.download_result = (b"abc", "application/octet-stream", "response.bin")
    receiver = mod.MatrixInboundReceiver(hass, entry_id="entry", account=account, incoming_dir=str(tmp_path), download_media=True)
    event = make_event(source={"content": {"msgtype": "m.file", "url": "mxc://ex/file", "filename": "matrix-name.bin"}})
    await receiver.async_handle_media(make_room(), event)
    assert hass.bus.events[-1][1]["filename"] == "matrix-name.bin"
