"""Matrix Extended Home Assistant integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from functools import partial
import logging
from pathlib import Path
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .actions import ReactionActionRegistry
from .commands import CommandRegistry
from .client import (
    MatrixAccount,
    MatrixAuthenticationError,
    MatrixClient,
    MatrixConnectionError,
    MatrixEncryptionRequiredError,
    MatrixExtendedError,
    PreparedRoom,
)
from .const import (
    ATTR_ACCOUNT,
    ATTR_ACTIONS,
    ATTR_EVENT_ID,
    ATTR_FORMAT,
    ATTR_MEDIA,
    ATTR_MENTION_ROOM,
    ATTR_MENTION_USERS,
    ATTR_MESSAGE,
    ATTR_MSGTYPE,
    ATTR_NOTIFICATION_KEY,
    ATTR_REACTION,
    ATTR_REASON,
    ATTR_ROUTE,
    ATTR_ROOM,
    ATTR_TARGET,
    ATTR_THREAD_ID,
    CONF_ACCESS_TOKEN,
    CONF_ALLOWED_ROOMS,
    CONF_ALLOWED_USERS,
    CONF_DEFAULT_ROOM,
    CONF_DEVICE_ID,
    CONF_DOWNLOAD_INCOMING_MEDIA,
    CONF_HOMESERVER,
    CONF_INCOMING_ENABLED,
    CONF_INCOMING_MEDIA_MAX_MB,
    CONF_INCOMING_MEDIA_RETENTION_DAYS,
    CONF_REQUIRE_E2EE,
    CONF_ROUTING_PROFILES,
    CONF_STORE_KEY,
    CONF_USER_ID,
    CONF_VERIFY_SSL,
    DEFAULT_INCOMING_MEDIA_MAX_MB,
    DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
    DOMAIN,
    EVENT_DELIVERY,
    FORMAT_HTML,
    FORMAT_MARKDOWN,
    FORMAT_TEXT,
    MEDIA_TYPES,
    MESSAGE_TYPES,
    SERVICE_EDIT,
    SERVICE_REACT,
    SERVICE_REDACT,
    SERVICE_REPLY,
    SERVICE_SEND,
)
from .content import (
    build_edit_content,
    build_media_content,
    build_mentions,
    build_reaction_content,
    build_reply_content,
    build_text_content,
    render_markdown,
    validate_media_item_shape,
)
from .delivery import delivery_event_record, delivery_lifecycle_payload
from .incoming import IncomingPolicy
from .media import MediaResolver
from .notifications import NotificationKeyRegistry
from .outbox import PersistentOutbox, matrix_transaction_id
from .routing import normalize_routing_profiles, resolve_targets
from .receiver import MatrixInboundReceiver
from .status import MatrixRuntimeStatus
from .v05_services import install_v05_services
from .v051_services import install_v051_services

PLATFORMS = [Platform.NOTIFY, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SELECT]
_OUTBOX_RETRY_SECONDS = 5.0
_LOGGER = logging.getLogger(__name__)

_MEDIA_BASE_SCHEMA = vol.Schema(
    {
        vol.Optional("path"): cv.string,
        vol.Optional("url"): cv.url,
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("media_source"): cv.string,
        vol.Optional("type", default="auto"): vol.In(MEDIA_TYPES),
        vol.Optional("filename"): cv.string,
        vol.Optional("caption"): cv.string,
        vol.Optional("formatted_caption"): cv.string,
        vol.Optional("width"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("height"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("duration_ms"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("voice", default=False): cv.boolean,
        vol.Optional("thumbnail"): dict,
    },
    extra=vol.PREVENT_EXTRA,
)

_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required("reaction"): cv.string,
        vol.Required("service"): cv.string,
        vol.Optional("target", default={}): dict,
        vol.Optional("data", default={}): dict,
        vol.Optional("expires_in"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=7 * 24 * 60 * 60)
        ),
        vol.Optional("max_uses"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        vol.Optional("allowed_users"): vol.All(cv.ensure_list, [cv.string]),
    },
    extra=vol.PREVENT_EXTRA,
)


def _validate_media_item(value: Any, *, allow_thumbnail: bool = True) -> dict[str, Any]:
    try:
        item = _MEDIA_BASE_SCHEMA(value)
        item = validate_media_item_shape(item)
    except (vol.Invalid, ValueError) as err:
        raise vol.Invalid(str(err)) from err
    if item.get("formatted_caption") is not None and item.get("caption") is None:
        raise vol.Invalid("formatted_caption requires caption")
    if item.get("voice") and item.get("type") not in {"auto", "audio"}:
        raise vol.Invalid("voice is only supported for audio media")
    if "thumbnail" in item:
        if not allow_thumbnail:
            raise vol.Invalid("nested thumbnails are not supported")
        item["thumbnail"] = _validate_media_item(item["thumbnail"], allow_thumbnail=False)
    return item


SEND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ROUTE): cv.string,
        vol.Optional(ATTR_NOTIFICATION_KEY): cv.string,
        vol.Optional(ATTR_MESSAGE, default=""): cv.string,
        vol.Optional(ATTR_MSGTYPE, default="text"): vol.In(MESSAGE_TYPES),
        vol.Optional(ATTR_FORMAT, default=FORMAT_TEXT): vol.In(
            [FORMAT_TEXT, FORMAT_HTML, FORMAT_MARKDOWN]
        ),
        vol.Optional(ATTR_MENTION_USERS, default=[]): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(ATTR_MENTION_ROOM, default=False): cv.boolean,
        vol.Optional(ATTR_THREAD_ID): cv.string,
        vol.Optional(ATTR_MEDIA, default=[]): vol.All(cv.ensure_list, [_validate_media_item]),
        vol.Optional(ATTR_ACTIONS, default=[]): vol.All(cv.ensure_list, [_ACTION_SCHEMA]),
    }
)

_REPLY_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_ROOM): cv.string,
        vol.Required(ATTR_EVENT_ID): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_MSGTYPE, default="text"): vol.In(MESSAGE_TYPES),
        vol.Optional(ATTR_FORMAT, default=FORMAT_TEXT): vol.In(
            [FORMAT_TEXT, FORMAT_HTML, FORMAT_MARKDOWN]
        ),
        vol.Optional(ATTR_MENTION_USERS, default=[]): vol.All(
            cv.ensure_list, [cv.string]
        ),
        vol.Optional(ATTR_MENTION_ROOM, default=False): cv.boolean,
        vol.Optional(ATTR_THREAD_ID): cv.string,
    }
)
_REACT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_ROOM): cv.string,
        vol.Required(ATTR_EVENT_ID): cv.string,
        vol.Required(ATTR_REACTION): cv.string,
    }
)
_EDIT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_ROOM): cv.string,
        vol.Required(ATTR_EVENT_ID): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_MSGTYPE, default="text"): vol.In(MESSAGE_TYPES),
        vol.Optional(ATTR_FORMAT, default=FORMAT_TEXT): vol.In(
            [FORMAT_TEXT, FORMAT_HTML, FORMAT_MARKDOWN]
        ),
    }
)
_REDACT_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_ROOM): cv.string,
        vol.Required(ATTR_EVENT_ID): cv.string,
        vol.Optional(ATTR_REASON): cv.string,
    }
)


def _select_account(hass: HomeAssistant, account_id: str | None) -> MatrixAccount:
    accounts: dict[str, MatrixAccount] = hass.data.get(DOMAIN, {})
    if account_id:
        account = accounts.get(account_id)
        if account is None:
            raise HomeAssistantError(f"Unknown Matrix Extended account: {account_id}")
        return account
    if len(accounts) == 1:
        return next(iter(accounts.values()))
    if not accounts:
        raise HomeAssistantError("No Matrix Extended accounts are loaded")
    raise HomeAssistantError(
        "Multiple Matrix Extended accounts are loaded; set 'account' to a config entry ID"
    )


def _rooms_by_encryption(rooms: list[PreparedRoom]) -> dict[bool, list[PreparedRoom]]:
    grouped: dict[bool, list[PreparedRoom]] = {}
    for room in rooms:
        grouped.setdefault(room.encrypted, []).append(room)
    return grouped


def _room_for_call(account: MatrixAccount, call: ServiceCall) -> str:
    return call.data.get(ATTR_ROOM) or account.default_room


def _formatted_body(message: str, message_format: str) -> str | None:
    if message_format == FORMAT_HTML:
        return message
    if message_format == FORMAT_MARKDOWN:
        return render_markdown(message)
    return None


def _send_payload(account: MatrixAccount, call: ServiceCall) -> dict[str, Any]:
    targets = resolve_targets(
        explicit_targets=call.data.get(ATTR_TARGET),
        route=call.data.get(ATTR_ROUTE),
        default_room=account.default_room,
        routing_profiles=account.routing_profiles or {},
    )
    payload = {
        "targets": targets,
        "notification_key": call.data.get(ATTR_NOTIFICATION_KEY),
        "message": call.data[ATTR_MESSAGE],
        "msgtype": call.data[ATTR_MSGTYPE],
        "format": call.data[ATTR_FORMAT],
        "mentions": build_mentions(
            call.data.get(ATTR_MENTION_USERS, []),
            room=bool(call.data.get(ATTR_MENTION_ROOM, False)),
        ),
        "thread_id": call.data.get(ATTR_THREAD_ID),
        "media": call.data[ATTR_MEDIA],
        "actions": call.data[ATTR_ACTIONS],
    }
    if not payload["message"] and not payload["media"]:
        raise HomeAssistantError("matrix_extended.send needs a message and/or media")
    if payload["actions"] and not payload["message"]:
        raise HomeAssistantError("reaction actions require a text message")
    if payload["notification_key"] and not payload["message"]:
        raise HomeAssistantError("notification_key requires a text message")
    return payload


def _tx_ids(delivery_id: str, event_key: str, rooms: list[PreparedRoom]) -> list[str]:
    return [
        matrix_transaction_id(delivery_id, event_key, room.room_id)
        for room in rooms
    ]


def _delivery_payload(
    account: MatrixAccount,
    delivery_id: str,
    status: str,
    events: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    account_id = account.entry_id
    if not account_id:
        raise HomeAssistantError("Matrix account has no config entry ID")
    return delivery_lifecycle_payload(
        account_id=account_id,
        delivery_id=delivery_id,
        status=status,
        events=events or [],
        error=error,
    )


def _fire_delivery(
    hass: HomeAssistant,
    account: MatrixAccount,
    delivery_id: str,
    status: str,
    events: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload = _delivery_payload(account, delivery_id, status, events, error)
    account.status.mark_delivery(status)
    hass.bus.async_fire(EVENT_DELIVERY, payload)
    return payload


def _delivery_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_id": payload["delivery_id"],
        "status": payload["status"],
        "events": list(payload["events"]),
    }


async def _async_execute_send(
    hass: HomeAssistant,
    account: MatrixAccount,
    payload: dict[str, Any],
    *,
    delivery_id: str,
) -> list[dict[str, Any]]:
    targets: list[str] = list(payload["targets"])
    notification_key: str | None = payload.get("notification_key")
    message: str = payload["message"]
    media_items: list[dict[str, Any]] = payload["media"]
    actions: list[dict[str, Any]] = payload["actions"]
    thread_id: str | None = payload.get("thread_id")
    delivery_events: list[dict[str, Any]] = []

    prepared_rooms = await account.client.async_prepare_rooms(targets)
    for target, room in zip(targets, prepared_rooms, strict=True):
        if target == account.default_room:
            account.status.set_default_room_encryption(room.encrypted)

    if message:
        formatted_body = _formatted_body(message, payload["format"])
        event_ids: list[str | None] = []
        registry_changed = False
        if notification_key and account.notification_registry:
            for room in prepared_rooms:
                original_event_id = account.notification_registry.get(
                    notification_key, room.room_id
                )
                event_key = f"notification:{notification_key}"
                room_tx_ids = _tx_ids(delivery_id, event_key, [room])
                if original_event_id:
                    sent = await account.client.async_send_prepared(
                        [room],
                        build_edit_content(
                            message,
                            event_id=original_event_id,
                            formatted_body=formatted_body,
                            msgtype=payload["msgtype"],
                        ),
                        tx_ids=room_tx_ids,
                    )
                    event_ids.append(original_event_id)
                    if sent[0]:
                        delivery_events.append(
                            delivery_event_record(
                                room_id=room.room_id,
                                event_id=sent[0],
                                kind="text",
                            )
                        )
                else:
                    sent = await account.client.async_send_prepared(
                        [room],
                        build_text_content(
                            message,
                            formatted_body=formatted_body,
                            thread_id=thread_id,
                            msgtype=payload["msgtype"],
                            mentions=payload["mentions"],
                        ),
                        tx_ids=room_tx_ids,
                    )
                    event_id = sent[0]
                    event_ids.append(event_id)
                    if event_id:
                        delivery_events.append(
                            delivery_event_record(
                                room_id=room.room_id,
                                event_id=event_id,
                                kind="text",
                            )
                        )
                        account.notification_registry.set(
                            notification_key, room.room_id, event_id
                        )
                        registry_changed = True
            if registry_changed and account.notification_store:
                await account.notification_store.async_save(
                    account.notification_registry.dump()
                )
        else:
            event_ids = await account.client.async_send_prepared(
                prepared_rooms,
                build_text_content(
                    message,
                    formatted_body=formatted_body,
                    thread_id=thread_id,
                    msgtype=payload["msgtype"],
                    mentions=payload["mentions"],
                ),
                tx_ids=_tx_ids(delivery_id, "text", prepared_rooms),
            )
            for room, event_id in zip(prepared_rooms, event_ids, strict=True):
                if event_id:
                    delivery_events.append(
                        delivery_event_record(
                            room_id=room.room_id,
                            event_id=event_id,
                            kind="text",
                        )
                    )
        if actions and account.action_registry:
            for room, event_id in zip(prepared_rooms, event_ids, strict=True):
                if event_id:
                    account.action_registry.register(
                        room_id=room.room_id,
                        event_id=event_id,
                        actions=actions,
                    )
            await account.action_registry.async_save()

    resolver = MediaResolver(hass)
    room_groups = _rooms_by_encryption(prepared_rooms)
    for media_index, item in enumerate(media_items):
        media = await resolver.async_resolve(item)
        thumbnail = None
        if thumbnail_source := item.get("thumbnail"):
            thumbnail = await resolver.async_resolve(thumbnail_source, force_type="image")

        for encrypted, rooms in room_groups.items():
            thumbnail_upload = None
            if thumbnail is not None:
                thumbnail_upload = await account.client.async_upload(
                    thumbnail.data,
                    filename=thumbnail.filename,
                    content_type=thumbnail.content_type,
                    encrypt=encrypted,
                )
            media_upload = await account.client.async_upload(
                media.data,
                filename=media.filename,
                content_type=media.content_type,
                encrypt=encrypted,
            )
            content = build_media_content(
                media_type=media.media_type,
                mxc_uri=None if encrypted else media_upload.mxc_uri,
                encrypted_file=media_upload.encrypted_file if encrypted else None,
                filename=media.filename,
                content_type=media.content_type,
                size=media.size,
                caption=item.get("caption"),
                formatted_caption=item.get("formatted_caption"),
                width=media.width,
                height=media.height,
                duration_ms=media.duration_ms,
                thumbnail_mxc_uri=(
                    None
                    if encrypted or thumbnail_upload is None
                    else thumbnail_upload.mxc_uri
                ),
                thumbnail_encrypted_file=(
                    thumbnail_upload.encrypted_file
                    if encrypted and thumbnail_upload is not None
                    else None
                ),
                thumbnail_info=thumbnail.image_info() if thumbnail else None,
                thread_id=thread_id,
                voice=bool(item.get("voice", False)),
            )
            sent = await account.client.async_send_prepared(
                rooms,
                content,
                tx_ids=_tx_ids(delivery_id, f"media-{media_index}", rooms),
            )
            for room, event_id in zip(rooms, sent, strict=True):
                if event_id:
                    delivery_events.append(
                        delivery_event_record(
                            room_id=room.room_id,
                            event_id=event_id,
                            kind="media",
                            media_index=media_index,
                        )
                    )
    account.status.mark_send_success()
    return delivery_events


async def _async_outbox_worker(hass: HomeAssistant, account: MatrixAccount) -> None:
    while True:
        if account.outbox is None:
            await asyncio.sleep(_OUTBOX_RETRY_SECONDS)
            continue
        pending = account.outbox.pending()
        if not pending:
            await asyncio.sleep(_OUTBOX_RETRY_SECONDS)
            continue
        item = pending[0]
        try:
            events = await _async_execute_send(
                hass,
                account,
                item.payload,
                delivery_id=item.delivery_id,
            )
        except asyncio.CancelledError:
            raise
        except MatrixConnectionError as err:
            account.status.mark_error(str(err))
            await asyncio.sleep(_OUTBOX_RETRY_SECONDS)
        except MatrixEncryptionRequiredError as err:
            account.status.mark_error(str(err), connected=True)
            _LOGGER.warning(
                "Dropping queued Matrix send %s after encryption-policy failure: %s",
                item.delivery_id,
                err,
            )
            _fire_delivery(
                hass, account, item.delivery_id, "dropped", error=str(err)
            )
            await account.outbox.async_remove(item.delivery_id)
        except (MatrixExtendedError, HomeAssistantError, ValueError) as err:
            account.status.mark_error(str(err))
            _LOGGER.warning(
                "Dropping queued Matrix send %s after permanent failure: %s",
                item.delivery_id,
                err,
            )
            _fire_delivery(
                hass, account, item.delivery_id, "dropped", error=str(err)
            )
            await account.outbox.async_remove(item.delivery_id)
        else:
            _fire_delivery(hass, account, item.delivery_id, "sent", events=events)
            await account.outbox.async_remove(item.delivery_id)


async def _async_handle_send(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    payload = _send_payload(account, call)
    delivery_id = secrets.token_hex(16)
    if not account.status.connected:
        if account.outbox is not None:
            await account.outbox.async_enqueue(payload, delivery_id=delivery_id)
            delivery = _fire_delivery(hass, account, delivery_id, "queued")
            return _delivery_response(delivery)
    try:
        events = await _async_execute_send(
            hass,
            account,
            payload,
            delivery_id=delivery_id,
        )
    except MatrixEncryptionRequiredError as err:
        account.status.mark_error(str(err), connected=True)
        _fire_delivery(hass, account, delivery_id, "failed", error=str(err))
        raise
    except MatrixConnectionError as err:
        account.status.mark_error(str(err))
        if account.outbox is None:
            _fire_delivery(hass, account, delivery_id, "failed", error=str(err))
            raise
        await account.outbox.async_enqueue(payload, delivery_id=delivery_id)
        delivery = _fire_delivery(hass, account, delivery_id, "queued")
        return _delivery_response(delivery)
    except (MatrixExtendedError, HomeAssistantError, ValueError) as err:
        account.status.mark_error(str(err))
        _fire_delivery(hass, account, delivery_id, "failed", error=str(err))
        raise
    delivery = _fire_delivery(hass, account, delivery_id, "sent", events=events)
    return _delivery_response(delivery)


async def _async_handle_reply(hass: HomeAssistant, call: ServiceCall) -> None:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    formatted = _formatted_body(call.data[ATTR_MESSAGE], call.data[ATTR_FORMAT])
    mentions = build_mentions(
        call.data.get(ATTR_MENTION_USERS, []),
        room=bool(call.data.get(ATTR_MENTION_ROOM, False)),
    )
    await account.client.async_send_content(
        _room_for_call(account, call),
        build_reply_content(
            call.data[ATTR_MESSAGE],
            reply_to=call.data[ATTR_EVENT_ID],
            formatted_body=formatted,
            thread_id=call.data.get(ATTR_THREAD_ID),
            msgtype=call.data[ATTR_MSGTYPE],
            mentions=mentions,
        ),
    )
    account.status.mark_send_success()


async def _async_handle_react(hass: HomeAssistant, call: ServiceCall) -> None:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    await account.client.async_send_event(
        _room_for_call(account, call),
        "m.reaction",
        build_reaction_content(call.data[ATTR_EVENT_ID], call.data[ATTR_REACTION]),
    )
    account.status.mark_send_success()


async def _async_handle_edit(hass: HomeAssistant, call: ServiceCall) -> None:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    formatted = _formatted_body(call.data[ATTR_MESSAGE], call.data[ATTR_FORMAT])
    await account.client.async_send_content(
        _room_for_call(account, call),
        build_edit_content(
            call.data[ATTR_MESSAGE],
            event_id=call.data[ATTR_EVENT_ID],
            formatted_body=formatted,
            msgtype=call.data[ATTR_MSGTYPE],
        ),
    )
    account.status.mark_send_success()


async def _async_handle_redact(hass: HomeAssistant, call: ServiceCall) -> None:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    await account.client.async_redact(
        _room_for_call(account, call),
        call.data[ATTR_EVENT_ID],
        reason=call.data.get(ATTR_REASON),
    )
    account.status.mark_send_success()


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Matrix Extended services."""
    hass.data.setdefault(DOMAIN, {})

    def register(
        name: str,
        handler: Any,
        schema: vol.Schema,
        *,
        supports_response: SupportsResponse = SupportsResponse.NONE,
    ) -> None:
        async def wrapped(call: ServiceCall) -> Any:
            try:
                return await handler(hass, call)
            except (MatrixExtendedError, ValueError) as err:
                raise HomeAssistantError(str(err)) from err

        hass.services.async_register(
            DOMAIN,
            name,
            wrapped,
            schema=schema,
            supports_response=supports_response,
        )

    register(
        SERVICE_SEND,
        _async_handle_send,
        SEND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(SERVICE_REPLY, _async_handle_reply, _REPLY_SCHEMA)
    register(SERVICE_REACT, _async_handle_react, _REACT_SCHEMA)
    register(SERVICE_EDIT, _async_handle_edit, _EDIT_SCHEMA)
    register(SERVICE_REDACT, _async_handle_redact, _REDACT_SCHEMA)
    install_v05_services(hass)
    install_v051_services(hass)
    return True


def _entry_value(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Matrix account from a config entry."""
    data = dict(entry.data)
    changed = False
    defaults = {
        CONF_STORE_KEY: secrets.token_urlsafe(32),
        CONF_REQUIRE_E2EE: True,
        CONF_INCOMING_ENABLED: True,
        CONF_ALLOWED_USERS: [data[CONF_USER_ID]],
        CONF_ALLOWED_ROOMS: [data[CONF_DEFAULT_ROOM]],
        CONF_DOWNLOAD_INCOMING_MEDIA: True,
        CONF_ROUTING_PROFILES: {},
    }
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
            changed = True
    if changed:
        hass.config_entries.async_update_entry(entry, data=data)

    store_path = hass.config.path(".storage", DOMAIN, entry.entry_id)
    await hass.async_add_executor_job(partial(Path(store_path).mkdir, parents=True, exist_ok=True))

    status = MatrixRuntimeStatus()
    client = MatrixClient(
        homeserver=data[CONF_HOMESERVER],
        user_id=data[CONF_USER_ID],
        access_token=data[CONF_ACCESS_TOKEN],
        device_id=data[CONF_DEVICE_ID],
        verify_ssl=data[CONF_VERIFY_SSL],
        store_path=store_path,
        store_key=data[CONF_STORE_KEY],
        require_e2ee=_entry_value(entry, CONF_REQUIRE_E2EE, True),
    )
    try:
        default_room_encrypted = await client.async_connect(data[CONF_DEFAULT_ROOM])
        allowed_rooms = {
            await client.async_resolve_room(room)
            for room in _entry_value(entry, CONF_ALLOWED_ROOMS, [data[CONF_DEFAULT_ROOM]])
        }
    except MatrixAuthenticationError as err:
        await client.async_close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except (MatrixConnectionError, MatrixExtendedError) as err:
        await client.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    status.mark_connected(default_room_encrypted=default_room_encrypted)
    notification_store: Store[dict[str, dict[str, str]]] = Store(
        hass, 1, f"{DOMAIN}.notification_keys_{entry.entry_id}", private=True
    )
    stored_notifications = await notification_store.async_load() or {}
    notification_registry = NotificationKeyRegistry(stored_notifications)
    action_store: Store[dict[str, Any]] = Store(
        hass, 1, f"{DOMAIN}.reaction_actions_{entry.entry_id}", private=True
    )
    stored_actions = await action_store.async_load() or {}
    action_registry = ReactionActionRegistry(stored_actions, store=action_store)
    command_store: Store[dict[str, Any]] = Store(
        hass, 1, f"{DOMAIN}.commands_{entry.entry_id}", private=True
    )
    stored_commands = await command_store.async_load() or {}
    command_registry = CommandRegistry(stored_commands, store=command_store)
    outbox_store: Store[dict[str, Any]] = Store(
        hass, 1, f"{DOMAIN}.outbox_{entry.entry_id}", private=True
    )
    stored_outbox = await outbox_store.async_load() or {}
    outbox = PersistentOutbox(stored_outbox, store=outbox_store)
    await outbox.async_save()
    rooms = client.rooms_snapshot()
    default_room_id = await client.async_resolve_room(data[CONF_DEFAULT_ROOM])
    account = MatrixAccount(
        client=client,
        default_room=data[CONF_DEFAULT_ROOM],
        user_id=data[CONF_USER_ID],
        device_id=data[CONF_DEVICE_ID],
        homeserver=data[CONF_HOMESERVER],
        status=status,
        action_registry=action_registry,
        command_registry=command_registry,
        outbox=outbox,
        incoming_policy=IncomingPolicy(
            allowed_users=_entry_value(entry, CONF_ALLOWED_USERS, [data[CONF_USER_ID]]),
            allowed_rooms=allowed_rooms,
        ),
        rooms=rooms,
        routing_profiles=normalize_routing_profiles(
            _entry_value(entry, CONF_ROUTING_PROFILES, {})
        ),
        notification_registry=notification_registry,
        notification_store=notification_store,
        entry_id=entry.entry_id,
        default_room_id=default_room_id,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = account
    account.outbox_task = hass.async_create_task(
        _async_outbox_worker(hass, account),
        f"matrix_extended_outbox_{entry.entry_id}",
    )

    if _entry_value(entry, CONF_INCOMING_ENABLED, True):
        incoming_dir = hass.config.path(DOMAIN, "incoming", entry.entry_id)
        await hass.async_add_executor_job(partial(Path(incoming_dir).mkdir, parents=True, exist_ok=True))
        receiver = MatrixInboundReceiver(
            hass,
            entry_id=entry.entry_id,
            account=account,
            incoming_dir=incoming_dir,
            download_media=_entry_value(entry, CONF_DOWNLOAD_INCOMING_MEDIA, True),
            media_retention_days=int(
                _entry_value(
                    entry,
                    CONF_INCOMING_MEDIA_RETENTION_DAYS,
                    DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
                )
            ),
            media_max_bytes=int(
                _entry_value(
                    entry,
                    CONF_INCOMING_MEDIA_MAX_MB,
                    DEFAULT_INCOMING_MEDIA_MAX_MB,
                )
            )
            * 1024
            * 1024,
        )
        receiver.register()
        await client.async_start_listener(receiver.async_listener_error)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Matrix account."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    account: MatrixAccount | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if account is not None:
        if account.outbox_task is not None:
            account.outbox_task.cancel()
            with suppress(asyncio.CancelledError):
                await account.outbox_task
            account.outbox_task = None
        await account.client.async_close()
    return True
