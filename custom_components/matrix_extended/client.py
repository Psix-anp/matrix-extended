"""Matrix client wrapper for Matrix Extended."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import inspect
import io
from typing import Any

from nio import AsyncClient, AsyncClientConfig
from nio.responses import (
    ErrorResponse,
    LoginResponse,
    RoomResolveAliasResponse,
    SyncResponse,
    UploadResponse,
    WhoamiResponse,
)


class MatrixExtendedError(Exception):
    """Base Matrix Extended transport error."""


class MatrixAuthenticationError(MatrixExtendedError):
    """Authentication failed."""


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
    access_token: str
    device_id: str


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
    incoming_policy: Any = None
    rooms: list[Any] = None
    routing_profiles: dict[str, list[str]] = None
    notification_registry: Any = None
    notification_store: Any = None
    entry_id: str = ""
    default_room_id: str = ""


def _error_text(response: Any) -> str:
    status = getattr(response, "status_code", None)
    message = getattr(response, "message", None) or str(response)
    return f"{status}: {message}" if status else message


async def async_password_login(
    homeserver: str,
    user_id: str,
    password: str,
    verify_ssl: bool,
) -> LoginDetails:
    """Log in once and return token/device details without retaining password."""
    client = AsyncClient(homeserver, user_id, ssl=verify_ssl)
    try:
        response = await client.login(
            password=password,
            device_name="Home Assistant Matrix Extended",
        )
        if not isinstance(response, LoginResponse):
            raise MatrixAuthenticationError(_error_text(response))
        return LoginDetails(
            user_id=response.user_id,
            access_token=response.access_token,
            device_id=response.device_id,
        )
    except MatrixAuthenticationError:
        raise
    except Exception as err:
        raise MatrixConnectionError(str(err)) from err
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
    ) -> None:
        config = AsyncClientConfig(
            encryption_enabled=True,
            store_sync_tokens=True,
            pickle_key=store_key,
        )
        self._client = AsyncClient(
            homeserver,
            user_id,
            device_id=device_id,
            store_path=store_path,
            config=config,
            ssl=verify_ssl,
        )
        self._client.restore_login(
            user_id=user_id,
            device_id=device_id,
            access_token=access_token,
        )
        self._room_cache: dict[str, str] = {}
        self._require_e2ee = require_e2ee
        self._sync_task: asyncio.Task[Any] | None = None

    async def _async_sync(self, *, full_state: bool = False) -> None:
        try:
            response = await self._client.sync(
                timeout=0,
                full_state=full_state,
                set_presence="offline",
            )
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, SyncResponse):
            raise MatrixConnectionError(f"Matrix sync failed: {_error_text(response)}")

    async def _async_crypto_housekeeping(self) -> None:
        """Run the key maintenance normally performed by sync_forever."""
        if self._client.should_upload_keys:
            try:
                response = await self._client.keys_upload()
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
                response = await self._client.keys_query()
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
                response = await self._client.keys_claim(
                    self._client.get_users_for_key_claiming()
                )
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
        try:
            response = await self._client.whoami()
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, WhoamiResponse):
            status = getattr(response, "status_code", None)
            if status in (401, 403):
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

    async def async_start_listener(self, on_error: Any = None) -> None:
        """Start resilient long-poll sync for inbound events and E2EE key traffic."""
        if self._sync_task is not None and not self._sync_task.done():
            return

        async def runner() -> None:
            while True:
                try:
                    await self._client.sync_forever(
                        timeout=30000,
                        set_presence="offline",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # pragma: no cover - transport dependent
                    if on_error is not None:
                        result = on_error(err)
                        if inspect.isawaitable(result):
                            await result
                    await asyncio.sleep(5)

        self._sync_task = asyncio.create_task(
            runner(), name="matrix_extended_sync"
        )
        await asyncio.sleep(0)

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
        """Resolve room aliases while preserving room IDs."""
        if room.startswith("!"):
            return room
        if room in self._room_cache:
            return self._room_cache[room]
        try:
            response = await self._client.room_resolve_alias(room)
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, RoomResolveAliasResponse):
            raise MatrixSendError(f"Unable to resolve {room}: {_error_text(response)}")
        self._room_cache[room] = response.room_id
        return response.room_id

    async def async_room_encrypted(self, room: str, *, sync: bool = True) -> bool:
        """Return whether a room is encrypted after a state sync."""
        room_id = await self.async_resolve_room(room)
        if sync:
            await self._async_sync(full_state=True)
        nio_room = self._client.rooms.get(room_id)
        if nio_room is None:
            raise MatrixEncryptionError(
                f"Room {room} ({room_id}) is not available in the current Matrix state"
            )
        return bool(nio_room.encrypted)

    async def async_prepare_rooms(self, rooms: list[str]) -> list[PreparedRoom]:
        """Resolve targets, sync once, and enforce the E2EE policy."""
        room_ids = [await self.async_resolve_room(room) for room in rooms]
        await self._async_sync(full_state=True)
        await self._async_crypto_housekeeping()
        prepared: list[PreparedRoom] = []
        for original, room_id in zip(rooms, room_ids, strict=True):
            nio_room = self._client.rooms.get(room_id)
            if nio_room is None:
                raise MatrixEncryptionError(
                    f"Room {original} ({room_id}) is not available in the current Matrix state"
                )
            encrypted = bool(nio_room.encrypted)
            if self._require_e2ee and not encrypted:
                raise MatrixEncryptionRequiredError(
                    f"Refusing to send to unencrypted Matrix room {original}; Require E2EE is enabled"
                )
            prepared.append(PreparedRoom(room_id=room_id, encrypted=encrypted))
        return prepared

    async def async_send_prepared(
        self,
        rooms: list[PreparedRoom],
        content: dict[str, Any],
        *,
        event_type: str = "m.room.message",
    ) -> list[str | None]:
        """Send content to rooms that already passed state and E2EE checks."""
        event_ids: list[str | None] = []
        for room in rooms:
            try:
                response = await self._client.room_send(
                    room_id=room.room_id,
                    message_type=event_type,
                    content=content,
                    ignore_unverified_devices=True,
                )
            except Exception as err:
                raise MatrixSendError(str(err)) from err
            if isinstance(response, ErrorResponse):
                raise MatrixSendError(_error_text(response))
            event_ids.append(getattr(response, "event_id", None))
        return event_ids

    async def async_send_content(
        self,
        room: str,
        content: dict[str, Any],
        *,
        event_type: str = "m.room.message",
    ) -> str | None:
        """Convenience wrapper for sending one event to one room."""
        prepared = await self.async_prepare_rooms([room])
        return (await self.async_send_prepared(prepared, content, event_type=event_type))[0]

    async def async_redact_event(
        self,
        *,
        room: str,
        event_id: str,
        reason: str | None = None,
    ) -> None:
        """Redact one Matrix event."""
        prepared = await self.async_prepare_rooms([room])
        try:
            response = await self._client.room_redact(
                prepared[0].room_id,
                event_id,
                reason=reason,
            )
        except Exception as err:
            raise MatrixSendError(str(err)) from err
        if isinstance(response, ErrorResponse):
            raise MatrixSendError(_error_text(response))

    async def async_upload_media(self, media: Any) -> UploadedMedia:
        """Upload a ResolvedMedia item, encrypted when requested by the caller."""
        encrypt = bool(getattr(media, "encrypt", True))
        try:
            response, encryption_info = await self._client.upload(
                io.BytesIO(media.data),
                content_type=media.content_type,
                filename=media.filename,
                encrypt=encrypt,
                filesize=len(media.data),
            )
        except Exception as err:
            raise MatrixSendError(str(err)) from err
        if not isinstance(response, UploadResponse):
            raise MatrixSendError(_error_text(response))
        encrypted_file = None
        if encryption_info is not None:
            encrypted_file = {
                "url": response.content_uri,
                "key": encryption_info["key"],
                "iv": encryption_info["iv"],
                "hashes": encryption_info["hashes"],
                "v": "v2",
            }
        media.uploaded = UploadedMedia(
            mxc_uri=response.content_uri,
            encrypted_file=encrypted_file,
        )
        return media.uploaded
