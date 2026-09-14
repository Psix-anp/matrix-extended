"""Focused v0.5 services kept separate from the core send runtime."""

from __future__ import annotations

import mimetypes
from pathlib import Path
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import MatrixAccount, MatrixExtendedError, PreparedRoom
from .const import (
    ATTR_ACCOUNT,
    ATTR_ROUTE,
    ATTR_TARGET,
    ATTR_THREAD_ID,
    DOMAIN,
    EVENT_DELIVERY,
    SERVICE_PURGE_MEDIA,
    SERVICE_SEND_LOCATION,
    SERVICE_SEND_VOICE,
    SERVICE_TRANSCRIBE_VOICE,
)
from .content import build_location_content, build_media_content
from .delivery import delivery_event_record, delivery_lifecycle_payload
from .outbox import matrix_transaction_id
from .retention import purge_media_directory
from .routing import resolve_targets
from .voice_pipeline import TRANSCRIBE_SCHEMA, async_transcribe_voice

_LOCATION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ROUTE): cv.string,
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("latitude"): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
        vol.Optional("longitude"): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
        vol.Optional("description"): cv.string,
        vol.Optional(ATTR_THREAD_ID): cv.string,
    }
)

_VOICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ROUTE): cv.string,
        vol.Required("text"): cv.string,
        vol.Optional("tts_engine"): cv.string,
        vol.Optional("language"): cv.string,
        vol.Optional("tts_options", default={}): dict,
        vol.Optional(ATTR_THREAD_ID): cv.string,
    }
)

_PURGE_SCHEMA = vol.Schema({vol.Optional(ATTR_ACCOUNT): cv.string})


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


def _targets(account: MatrixAccount, call: ServiceCall) -> list[str]:
    return resolve_targets(
        explicit_targets=call.data.get(ATTR_TARGET),
        route=call.data.get(ATTR_ROUTE),
        default_room=account.default_room,
        routing_profiles=account.routing_profiles or {},
    )


def _rooms_by_encryption(
    rooms: list[PreparedRoom],
) -> dict[bool, list[PreparedRoom]]:
    grouped: dict[bool, list[PreparedRoom]] = {}
    for room in rooms:
        grouped.setdefault(room.encrypted, []).append(room)
    return grouped


def _location_from_call(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[float, float, str]:
    entity_id = call.data.get("entity_id")
    explicit_lat = call.data.get("latitude")
    explicit_lon = call.data.get("longitude")

    if entity_id and (explicit_lat is not None or explicit_lon is not None):
        raise HomeAssistantError(
            "Use either entity_id or explicit latitude/longitude, not both"
        )

    if entity_id:
        state = hass.states.get(entity_id)
        if state is None:
            raise HomeAssistantError(f"Location entity not found: {entity_id}")
        latitude = state.attributes.get("latitude")
        longitude = state.attributes.get("longitude")
        if latitude is None or longitude is None:
            raise HomeAssistantError(
                f"Location entity {entity_id} has no latitude/longitude attributes"
            )
        description = call.data.get("description") or state.attributes.get(
            "friendly_name"
        ) or entity_id
        return float(latitude), float(longitude), str(description)

    if explicit_lat is None or explicit_lon is None:
        raise HomeAssistantError(
            "send_location needs entity_id or both latitude and longitude"
        )
    return (
        float(explicit_lat),
        float(explicit_lon),
        str(call.data.get("description") or "Location"),
    )


def _fire_delivery(
    hass: HomeAssistant,
    account: MatrixAccount,
    delivery_id: str,
    status: str,
    *,
    events: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if not account.entry_id:
        raise HomeAssistantError("Matrix account has no config entry ID")
    payload = delivery_lifecycle_payload(
        account_id=account.entry_id,
        delivery_id=delivery_id,
        status=status,
        events=events or [],
        error=error,
    )
    account.status.mark_delivery(status)
    hass.bus.async_fire(EVENT_DELIVERY, payload)
    return payload


def _delivery_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_id": payload["delivery_id"],
        "status": payload["status"],
        "events": list(payload["events"]),
    }


async def _async_send_location(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    latitude, longitude, description = _location_from_call(hass, call)
    targets = _targets(account, call)
    content = build_location_content(
        latitude=latitude,
        longitude=longitude,
        description=description,
        thread_id=call.data.get(ATTR_THREAD_ID),
    )
    delivery_id = secrets.token_hex(16)
    try:
        rooms = await account.client.async_prepare_rooms(targets)
        event_ids = await account.client.async_send_prepared(
            rooms,
            content,
            tx_ids=[
                matrix_transaction_id(delivery_id, "location", room.room_id)
                for room in rooms
            ],
        )
    except (MatrixExtendedError, ValueError) as err:
        account.status.mark_error(str(err))
        _fire_delivery(hass, account, delivery_id, "failed", error=str(err))
        raise

    events = [
        delivery_event_record(room_id=room.room_id, event_id=event_id, kind="location")
        for room, event_id in zip(rooms, event_ids, strict=True)
        if event_id
    ]
    account.status.mark_send_success()
    return _delivery_response(
        _fire_delivery(hass, account, delivery_id, "sent", events=events)
    )


async def _async_send_voice(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Generate Home Assistant TTS once and send it as native Matrix voice."""
    from homeassistant.components import tts  # noqa: PLC0415
    from homeassistant.components.tts.media_source import (  # noqa: PLC0415
        generate_media_source_id,
    )

    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    text = str(call.data["text"]).strip()
    if not text:
        raise HomeAssistantError("send_voice text must not be empty")

    media_source_id = generate_media_source_id(
        hass,
        text,
        engine=call.data.get("tts_engine"),
        language=call.data.get("language"),
        options=dict(call.data.get("tts_options") or {}),
        cache=True,
    )
    extension, audio = await tts.async_get_media_source_audio(hass, media_source_id)
    if not audio:
        raise HomeAssistantError("Home Assistant TTS returned empty audio")

    ext = str(extension or "mp3").lower().lstrip(".")
    content_type = mimetypes.types_map.get(f".{ext}", "audio/mpeg")
    filename = f"matrix-voice.{ext}"
    targets = _targets(account, call)
    delivery_id = secrets.token_hex(16)
    events: list[dict[str, Any]] = []

    try:
        rooms = await account.client.async_prepare_rooms(targets)
        for encrypted, group in _rooms_by_encryption(rooms).items():
            upload = await account.client.async_upload(
                audio,
                filename=filename,
                content_type=content_type,
                encrypt=encrypted,
            )
            content = build_media_content(
                media_type="audio",
                mxc_uri=None if encrypted else upload.mxc_uri,
                encrypted_file=upload.encrypted_file if encrypted else None,
                filename=filename,
                content_type=content_type,
                size=len(audio),
                thread_id=call.data.get(ATTR_THREAD_ID),
                voice=True,
            )
            event_ids = await account.client.async_send_prepared(
                group,
                content,
                tx_ids=[
                    matrix_transaction_id(delivery_id, "voice", room.room_id)
                    for room in group
                ],
            )
            events.extend(
                delivery_event_record(
                    room_id=room.room_id,
                    event_id=event_id,
                    kind="voice",
                )
                for room, event_id in zip(group, event_ids, strict=True)
                if event_id
            )
    except (MatrixExtendedError, ValueError) as err:
        account.status.mark_error(str(err))
        _fire_delivery(hass, account, delivery_id, "failed", error=str(err))
        raise

    account.status.mark_send_success()
    return _delivery_response(
        _fire_delivery(hass, account, delivery_id, "sent", events=events)
    )


async def _async_purge_media(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, int]:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    if not account.entry_id:
        raise HomeAssistantError("Matrix account has no config entry ID")
    path = Path(hass.config.path(DOMAIN, "incoming", account.entry_id))
    result = await hass.async_add_executor_job(purge_media_directory, path)
    return {
        "removed_files": result.removed_files,
        "removed_bytes": result.removed_bytes,
    }


def install_v05_services(hass: HomeAssistant) -> None:
    """Register focused v0.5 services once during integration setup."""

    def register(
        name: str,
        handler: Any,
        schema: vol.Schema,
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
            supports_response=SupportsResponse.OPTIONAL,
        )

    register(SERVICE_SEND_LOCATION, _async_send_location, _LOCATION_SCHEMA)
    register(SERVICE_SEND_VOICE, _async_send_voice, _VOICE_SCHEMA)
    register(SERVICE_TRANSCRIBE_VOICE, async_transcribe_voice, TRANSCRIBE_SCHEMA)
    register(SERVICE_PURGE_MEDIA, _async_purge_media, _PURGE_SCHEMA)
