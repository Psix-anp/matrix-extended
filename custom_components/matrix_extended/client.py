"""Matrix client wrapper for Matrix Extended."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
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
    safe_action_executor: Any = None
    panel_manager: Any = None


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
        if not self._login_restored:
            await asyncio.to_thread(
                self._client.restore_login,
                user_id=self._login_user_id,
                device_id=self._login_device_id,
                access_token=self._login_access_token,
            )
            self._login_restored = True
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
        """Resolve a room alias to a room ID, caching successful aliases."""
        if room.startswith("!"):
            return room
        if not room.startswith("#"):
            raise MatrixSendError("Matrix room must start with '#' or '!'")
        if cached := self._room_cache.get(room):
            return cached
        try:
            response = await self._client.room_resolve_alias(room)
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, RoomResolveAliasResponse):
            raise MatrixSendError(f"Unable to resolve room {room}: {_error_text(response)}")
        self._room_cache[room] = response.room_id
        return response.room_id

    async def async_get_event(
        self, room: str, event_id: str
    ) -> dict[str, Any] | None:
        """Fetch one room event; return None only when Matrix reports it missing."""
        room_id = await self.async_resolve_room(room)
        try:
            response = await self._client.room_get_event(room_id, event_id)
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if isinstance(response, ErrorResponse):
            if getattr(response, "status_code", None) == "M_NOT_FOUND":
                return None
            raise MatrixSendError(
                f"Unable to fetch Matrix event {event_id}: {_error_text(response)}"
            )
        event = getattr(response, "event", None)
        source = getattr(event, "source", None)
        if not isinstance(source, Mapping):
            raise MatrixSendError(f"Matrix event {event_id} has no event source")
        return dict(source)

    async def async_get_state_event(
        self,
        room: str,
        event_type: str,
        *,
        state_key: str = "",
    ) -> dict[str, Any] | None:
        """Fetch one room state event; return None only when state is absent."""
        room_id = await self.async_resolve_room(room)
        try:
            response = await self._client.room_get_state_event(
                room_id, event_type, state_key
            )
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if isinstance(response, ErrorResponse):
            if getattr(response, "status_code", None) == "M_NOT_FOUND":
                return None
            raise MatrixSendError(
                f"Unable to fetch Matrix state {event_type}: {_error_text(response)}"
            )
        content = getattr(response, "content", None)
        if not isinstance(content, Mapping):
            raise MatrixSendError(f"Matrix state {event_type} has no content")
        return dict(content)

    async def async_put_state_event(
        self,
        room: str,
        event_type: str,
        content: Mapping[str, Any],
        *,
        state_key: str = "",
    ) -> str | None:
        """Write one Matrix room-state event and return its event ID."""
        room_id = await self.async_resolve_room(room)
        try:
            response = await self._client.room_put_state(
                room_id,
                event_type,
                dict(content),
                state_key=state_key,
            )
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if isinstance(response, ErrorResponse):
            raise MatrixSendError(
                f"Unable to write Matrix state {event_type}: {_error_text(response)}"
            )
        return getattr(response, "event_id", None)

    async def async_pin_event(self, room: str, event_id: str) -> bool:
        """Append one pin without deleting unrelated pinned events."""
        state = await self.async_get_state_event(room, "m.room.pinned_events") or {}
        raw_pins = state.get("pinned", [])
        pins = (
            [str(item) for item in raw_pins if isinstance(item, str) and item]
            if isinstance(raw_pins, list)
            else []
        )
        if event_id in pins:
            return False
        pins.append(event_id)
        await self.async_put_state_event(
            room,
            "m.room.pinned_events",
            {"pinned": pins},
        )
        return True

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
            response, decryption_info = await self._client.upload(
                io.BytesIO(data),
                content_type=content_type,
                filename=filename,
                filesize=len(data),
                encrypt=encrypt,
            )
        except Exception as err:
            raise MatrixConnectionError(str(err)) from err
        if not isinstance(response, UploadResponse):
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
            try:
                response = await self._client.room_send(**send_kwargs)
            except Exception as err:
                raise MatrixConnectionError(str(err)) from err
            if isinstance(response, ErrorResponse):
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
            response = await self._client.room_redact(
                room_id, event_id, reason=reason
            )
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
            response = await self._client.download(mxc=mxc_uri)
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
