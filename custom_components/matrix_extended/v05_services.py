"""Focused v0.5 services kept separate from the core send runtime."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import MatrixAccount, MatrixExtendedError
from .const import (
    ATTR_ACCOUNT,
    ATTR_ROUTE,
    ATTR_TARGET,
    ATTR_THREAD_ID,
    DOMAIN,
    EVENT_DELIVERY,
    SERVICE_PURGE_MEDIA,
    SERVICE_SEND_LOCATION,
)
from .content import build_location_content
from .delivery import delivery_event_record, delivery_lifecycle_payload
from .outbox import matrix_transaction_id
from .retention import purge_media_directory
from .routing import resolve_targets

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
    hass.bus.async_fire(EVENT_DELIVERY, payload)
    return payload


async def _async_send_location(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    latitude, longitude, description = _location_from_call(hass, call)
    targets = resolve_targets(
        explicit_targets=call.data.get(ATTR_TARGET),
        route=call.data.get(ATTR_ROUTE),
        default_room=account.default_room,
        routing_profiles=account.routing_profiles or {},
    )
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
    delivery = _fire_delivery(
        hass, account, delivery_id, "sent", events=events
    )
    return {
        "delivery_id": delivery["delivery_id"],
        "status": delivery["status"],
        "events": list(delivery["events"]),
    }


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
    register(SERVICE_PURGE_MEDIA, _async_purge_media, _PURGE_SCHEMA)
