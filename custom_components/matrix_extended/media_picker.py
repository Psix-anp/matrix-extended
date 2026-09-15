"""Graphical Home Assistant media picker action for Matrix Extended."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import MatrixAccount
from .const import (
    ATTR_ACCOUNT,
    ATTR_MEDIA,
    ATTR_ROUTE,
    ATTR_TARGET,
    ATTR_THREAD_ID,
    DOMAIN,
    SERVICE_SEND,
    SERVICE_SEND_MEDIA,
)
from .media_picker_value import send_media_source_to_media_item

MEDIA_PICKER_FIELD = "media_picker"
URL_FIELD = "url"
ENTITY_ID_FIELD = "entity_id"
MEDIA_TYPE_FIELD = "type"
FILENAME_FIELD = "filename"

_MEDIA_PICKER_VALUE_SCHEMA = vol.Schema(
    {
        vol.Required("media_content_id"): cv.string,
        vol.Optional("media_content_type"): cv.string,
        vol.Optional("metadata"): dict,
        vol.Optional("entity_id"): cv.entity_id,
    },
    extra=vol.ALLOW_EXTRA,
)


def _validate_single_media_source(data: dict[str, Any]) -> dict[str, Any]:
    """Require exactly one graphical send_media source."""
    sources = [
        MEDIA_PICKER_FIELD in data,
        bool(str(data.get(URL_FIELD, "")).strip()),
        bool(str(data.get(ENTITY_ID_FIELD, "")).strip()),
    ]
    if sum(sources) != 1:
        raise vol.Invalid(
            "send_media requires exactly one source: media_picker, url, or entity_id"
        )
    return data


SEND_MEDIA_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_ACCOUNT): cv.string,
            vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(ATTR_ROUTE): cv.string,
            vol.Optional(MEDIA_PICKER_FIELD): _MEDIA_PICKER_VALUE_SCHEMA,
            vol.Optional(URL_FIELD): cv.string,
            vol.Optional(ENTITY_ID_FIELD): cv.entity_id,
            vol.Optional(MEDIA_TYPE_FIELD, default="auto"): vol.In(
                ("auto", "image", "video", "audio", "file")
            ),
            vol.Optional(FILENAME_FIELD): cv.string,
            vol.Optional("caption"): cv.string,
            vol.Optional("voice", default=False): cv.boolean,
            vol.Optional(ATTR_THREAD_ID): cv.string,
        }
    ),
    _validate_single_media_source,
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


async def _async_send_media(hass: HomeAssistant, call: ServiceCall) -> None:
    """Translate one graphical media source into matrix_extended.send."""
    _select_account(hass, call.data.get(ATTR_ACCOUNT))
    try:
        media_item = send_media_source_to_media_item(
            media_picker=call.data.get(MEDIA_PICKER_FIELD),
            url=call.data.get(URL_FIELD),
            entity_id=call.data.get(ENTITY_ID_FIELD),
            media_type=call.data.get(MEDIA_TYPE_FIELD, "auto"),
            filename=call.data.get(FILENAME_FIELD),
            caption=call.data.get("caption"),
            voice=bool(call.data.get("voice", False)),
        )
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err
    data: dict[str, Any] = {ATTR_MEDIA: [media_item]}
    for key in (ATTR_ACCOUNT, ATTR_TARGET, ATTR_ROUTE, ATTR_THREAD_ID):
        if key in call.data:
            data[key] = call.data[key]
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        data,
        blocking=True,
    )


def install_media_picker_service(hass: HomeAssistant) -> None:
    """Register the graphical media-picker service."""

    async def handler(call: ServiceCall) -> None:
        await _async_send_media(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MEDIA,
        handler,
        schema=SEND_MEDIA_SCHEMA,
    )
