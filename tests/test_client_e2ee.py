from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
CLIENT_PATH = ROOT / "custom_components" / "matrix_extended" / "client.py"


class _Response:
    pass


class LoginResponse(_Response):
    pass


class WhoamiResponse(_Response):
    pass


class RoomResolveAliasResponse(_Response):
    pass


class UploadResponse(_Response):
    def __init__(self, content_uri: str = "mxc://example/file") -> None:
        self.content_uri = content_uri


class SyncResponse(_Response):
    pass


class ErrorResponse(_Response):
    pass


class SyncError(ErrorResponse):
    def __init__(self, status_code):
        self.status_code = status_code
        self.message = status_code


class FakeRoom:
    def __init__(
        self,
        encrypted: bool,
        *,
        room_id: str = "!room:example",
        display_name: str = "Room",
        canonical_alias: str | None = None,
        joined_count: int = 1,
    ) -> None:
        self.encrypted = encrypted
        self.room_id = room_id
        self.display_name = display_name
        self.canonical_alias = canonical_alias
        self.joined_count = joined_count


class AsyncClientConfig:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class AsyncClient:
    last_instance = None

    def __init__(self, homeserver, user="", device_id="", store_path="", config=None, ssl=None):
        type(self).last_instance = self
        self.homeserver = homeserver
        self.user_id = user
        self.device_id = device_id
        self.store_path = store_path
        self.config = config
        self.ssl = ssl
        self.rooms = {}
        self.should_upload_keys = False
        self.should_query_keys = False
        self.should_claim_keys = False
        self.upload_encrypt_values = []
        self.keys_query_calls = 0
        self.sent_events = []
        self.redactions = []
        self.event_callbacks = []
        self.response_callbacks = []
        self.sync_calls = []
        self.close_calls = 0
        self.resolve_calls = []
        self.download_calls = []
        self.login_response = LoginResponse()
        self.login_response.user_id = "@ha:example"
        self.login_response.access_token = "token-from-login"
        self.login_response.device_id = "LOGINDEVICE"
        self.whoami_response = WhoamiResponse()
        self.sync_response = SyncResponse()
        self.room_resolve_response = None
        self.room_send_response = None
        self.download_response = None
        self.sync_forever_calls = []
        self.stop_sync_calls = 0
        self.sync_forever_error_once = None

    def restore_login(self, *, user_id, device_id, access_token):
        self.user_id = user_id
        self.device_id = device_id
        self.access_token = access_token

    async def login(self, *, password, device_name):
        return self.login_response

    async def upload(self, data, *, content_type, filename, filesize, encrypt=False):
        self.upload_encrypt_values.append(encrypt)
        decrypt = {
            "v": "v2",
            "key": {"alg": "A256CTR", "kty": "oct", "k": "key"},
            "iv": "iv",
            "hashes": {"sha256": "hash"},
        } if encrypt else None
        return UploadResponse(), decrypt

    async def sync(self, **kwargs):
        self.sync_calls.append(kwargs)
        return self.sync_response

    async def keys_upload(self):
        return _Response()

    async def keys_query(self):
        self.keys_query_calls += 1
        self.should_query_keys = False
        return _Response()

    def get_users_for_key_claiming(self):
        return {}

    async def keys_claim(self, users):
        self.should_claim_keys = False
        return _Response()

    async def room_resolve_alias(self, room):
        self.resolve_calls.append(room)
        if self.room_resolve_response is not None:
            return self.room_resolve_response
        response = RoomResolveAliasResponse()
        response.room_id = "!resolved:example"
        return response

    async def room_send(self, **kwargs):
        self.sent_events.append(kwargs)
        if self.room_send_response is not None:
            return self.room_send_response
        response = _Response()
        response.event_id = "$event"
        return response

    def add_event_callback(self, callback, event_filter):
        self.event_callbacks.append((callback, event_filter))

    def add_response_callback(self, callback, response_filter):
        self.response_callbacks.append((callback, response_filter))

    async def room_redact(self, room_id, event_id, reason=None):
        self.redactions.append((room_id, event_id, reason))
        return _Response()

    async def sync_forever(self, **kwargs):
        self.sync_forever_calls.append(kwargs)
        if self.sync_forever_error_once is not None:
            err = self.sync_forever_error_once
            self.sync_forever_error_once = None
            raise err
        await __import__("asyncio").Event().wait()

    def stop_sync_forever(self):
        self.stop_sync_calls += 1

    async def whoami(self):
        return self.whoami_response

    async def download(self, *, mxc):
        self.download_calls.append(mxc)
        if self.download_response is not None:
            return self.download_response
        response = _Response()
        response.body = b"plain"
        response.content_type = "application/octet-stream"
        response.filename = "file.bin"
        return response

    async def close(self):
        self.close_calls += 1
        return None


@pytest.fixture
def client_module(monkeypatch):
    nio = types.ModuleType("nio")
    nio.AsyncClient = AsyncClient
    nio.AsyncClientConfig = AsyncClientConfig
    responses = types.ModuleType("nio.responses")
    for name, value in {
        "ErrorResponse": ErrorResponse,
        "LoginResponse": LoginResponse,
        "RoomResolveAliasResponse": RoomResolveAliasResponse,
        "SyncResponse": SyncResponse,
        "SyncError": SyncError,
        "UploadResponse": UploadResponse,
        "WhoamiResponse": WhoamiResponse,
    }.items():
        setattr(responses, name, value)
    monkeypatch.setitem(sys.modules, "nio", nio)
    monkeypatch.setitem(sys.modules, "nio.responses", responses)

    spec = importlib.util.spec_from_file_location("matrix_extended_client_e2ee", CLIENT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def make_client(mod, *, require_e2ee: bool = True):
    return mod.MatrixClient(
        homeserver="https://matrix.example",
        user_id="@ha:example",
        access_token="token",
        device_id="DEVICE",
        verify_ssl=True,
        store_path="/tmp/matrix-store",
        store_key="secret-key",
        require_e2ee=require_e2ee,
    )


def test_client_uses_persistent_e2ee_config(client_module) -> None:
    make_client(client_module)
    nio_client = AsyncClient.last_instance
    assert nio_client.store_path == "/tmp/matrix-store"
    assert nio_client.config.encryption_enabled is True
    assert nio_client.config.store_sync_tokens is True
    assert nio_client.config.pickle_key == "secret-key"


@pytest.mark.asyncio
async def test_encrypted_upload_returns_matrix_encrypted_file(client_module) -> None:
    client = make_client(client_module)
    uploaded = await client.async_upload(
        b"secret image",
        filename="door.jpg",
        content_type="image/jpeg",
        encrypt=True,
    )
    assert AsyncClient.last_instance.upload_encrypt_values == [True]
    assert uploaded.mxc_uri == "mxc://example/file"
    assert uploaded.encrypted_file["url"] == "mxc://example/file"
    assert uploaded.encrypted_file["v"] == "v2"


@pytest.mark.asyncio
async def test_prepare_rooms_rejects_unencrypted_room_when_e2ee_required(client_module) -> None:
    client = make_client(client_module, require_e2ee=True)
    AsyncClient.last_instance.rooms["!plain:example"] = FakeRoom(encrypted=False)
    with pytest.raises(client_module.MatrixEncryptionRequiredError, match="not encrypted"):
        await client.async_prepare_rooms(["!plain:example"])


@pytest.mark.asyncio
async def test_prepare_rooms_marks_encrypted_room(client_module) -> None:
    client = make_client(client_module, require_e2ee=True)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    rooms = await client.async_prepare_rooms(["!secure:example"])
    assert [(room.room_id, room.encrypted) for room in rooms] == [
        ("!secure:example", True)
    ]


@pytest.mark.asyncio
async def test_prepare_rooms_runs_pending_key_query(client_module) -> None:
    client = make_client(client_module, require_e2ee=True)
    nio_client = AsyncClient.last_instance
    nio_client.rooms["!secure:example"] = FakeRoom(encrypted=True)
    nio_client.should_query_keys = True
    await client.async_prepare_rooms(["!secure:example"])
    assert nio_client.keys_query_calls == 1


@pytest.mark.asyncio
async def test_generic_event_send_supports_reactions(client_module) -> None:
    client = make_client(client_module, require_e2ee=True)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    event_id = await client.async_send_event(
        "!secure:example",
        "m.reaction",
        {"m.relates_to": {"rel_type": "m.annotation", "event_id": "$x", "key": "✅"}},
    )
    assert event_id == "$event"
    assert AsyncClient.last_instance.sent_events[-1]["message_type"] == "m.reaction"


def test_event_callback_is_forwarded_to_nio(client_module) -> None:
    client = make_client(client_module)
    callback = object()
    event_filter = object()
    client.add_event_callback(callback, event_filter)
    assert AsyncClient.last_instance.event_callbacks == [(callback, event_filter)]


@pytest.mark.asyncio
async def test_redact_resolves_room_and_calls_nio(client_module) -> None:
    client = make_client(client_module, require_e2ee=True)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    await client.async_redact("!secure:example", "$old", reason="expired")
    assert AsyncClient.last_instance.redactions == [
        ("!secure:example", "$old", "expired")
    ]


def test_rooms_snapshot_exposes_joined_room_metadata(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.rooms["!garage:example"] = FakeRoom(
        True,
        room_id="!garage:example",
        display_name="Garage",
        canonical_alias="#garage:example",
        joined_count=3,
    )
    rooms = client.rooms_snapshot()
    assert len(rooms) == 1
    assert rooms[0].room_id == "!garage:example"
    assert rooms[0].display_name == "Garage"
    assert rooms[0].canonical_alias == "#garage:example"
    assert rooms[0].encrypted is True
    assert rooms[0].joined_count == 3


def test_error_text_uses_status_and_string_fallback(client_module) -> None:
    class Response:
        status_code = 500
        message = ""
        def __str__(self) -> str:
            return "fallback"

    assert client_module._error_text(Response()) == "500: fallback"


@pytest.mark.asyncio
async def test_password_login_returns_token_and_closes_client(client_module) -> None:
    details = await client_module.async_password_login(
        "https://matrix.example", "@ha:example", "secret", True
    )
    assert details.user_id == "@ha:example"
    assert details.access_token == "token-from-login"
    assert details.device_id == "LOGINDEVICE"
    assert AsyncClient.last_instance.close_calls == 1


@pytest.mark.asyncio
async def test_connect_syncs_full_state_and_returns_none_without_default_room(client_module) -> None:
    client = make_client(client_module)
    result = await client.async_connect()
    assert result is None
    assert AsyncClient.last_instance.sync_calls[0]["timeout"] == 0
    assert AsyncClient.last_instance.sync_calls[0]["full_state"] is True
    assert AsyncClient.last_instance.sync_calls[0]["set_presence"] == "offline"


@pytest.mark.asyncio
async def test_connect_maps_401_to_authentication_error(client_module) -> None:
    client = make_client(client_module)
    response = ErrorResponse()
    response.status_code = 401
    response.message = "bad token"
    AsyncClient.last_instance.whoami_response = response
    with pytest.raises(client_module.MatrixAuthenticationError, match="bad token"):
        await client.async_connect()


@pytest.mark.asyncio
async def test_default_require_e2ee_blocks_plain_room(client_module) -> None:
    client = client_module.MatrixClient(
        homeserver="https://matrix.example",
        user_id="@ha:example",
        access_token="token",
        device_id="DEVICE",
        verify_ssl=True,
        store_path="/tmp/matrix-store",
        store_key="secret-key",
    )
    AsyncClient.last_instance.rooms["!plain:example"] = FakeRoom(encrypted=False)
    with pytest.raises(client_module.MatrixEncryptionRequiredError):
        await client.async_prepare_rooms(["!plain:example"])


@pytest.mark.asyncio
async def test_resolve_room_validates_alias_and_caches_result(client_module) -> None:
    client = make_client(client_module)
    assert await client.async_resolve_room("!direct:example") == "!direct:example"
    with pytest.raises(client_module.MatrixSendError, match="must start"):
        await client.async_resolve_room("bad-room")
    assert await client.async_resolve_room("#alias:example") == "!resolved:example"
    assert await client.async_resolve_room("#alias:example") == "!resolved:example"
    assert AsyncClient.last_instance.resolve_calls == ["#alias:example"]


@pytest.mark.asyncio
async def test_resolve_room_rejects_error_response(client_module) -> None:
    client = make_client(client_module)
    response = ErrorResponse()
    response.message = "missing alias"
    AsyncClient.last_instance.room_resolve_response = response
    with pytest.raises(client_module.MatrixSendError, match="missing alias"):
        await client.async_resolve_room("#missing:example")


@pytest.mark.asyncio
async def test_room_encrypted_syncs_incrementally_and_rejects_unjoined(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    assert await client.async_room_encrypted("!secure:example") is True
    assert AsyncClient.last_instance.sync_calls[0]["full_state"] is False

    client2 = make_client(client_module)
    with pytest.raises(client_module.MatrixSendError, match="not joined"):
        await client2.async_room_encrypted("!missing:example")
    assert [call["full_state"] for call in AsyncClient.last_instance.sync_calls] == [False, True]


@pytest.mark.asyncio
async def test_prepare_rooms_runs_incremental_sync_when_listener_is_not_running(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    await client.async_prepare_rooms(["!secure:example"])
    assert AsyncClient.last_instance.sync_calls[0]["full_state"] is False


@pytest.mark.asyncio
async def test_plain_upload_does_not_return_encrypted_metadata(client_module) -> None:
    client = make_client(client_module)
    uploaded = await client.async_upload(
        b"plain", filename="x.bin", content_type="application/octet-stream"
    )
    assert AsyncClient.last_instance.upload_encrypt_values == [False]
    assert uploaded.mxc_uri == "mxc://example/file"
    assert uploaded.encrypted_file is None


@pytest.mark.asyncio
async def test_send_event_passes_unverified_device_policy_and_returns_first_event(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    event_id = await client.async_send_content("!secure:example", {"body": "hello"})
    assert event_id == "$event"
    sent = AsyncClient.last_instance.sent_events[-1]
    assert sent["ignore_unverified_devices"] is True
    assert sent["message_type"] == "m.room.message"


@pytest.mark.asyncio
async def test_plain_download_returns_body_metadata(client_module) -> None:
    client = make_client(client_module)
    data, content_type, filename = await client.async_download_media("mxc://example/file")
    assert data == b"plain"
    assert content_type == "application/octet-stream"
    assert filename == "file.bin"
    assert AsyncClient.last_instance.download_calls == ["mxc://example/file"]


@pytest.mark.asyncio
async def test_download_rejects_response_without_body(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.download_response = _Response()
    with pytest.raises(client_module.MatrixSendError, match="download failed"):
        await client.async_download_media("mxc://example/missing")


@pytest.mark.asyncio
async def test_sync_default_is_incremental(client_module) -> None:
    client = make_client(client_module)
    await client._async_sync()
    assert AsyncClient.last_instance.sync_calls == [
        {"timeout": 0, "full_state": False, "set_presence": "offline"}
    ]


@pytest.mark.asyncio
async def test_connect_default_room_does_not_trigger_second_sync(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    assert await client.async_connect("!secure:example") is True
    assert [call["full_state"] for call in AsyncClient.last_instance.sync_calls] == [True]


def test_rooms_snapshot_fallback_defaults_and_sorts_by_room_id(client_module) -> None:
    client = make_client(client_module)

    class MinimalRoom:
        def __init__(self, room_id):
            self.room_id = room_id

    AsyncClient.last_instance.rooms["!z:example"] = MinimalRoom("!z:example")
    AsyncClient.last_instance.rooms["!a:example"] = MinimalRoom("!a:example")
    rooms = client.rooms_snapshot()
    assert [room.room_id for room in rooms] == ["!a:example", "!z:example"]
    assert rooms[0].display_name == "!a:example"
    assert rooms[0].encrypted is False
    assert rooms[0].joined_count == 0


@pytest.mark.asyncio
async def test_listener_starts_once_and_close_cancels_it(client_module) -> None:
    client = make_client(client_module)
    await client.async_start_listener()
    task = client._sync_task
    assert task is not None
    await client.async_start_listener()
    assert client._sync_task is task
    assert len(AsyncClient.last_instance.response_callbacks) == 1
    assert AsyncClient.last_instance.sync_forever_calls == [
        {"timeout": 30000, "set_presence": "offline"}
    ]
    await client.async_close()
    assert client._sync_task is None
    assert AsyncClient.last_instance.stop_sync_calls == 1
    assert AsyncClient.last_instance.close_calls == 1


@pytest.mark.asyncio
async def test_prepare_rooms_skips_initial_sync_with_active_listener(client_module) -> None:
    client = make_client(client_module)

    class ActiveTask:
        def done(self):
            return False

    client._sync_task = ActiveTask()
    AsyncClient.last_instance.rooms["!secure:example"] = FakeRoom(encrypted=True)
    result = await client.async_prepare_rooms(["!secure:example"])
    assert result[0].room_id == "!secure:example"
    assert AsyncClient.last_instance.sync_calls == []


@pytest.mark.asyncio
async def test_prepare_rooms_full_sync_can_materialize_missing_room(client_module) -> None:
    client = make_client(client_module)
    calls = []

    async def fake_sync(*, full_state=False):
        calls.append(full_state)
        if full_state:
            AsyncClient.last_instance.rooms["!late:example"] = FakeRoom(
                encrypted=True, room_id="!late:example"
            )

    client._async_sync = fake_sync
    result = await client.async_prepare_rooms(["!late:example"])
    assert result[0].room_id == "!late:example"
    assert calls == [False, True]


def test_runtime_dataclasses_keep_slots_and_immutable_value_objects(client_module) -> None:
    from dataclasses import FrozenInstanceError

    login = client_module.LoginDetails("@u:ex", "token", "DEV")
    prepared = client_module.PreparedRoom("!r:ex", True)
    uploaded = client_module.UploadedMedia("mxc://ex/file")
    account = client_module.MatrixAccount(client=object(), default_room="!r:ex")

    for obj in (login, prepared, uploaded, account):
        assert not hasattr(obj, "__dict__")

    with pytest.raises(FrozenInstanceError):
        prepared.encrypted = False
    with pytest.raises(FrozenInstanceError):
        uploaded.mxc_uri = "mxc://ex/other"


@pytest.mark.asyncio
async def test_listener_reports_transport_error_and_yields_immediately(client_module) -> None:
    client = make_client(client_module)
    AsyncClient.last_instance.sync_forever_error_once = RuntimeError("sync boom")
    delays = []
    errors = []
    real_sleep = client_module.asyncio.sleep

    async def fast_sleep(delay):
        delays.append(delay)
        await real_sleep(0)

    async def on_error(err):
        errors.append(str(err))

    client_module.asyncio.sleep = fast_sleep
    try:
        await client.async_start_listener(on_error)
        for _ in range(3):
            await real_sleep(0)
        assert errors == ["sync boom"]
        assert delays[0] == 0
        assert 5 in delays
    finally:
        await client.async_close()
        client_module.asyncio.sleep = real_sleep

@pytest.mark.asyncio
async def test_listener_recovers_after_empty_sync_without_inventing_activity(client_module):
    import asyncio

    status_spec = importlib.util.spec_from_file_location(
        "matrix_reconnect_status", ROOT / "custom_components" / "matrix_extended" / "status.py"
    )
    status_module = importlib.util.module_from_spec(status_spec)
    status_spec.loader.exec_module(status_module)
    status = status_module.MatrixRuntimeStatus()
    status.mark_connected(default_room_encrypted=True)
    changes = []
    status.add_listener(lambda: changes.append(status.connected))
    client = make_client(client_module)
    nio_client = AsyncClient.last_instance
    nio_client.sync_forever_error_once = RuntimeError("network down")
    callbacks = []
    nio_client.add_response_callback = lambda callback, filter: callbacks.append((callback, filter))
    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    async def on_error(err):
        status.mark_error(str(err))

    async def on_success():
        if not status.connected:
            status.mark_connected()

    client_module.asyncio.sleep = fast_sleep
    try:
        await client.async_start_listener(on_error, on_success)
        for _ in range(3):
            await real_sleep(0)
        assert not status.connected
        response = SyncResponse()
        for callback, response_type in callbacks:
            if isinstance(response, response_type):
                await callback(response)
        assert status.connected
        assert status.default_room_encrypted is True
        assert status.last_send is None and status.last_receive is None
        assert status.last_error is None
        assert changes == [False, True]
        for callback, response_type in callbacks:
            if isinstance(response, response_type):
                await callback(response)
        assert changes == [False, True]
    finally:
        await client.async_close()
        client_module.asyncio.sleep = real_sleep

@pytest.mark.asyncio
async def test_sync_errors_back_off_and_success_resets_retry_delay(client_module):
    import asyncio

    client = make_client(client_module)
    nio_client = AsyncClient.last_instance
    callbacks = []
    nio_client.add_response_callback = lambda callback, filter: callbacks.append((callback, filter))
    outcomes = [SyncError("502"), SyncError("502"), SyncResponse(), SyncError("M_UNKNOWN_TOKEN")]
    delays, errors = [], []
    done = asyncio.Event()
    real_sleep = asyncio.sleep

    async def fake_forever(**kwargs):
        while outcomes:
            response = outcomes.pop(0)
            for callback, response_type in callbacks:
                if isinstance(response, response_type):
                    await callback(response)
        done.set()
        await asyncio.Event().wait()

    async def fast_sleep(delay):
        if delay:
            delays.append(delay)
        await real_sleep(0)

    nio_client.sync_forever = fake_forever
    client_module.asyncio.sleep = fast_sleep
    try:
        await client.async_start_listener(lambda err: errors.append(str(err)))
        await asyncio.wait_for(done.wait(), 2)
        assert delays == [5, 10, 5]
        assert len(errors) == 3 and "M_UNKNOWN_TOKEN" in errors[-1]
    finally:
        await client.async_close()
        client_module.asyncio.sleep = real_sleep


@pytest.mark.asyncio
async def test_rate_limit_callback_does_not_interrupt_nio_server_delay(client_module):
    client = make_client(client_module)
    callbacks, errors, successes = [], [], []
    AsyncClient.last_instance.add_response_callback = lambda callback, filter: callbacks.append((callback, filter))
    await client.async_start_listener(lambda err: errors.append(str(err)), lambda: successes.append(True))
    try:
        for response in (SyncError("M_LIMIT_EXCEEDED"), SyncError(None), SyncResponse()):
            if getattr(response, "status_code", None) is None:
                response.transport_response = types.SimpleNamespace(status=429)
            for callback, response_type in callbacks:
                if isinstance(response, response_type):
                    await callback(response)
        assert errors == []
        assert successes == []
    finally:
        await client.async_close()

@pytest.mark.asyncio
async def test_sync_error_retry_delay_is_bounded(client_module):
    import asyncio

    client = make_client(client_module)
    delays = []
    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        delays.append(delay)
        await real_sleep(0)

    client_module.asyncio.sleep = fast_sleep
    try:
        for _ in range(7):
            await client._async_sync_response(SyncError("502"))
        assert delays == [5, 10, 20, 40, 60, 60, 60]
    finally:
        client_module.asyncio.sleep = real_sleep

@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["send", "upload", "alias"])
@pytest.mark.parametrize("status,expected", [(502, "MatrixConnectionError"), (403, "MatrixSendError"), (501, "MatrixSendError")])
async def test_server_error_classification_preserves_retryable_delivery(client_module, operation, status, expected):
    client = make_client(client_module)
    nio_client = AsyncClient.last_instance
    error = ErrorResponse()
    error.message = "server error"
    error.status_code = "M_UNKNOWN"
    error.transport_response = types.SimpleNamespace(status=status)
    if operation == "send":
        nio_client.room_send_response = error
        call = client.async_send_prepared([client_module.PreparedRoom("!room:example", True)], {})
    elif operation == "upload":
        async def upload(*args, **kwargs):
            return error, None
        nio_client.upload = upload
        call = client.async_upload(b"content", filename="a", content_type="text/plain")
    else:
        nio_client.room_resolve_response = error
        call = client.async_resolve_room("#room:example")
    with pytest.raises(getattr(client_module, expected)):
        await call

@pytest.mark.asyncio
async def test_listener_observer_exceptions_do_not_stop_sync(client_module):
    import asyncio
    client = make_client(client_module)
    real_sleep = asyncio.sleep
    async def fast_sleep(delay):
        await real_sleep(0)
    def broken(*args):
        raise RuntimeError("observer failed")
    client_module.asyncio.sleep = fast_sleep
    try:
        await client.async_start_listener(broken, broken)
        await client._async_sync_response(SyncError("M_UNKNOWN"))
        await client._async_sync_response(SyncResponse())
        assert not client._sync_task.done()
    finally:
        await client.async_close()
        client_module.asyncio.sleep = real_sleep

@pytest.mark.asyncio
async def test_sync_observer_cancellation_propagates(client_module):
    import asyncio
    client = make_client(client_module)
    async def cancelled():
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await client._async_notify_sync_observer(cancelled)
