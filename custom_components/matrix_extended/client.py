"""Matrix client wrapper for Matrix Extended."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
import inspect
import io
import json
import logging
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from nio import AsyncClient, AsyncClientConfig
from nio.responses import (
    ErrorResponse,
    LoginResponse,
    RoomResolveAliasResponse,
    SyncError,
    SyncResponse,
    UploadResponse,
    WhoamiResponse,
)

_LOGGER = logging.getLogger(__name__)


class MatrixExtendedError(Exception):
    """Base Matrix Extended transport error."""


class MatrixAuthenticationError(MatrixExtendedError):
    """Authentication failed."""

    def __init__(self, message: str, *, soft_logout: bool = False) -> None:
        super().__init__(message)
        self.soft_logout = soft_logout


class MatrixConnectionError(MatrixExtendedError):
    """Homeserver communication failed."""


class MatrixSendError(MatrixExtendedError):
    """A Matrix upload or send failed."""


class MatrixEncryptionError(MatrixExtendedError):
    """Matrix encryption could not be initialized or used."""


class MatrixEncryptionRequiredError(MatrixEncryptionError):
    """The configured security policy requires an encrypted room."""


@dataclass(slots=True)
class LoginDetails:
    """Persistable Matrix login details."""

    user_id: str
    access_token: str = field(repr=False)
    device_id: str
    refresh_token: str | None = field(default=None, repr=False)


@dataclass(slots=True, frozen=True)
class PreparedRoom:
    """Resolved Matrix room with its encryption state."""

    room_id: str
    encrypted: bool


@dataclass(slots=True, frozen=True)
class UploadedMedia:
    """Result of a Matrix media upload."""

    mxc_uri: str
    encrypted_file: dict[str, Any] | None = None


@dataclass(slots=True)
class MatrixAccount:
    """Runtime account data."""

    client: "MatrixClient"
    default_room: str
    user_id: str = ""
    device_id: str = ""
    homeserver: str = ""
    status: Any = None
    action_registry: Any = None
    command_registry: Any = None
    incoming_policy: Any = None
    rooms: list[Any] = None
    routing_profiles: dict[str, list[str]] = None
    notification_registry: Any = None
    notification_store: Any = None
    outbox: Any = None
    outbox_task: Any = None
    entry_id: str = ""
    default_room_id: str = ""


def _error_text(response: Any) -> str:
    status = getattr(response, "status_code", None)
    message = getattr(response, "message", None) or str(response)
    return f"{status}: {message}" if status else message


def _http_status(response: Any) -> Any:
    return getattr(getattr(response, "transport_response", None), "status", None)


def _raise_transient_server_error(response: Any, message: str) -> None:
    """Keep server failures retryable for the persistent outbox."""
    if _http_status(response) in (500, 502, 503, 504):
        raise MatrixConnectionError(f"{message}: {_error_text(response)}")


async def async_password_login(
    homeserver: str,
    user_id: str,
    password: str,
    verify_ssl: bool,
    *,
    device_id: str | None = None,
) -> LoginDetails:
    """Log in once and return token/device details without retaining password."""
    client = AsyncClient(homeserver, user_id, ssl=verify_ssl)
    try:
        body = {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": user_id},
            "password": password,
            "initial_device_display_name": "Home Assistant Matrix Extended",
            "refresh_token": True,
        }
        if device_id:
            body["device_id"] = device_id
        if hasattr(client, "client_session"):
            async with ClientSession(timeout=ClientTimeout(total=60)) as session:
                async with session.post(
                    homeserver.rstrip("/") + "/_matrix/client/v3/login",
                    json=body, ssl=verify_ssl, allow_redirects=False,
                ) as http:
                    if http.status == 429 or http.status >= 500 or 300 <= http.status < 400:
                        raise MatrixConnectionError("Matrix login unavailable")
                    try:
                        payload = await http.json()
                    except Exception:
                        raise MatrixConnectionError("Invalid Matrix login response") from None
                    if not isinstance(payload, dict):
                        raise MatrixConnectionError("Invalid Matrix login response")
                    if http.status < 200 or http.status >= 300:
                        if payload.get("errcode") in ("M_FORBIDDEN", "M_UNAUTHORIZED", "M_USER_DEACTIVATED"):
                            raise MatrixAuthenticationError("Matrix login rejected")
                        raise MatrixConnectionError("Matrix login unavailable")
                    if not all(isinstance(payload.get(key), str) and payload[key] for key in ("user_id", "device_id", "access_token")):
                        raise MatrixConnectionError("Invalid Matrix login response")
                    refresh_token = payload.get("refresh_token")
                    if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token):
                        raise MatrixConnectionError("Invalid Matrix login response")
                    return LoginDetails(
                        user_id=payload["user_id"], device_id=payload["device_id"],
                        access_token=payload["access_token"], refresh_token=refresh_token,
                    )
        if hasattr(client, "login_raw"):
            response = await client.login_raw(body)
        else:
            response = await client.login(password=password, device_name="Home Assistant Matrix Extended")
        if not isinstance(response, LoginResponse):
            if _http_status(response) in (429, 500, 502, 503, 504):
                raise MatrixConnectionError("Matrix login unavailable")
            raise MatrixAuthenticationError("Matrix login rejected")
        transport = getattr(response, "transport_response", None)
        payload = await transport.json() if transport is not None else {}
        return LoginDetails(
            user_id=response.user_id,
            access_token=response.access_token,
            device_id=response.device_id,
            refresh_token=payload.get("refresh_token"),
        )
    except MatrixExtendedError:
        raise
    except Exception:
        raise MatrixConnectionError("Matrix login unavailable") from None
    finally:
        await client.close()


class MatrixClient:
    """Outbound Matrix client with persistent E2EE state."""

    def __init__(
        self,
        *,
        homeserver: str,
        user_id: str,
        access_token: str,
        device_id: str,
        verify_ssl: bool,
        store_path: str,
        store_key: str,
        require_e2ee: bool = True,
        refresh_token: str | None = None,
        on_credentials_updated: Any = None,
        on_auth_failed: Any = None,
    ) -> None:
        config = AsyncClientConfig(
            encryption_enabled=True,
            store_sync_tokens=True,
            pickle_key=store_key,
            max_timeouts=0,
        )
        self._client = AsyncClient(
            homeserver,
            user_id,
            device_id=device_id,
            store_path=store_path,
            config=config,
            ssl=verify_ssl,
        )
        self._login_user_id = user_id
        self._login_device_id = device_id
        self._login_access_token = access_token
        self._login_restored = False
        self._refresh_token = refresh_token
        self._on_credentials_updated = on_credentials_updated
        self._on_auth_failed = on_auth_failed
        self._refresh_lock = asyncio.Lock()
        self._credentials_pending = False
        self._definitive_auth_error: MatrixAuthenticationError | None = None
        self._room_cache: dict[str, str] = {}
        self._require_e2ee = require_e2ee
        self._sync_task: asyncio.Task[Any] | None = None
        self._sync_callbacks_registered = False
        self._sync_on_error: Any = None
        self._sync_on_success: Any = None
        self._sync_retry_delay = 5
        self._listener_auth_failed = False
        self._send_failures: ContextVar[Any] = ContextVar("matrix_send_failures", default=None)
        # Intercept nio's individual requests, including key distribution inside
        # room_send and concurrent background sync requests.
        nio_send = getattr(self._client, "_send", None)
        if callable(nio_send):
            async def authenticated_send(*args: Any, **kwargs: Any) -> Any:
                failures = self._send_failures.get()
                if failures:
                    raise failures[0]
                try:
                    if kwargs.get("data_provider") is not None:
                        return await nio_send(*args, **kwargs)
                    result = await self._request(nio_send, *args, **kwargs)
                    response_type = getattr(args[0], "__name__", "") if args else ""
                    if failures is not None and response_type in {
                        "ShareGroupSessionResponse", "KeysClaimResponse", "KeysQueryResponse", "JoinedMembersResponse"
                    } and isinstance(result, ErrorResponse):
                        error = MatrixConnectionError("Matrix key distribution failed")
                        failures.append(error)
                        raise error
                    return result
                except Exception as err:
                    if failures is not None and not failures:
                        failures.append(err if isinstance(err, MatrixExtendedError) else MatrixConnectionError("Matrix request failed"))
                    raise
            self._client._send = authenticated_send

        nio_share = getattr(self._client, "share_group_session", None)
        if callable(nio_share):
            async def safe_share(room_id: str, *args: Any, **kwargs: Any) -> Any:
                sharing = self._client.sharing_session
                previous = sharing.get(room_id)
                try:
                    return await nio_share(room_id, *args, **kwargs)
                except BaseException:
                    # nio 0.26 creates this event synchronously before its first
                    # await, but its keys_claim await precedes nio's finally.
                    # A pre-existing event belongs to another invocation.
                    event = sharing.get(room_id)
                    if previous is None and event is not None:
                        if sharing.get(room_id) is event:
                            sharing.pop(room_id)
                            event.set()
                    raise
            self._client.share_group_session = safe_share

    @staticmethod
    def _is_expired(response: Any) -> bool:
        return getattr(response, "status_code", None) in ("M_UNKNOWN_TOKEN", 401)

    async def _async_recover_auth(self, response: Any, used_token: str) -> None:
        async with self._refresh_lock:
            if self._definitive_auth_error is not None:
                raise self._definitive_auth_error
            if self._credentials_pending:
                await self._persist_credentials()
            if self._login_access_token != used_token:
                self._client.access_token = self._login_access_token
                return
            if not self._refresh_token:
                await self._auth_failed(response)
            try:
                http = await self._credential_request(
                    "/_matrix/client/v3/refresh", {"refresh_token": self._refresh_token}
                )
                try:
                    if http.status == 429 or http.status >= 500:
                        raise MatrixConnectionError("Matrix token refresh unavailable")
                    try:
                        payload = await http.json()
                    except Exception:
                        raise MatrixConnectionError("Invalid Matrix token refresh response") from None
                finally:
                    release = getattr(http, "release", None)
                    if callable(release):
                        release()
                if not isinstance(payload, dict):
                    raise MatrixConnectionError("Invalid Matrix token refresh response")
                if payload.get("errcode") in ("M_UNKNOWN_TOKEN", "M_MISSING_TOKEN", "M_FORBIDDEN"):
                    await self._auth_failed(response, soft_logout=payload.get("soft_logout") is True)
                if http.status < 200 or http.status >= 300:
                    raise MatrixConnectionError("Matrix token refresh unavailable")
                access = payload.get("access_token")
                refresh = payload.get("refresh_token", self._refresh_token)
                if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
                    raise MatrixConnectionError("Invalid Matrix token refresh response")
                self._login_access_token = access
                self._refresh_token = refresh
                self._credentials_pending = True
                await self._persist_credentials()
            except MatrixAuthenticationError:
                raise
            except Exception:
                self._client.access_token = used_token if self._credentials_pending else self._login_access_token
                raise MatrixConnectionError("Matrix token refresh unavailable") from None

    async def _credential_request(self, path: str, payload: dict[str, Any]) -> Any:
        session = getattr(self._client, "client_session", None)
        if session is not None:
            return await session.request(
                "POST", self._client.homeserver + path, json=payload,
                ssl=self._client.ssl, allow_redirects=False,
                timeout=self._client.config.request_timeout,
            )
        return await self._client.send(
            "POST", path, json.dumps(payload), {"Content-Type": "application/json"}
        )

    async def _persist_credentials(self) -> None:
        try:
            if self._on_credentials_updated is not None:
                await self._on_credentials_updated(self._login_access_token, self._refresh_token)
        except Exception:
            raise MatrixConnectionError("Unable to persist Matrix credentials") from None
        self._client.access_token = self._login_access_token
        self._credentials_pending = False

    async def _auth_failed(self, response: Any, *, soft_logout: bool | None = None) -> None:
        if self._definitive_auth_error is None:
            code = getattr(response, "status_code", None)
            detail = "bad token" if code == 401 else "M_UNKNOWN_TOKEN"
            if soft_logout is None:
                soft_logout = getattr(response, "soft_logout", False) is True
            self._definitive_auth_error = MatrixAuthenticationError(
                f"Matrix session expired: {detail}", soft_logout=soft_logout
            )
            if self._on_auth_failed is not None:
                await self._on_auth_failed(self._definitive_auth_error)
        raise self._definitive_auth_error

    async def _request(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        if self._definitive_auth_error is not None:
            raise self._definitive_auth_error
        if self._credentials_pending:
            async with self._refresh_lock:
                if self._credentials_pending:
                    await self._persist_credentials()
        used_token = self._login_access_token
        if not getattr(self._client, "access_token", used_token):
            self._client.access_token = used_token
        response = await operation(*args, **kwargs)
        actual = response[0] if isinstance(response, tuple) else response
        if self._is_expired(actual):
            await self._async_recover_auth(actual, used_token)
            for arg in args:
                if isinstance(arg, io.BytesIO):
                    arg.seek(0)
            response = await operation(*args, **kwargs)
            actual = response[0] if isinstance(response, tuple) else response
            if self._is_expired(actual):
                await self._auth_failed(actual)
        return response

    async def _async_sync(self, *, full_state: bool = False) -> None:
        try:
            response = await self._request(self._client.sync,
                timeout=0,
                full_state=full_state,
                set_presence="offline",
            )
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, SyncResponse):
            raise MatrixConnectionError(f"Matrix sync failed: {_error_text(response)}")

    async def _async_crypto_housekeeping(self) -> None:
        """Run the key maintenance normally performed by sync_forever."""
        if self._client.should_upload_keys:
            try:
                response = await self._request(self._client.keys_upload, )
            except MatrixExtendedError:
                raise
            except Exception as err:
                raise MatrixEncryptionError(
                    f"Unable to upload E2EE device keys: {err}"
                ) from err
            if isinstance(response, ErrorResponse):
                raise MatrixEncryptionError(
                    f"Unable to upload E2EE device keys: {_error_text(response)}"
                )

        if self._client.should_query_keys:
            try:
                response = await self._request(self._client.keys_query, )
            except MatrixExtendedError:
                raise
            except Exception as err:
                raise MatrixEncryptionError(
                    f"Unable to query Matrix device keys: {err}"
                ) from err
            if isinstance(response, ErrorResponse):
                raise MatrixEncryptionError(
                    f"Unable to query Matrix device keys: {_error_text(response)}"
                )

        if self._client.should_claim_keys:
            try:
                response = await self._request(self._client.keys_claim,
                    self._client.get_users_for_key_claiming()
                )
            except MatrixExtendedError:
                raise
            except Exception as err:
                raise MatrixEncryptionError(
                    f"Unable to claim Matrix one-time keys: {err}"
                ) from err
            if isinstance(response, ErrorResponse):
                raise MatrixEncryptionError(
                    f"Unable to claim Matrix one-time keys: {_error_text(response)}"
                )

    async def async_connect(self, default_room: str | None = None) -> bool | None:
        """Verify login, load room state, and initialize E2EE keys."""
        if not self._login_restored:
            await asyncio.to_thread(
                self._client.restore_login,
                user_id=self._login_user_id,
                device_id=self._login_device_id,
                access_token=self._login_access_token,
            )
            self._login_restored = True
        try:
            response = await self._request(self._client.whoami)
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, WhoamiResponse):
            status = getattr(response, "status_code", None)
            if status == 401:
                raise MatrixAuthenticationError(_error_text(response))
            raise MatrixConnectionError(_error_text(response))

        await self._async_sync(full_state=True)
        await self._async_crypto_housekeeping()
        if default_room is None:
            return None
        return await self.async_room_encrypted(default_room, sync=False)

    def rooms_snapshot(self) -> list[Any]:
        """Return a stable snapshot of joined room metadata after sync."""
        try:
            from .rooms import room_info_from_nio
        except ImportError:  # pragma: no cover - standalone unit loader fallback
            def room_info_from_nio(room: Any) -> Any:
                class RoomInfo:
                    pass
                info = RoomInfo()
                info.room_id = str(room.room_id)
                info.display_name = str(getattr(room, "display_name", "") or room.room_id)
                alias = getattr(room, "canonical_alias", None)
                info.canonical_alias = str(alias) if alias else None
                info.encrypted = bool(getattr(room, "encrypted", False))
                info.joined_count = int(getattr(room, "joined_count", 0) or 0)
                return info

        return [
            room_info_from_nio(room)
            for _, room in sorted(self._client.rooms.items(), key=lambda item: item[0])
        ]

    def add_event_callback(self, callback: Any, event_filter: Any) -> None:
        """Register a matrix-nio room event callback."""
        self._client.add_event_callback(callback, event_filter)

    async def async_start_listener(
        self, on_error: Any = None, on_success: Any = None
    ) -> None:
        """Start resilient long-poll sync for inbound events and E2EE key traffic."""
        if self._sync_task is not None and not self._sync_task.done():
            return

        self._listener_auth_failed = False
        self._sync_on_error = on_error
        self._sync_on_success = on_success
        if not self._sync_callbacks_registered:
            self._client.add_response_callback(
                self._async_sync_response, (SyncResponse, SyncError)
            )
            self._sync_callbacks_registered = True

        async def runner() -> None:
            while True:
                try:
                    await self._client.sync_forever(
                        timeout=30000,
                        set_presence="offline",
                    )
                    if self._listener_auth_failed:
                        return
                except asyncio.CancelledError:
                    raise
                except MatrixAuthenticationError as err:
                    self._listener_auth_failed = True
                    await self._async_notify_sync_observer(self._sync_on_error, err)
                    return
                except Exception as err:  # pragma: no cover - transport dependent
                    await self._async_sync_failure(err)

        self._sync_task = asyncio.create_task(
            runner(), name="matrix_extended_sync"
        )
        await asyncio.sleep(0)

    async def _async_sync_response(self, response: Any) -> None:
        """Observe background sync responses; let nio handle rate limits."""
        if _http_status(response) == 429:
            return
        if isinstance(response, SyncError):
            if self._is_expired(response):
                try:
                    transport = getattr(response, "transport_response", None)
                    request_info = getattr(transport, "request_info", None)
                    headers = getattr(request_info, "headers", {})
                    authorization = headers.get("Authorization", "")
                    used_token = authorization[7:] if authorization.startswith("Bearer ") else self._login_access_token
                    await self._async_recover_auth(response, used_token)
                except MatrixAuthenticationError as err:
                    self._listener_auth_failed = True
                    await self._async_sync_failure(err)
                    self._client.stop_sync_forever()
                except MatrixConnectionError as err:
                    await self._async_sync_failure(err)
                return
            if getattr(response, "status_code", None) in (429, "M_LIMIT_EXCEEDED"):
                return
            await self._async_sync_failure(
                MatrixConnectionError(f"Matrix sync failed: {_error_text(response)}")
            )
            return
        if isinstance(response, SyncResponse):
            self._sync_retry_delay = 5
            await self._async_notify_sync_observer(self._sync_on_success)

    async def _async_notify_sync_observer(self, callback: Any, *args: Any) -> None:
        if callback is None:
            return
        try:
            result = callback(*args)
            if inspect.isawaitable(result):
                await result
        except Exception:
            _LOGGER.exception("Matrix sync status observer failed")

    async def _async_sync_failure(self, error: Exception) -> None:
        """Report a sync failure and limit retry frequency."""
        await self._async_notify_sync_observer(self._sync_on_error, error)
        delay = self._sync_retry_delay
        self._sync_retry_delay = min(delay * 2, 60)
        await asyncio.sleep(delay)

    async def async_close(self) -> None:
        """Stop sync and close the nio HTTP session."""
        stop = getattr(self._client, "stop_sync_forever", None)
        if callable(stop):
            stop()
        if self._sync_task is not None:
            self._sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None
        await self._client.close()

    async def async_resolve_room(self, room: str) -> str:
        """Resolve a room alias to a room ID, caching successful aliases."""
        if room.startswith("!"):
            return room
        if not room.startswith("#"):
            raise MatrixSendError("Matrix room must start with '#' or '!'")
        if cached := self._room_cache.get(room):
            return cached
        try:
            response = await self._request(self._client.room_resolve_alias, room)
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, RoomResolveAliasResponse):
            _raise_transient_server_error(response, f"Unable to resolve room {room}")
            raise MatrixSendError(f"Unable to resolve room {room}: {_error_text(response)}")
        self._room_cache[room] = response.room_id
        return response.room_id

    async def async_room_encrypted(self, room: str, *, sync: bool = True) -> bool:
        """Return whether a joined room has Matrix E2EE enabled."""
        if sync:
            await self._async_sync(full_state=False)
        room_id = await self.async_resolve_room(room)
        nio_room = self._client.rooms.get(room_id)
        if nio_room is None:
            # A stored incremental sync can omit a room that has not yet been
            # materialized in this process. One full sync resolves that case.
            await self._async_sync(full_state=True)
            nio_room = self._client.rooms.get(room_id)
        if nio_room is None:
            raise MatrixSendError(f"Matrix account is not joined to room {room}")
        return bool(nio_room.encrypted)

    async def async_prepare_rooms(self, rooms: list[str]) -> list[PreparedRoom]:
        """Resolve rooms and enforce the configured E2EE policy before sending."""
        listener_running = self._sync_task is not None and not self._sync_task.done()
        if not listener_running:
            await self._async_sync(full_state=False)
            await self._async_crypto_housekeeping()
        prepared: list[PreparedRoom] = []
        for room in rooms:
            room_id = await self.async_resolve_room(room)
            nio_room = self._client.rooms.get(room_id)
            if nio_room is None:
                await self._async_sync(full_state=True)
                nio_room = self._client.rooms.get(room_id)
            if nio_room is None:
                raise MatrixSendError(f"Matrix account is not joined to room {room}")
            encrypted = bool(nio_room.encrypted)
            if self._require_e2ee and not encrypted:
                raise MatrixEncryptionRequiredError(
                    f"Room {room} is not encrypted; Matrix Extended requires E2EE"
                )
            prepared.append(PreparedRoom(room_id=room_id, encrypted=encrypted))
        return prepared

    async def async_upload(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        encrypt: bool = False,
    ) -> UploadedMedia:
        """Upload bytes, optionally encrypted for use in an E2EE room."""
        try:
            response, decryption_info = await self._request(self._client.upload,
                io.BytesIO(data),
                content_type=content_type,
                filename=filename,
                filesize=len(data),
                encrypt=encrypt,
            )
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, UploadResponse):
            _raise_transient_server_error(response, "Matrix media upload failed")
            raise MatrixSendError(f"Matrix media upload failed: {_error_text(response)}")

        if not encrypt:
            return UploadedMedia(mxc_uri=response.content_uri)
        if not decryption_info:
            raise MatrixEncryptionError(
                "Matrix encrypted upload did not return attachment decryption metadata"
            )
        encrypted_file = dict(decryption_info)
        encrypted_file["url"] = response.content_uri
        return UploadedMedia(
            mxc_uri=response.content_uri,
            encrypted_file=encrypted_file,
        )

    async def async_send_event_prepared(
        self,
        rooms: list[PreparedRoom],
        event_type: str,
        content: dict[str, Any],
        *,
        tx_ids: list[str] | None = None,
    ) -> list[str | None]:
        """Send an arbitrary Matrix room event to already prepared rooms."""
        if tx_ids is not None and len(tx_ids) != len(rooms):
            raise ValueError("tx_ids must match prepared rooms")
        results: list[str | None] = []
        for index, room in enumerate(rooms):
            send_kwargs: dict[str, Any] = {
                "room_id": room.room_id,
                "message_type": event_type,
                "content": content,
                "ignore_unverified_devices": True,
            }
            if tx_ids is not None:
                send_kwargs["tx_id"] = tx_ids[index]
            failures: list[Exception] = []
            context_token = self._send_failures.set(failures)
            try:
                response = await self._request(self._client.room_send, **send_kwargs)
                if failures:
                    raise failures[0]
            except Exception as err:
                invalidate = getattr(self._client, "invalidate_outbound_session", None)
                if room.encrypted and callable(invalidate):
                    invalidate(room.room_id)
                if isinstance(err, MatrixExtendedError):
                    raise
                raise MatrixConnectionError("Matrix send failed") from None
            finally:
                self._send_failures.reset(context_token)
            if isinstance(response, ErrorResponse):
                _raise_transient_server_error(response, f"Matrix send failed for {room.room_id}")
                raise MatrixSendError(
                    f"Matrix send failed for {room.room_id}: {_error_text(response)}"
                )
            results.append(getattr(response, "event_id", None))
        return results

    async def async_send_prepared(
        self,
        rooms: list[PreparedRoom],
        content: dict[str, Any],
        *,
        tx_ids: list[str] | None = None,
    ) -> list[str | None]:
        """Send m.room.message content to already-resolved rooms."""
        return await self.async_send_event_prepared(
            rooms, "m.room.message", content, tx_ids=tx_ids
        )

    async def async_send_event(
        self, room: str, event_type: str, content: dict[str, Any]
    ) -> str | None:
        """Prepare a room and send an arbitrary Matrix event."""
        prepared = await self.async_prepare_rooms([room])
        return (await self.async_send_event_prepared(prepared, event_type, content))[0]

    async def async_redact(
        self, room: str, event_id: str, *, reason: str | None = None
    ) -> None:
        """Redact one event in an authorized target room."""
        prepared = await self.async_prepare_rooms([room])
        room_id = prepared[0].room_id
        try:
            response = await self._request(self._client.room_redact,
                room_id, event_id, reason=reason
            )
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if isinstance(response, ErrorResponse):
            raise MatrixSendError(
                f"Matrix redaction failed for {event_id}: {_error_text(response)}"
            )

    async def async_download_media(
        self,
        mxc_uri: str,
        *,
        encrypted_file: dict[str, Any] | None = None,
    ) -> tuple[bytes, str | None, str | None]:
        """Download a Matrix media object and decrypt it locally when needed."""
        try:
            response = await self._request(self._client.download, mxc=mxc_uri)
        except MatrixExtendedError:
            raise
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if isinstance(response, ErrorResponse) or not hasattr(response, "body"):
            raise MatrixSendError(
                f"Matrix media download failed: {_error_text(response)}"
            )
        data = bytes(response.body)
        if encrypted_file is not None:
            try:
                from nio.crypto.attachments import decrypt_attachment

                data = decrypt_attachment(
                    data,
                    encrypted_file["key"]["k"],
                    encrypted_file["hashes"]["sha256"],
                    encrypted_file["iv"],
                )
            except MatrixExtendedError:
                raise
            except Exception as err:
                raise MatrixEncryptionError(
                    f"Unable to decrypt Matrix attachment: {err}"
                ) from err
        return (
            data,
            getattr(response, "content_type", None),
            getattr(response, "filename", None),
        )

    async def async_send_content(self, room: str, content: dict[str, Any]) -> str | None:
        """Prepare and send one m.room.message event."""
        prepared = await self.async_prepare_rooms([room])
        return (await self.async_send_prepared(prepared, content))[0]

    async def async_send_many(
        self, rooms: list[str], content: dict[str, Any]
    ) -> list[str | None]:
        """Prepare and send the same event content to multiple rooms."""
        prepared = await self.async_prepare_rooms(rooms)
        return await self.async_send_prepared(prepared, content)
