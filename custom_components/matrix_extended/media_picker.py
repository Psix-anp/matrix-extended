"""Graphical Home Assistant media picker action for Matrix Extended."""

from __future__ import annotations

from collections.abc import Mapping
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

MEDIA_PICKER_FIELD = "media_picker"

_MEDIA_PICKER_VALUE_SCHEMA = vol.Schema(
    {
        vol.Required("media_content_id"): cv.string,
        vol.Optional("media_content_type"): cv.string,
        vol.Optional("metadata"): dict,
        vol.Optional("entity_id"): cv.entity_id,
    },
    extra=vol.ALLOW_EXTRA,
)

SEND_MEDIA_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ROUTE): cv.string,
        vol.Required(MEDIA_PICKER_FIELD): _MEDIA_PICKER_VALUE_SCHEMA,
        vol.Optional("caption"): cv.string,
        vol.Optional("voice", default=False): cv.boolean,
        vol.Optional(ATTR_THREAD_ID): cv.string,
    }
)


def media_picker_to_media_item(
    value: Mapping[str, Any],
    *,
    caption: str | None = None,
    voice: bool = False,
) -> dict[str, Any]:
    """Convert native HA media-selector output to the existing media resolver shape."""
    media_content_id = value.get("media_content_id")
    if not isinstance(media_content_id, str) or not media_content_id.strip():
        raise ValueError("media picker result has no media_content_id")
    item: dict[str, Any] = {
        "media_source": media_content_id.strip(),
        "type": "auto",
    }
    if caption:
        item["caption"] = caption
    if voice:
        item["voice"] = True
    return item


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
    """Translate a graphical picker selection into matrix_extended.send."""
    _select_account(hass, call.data.get(ATTR_ACCOUNT))
    media_item = media_picker_to_media_item(
        call.data[MEDIA_PICKER_FIELD],
        caption=call.data.get("caption"),
        voice=bool(call.data.get("voice", False)),
    )
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MEDIA,
        _async_send_media,
        schema=SEND_MEDIA_SCHEMA,
    )
