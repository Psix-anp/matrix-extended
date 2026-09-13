"""Matrix Extended v0.5.1 safe command management actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import MatrixAccount
from .commands import CameraSnapshotCommandHandler, ServiceCommandHandler
from .const import (
    ATTR_ACCOUNT,
    DOMAIN,
    SERVICE_REGISTER_COMMAND,
    SERVICE_UNREGISTER_COMMAND,
)

_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Required("id"): cv.string,
        vol.Required("trigger"): cv.string,
        vol.Optional("aliases", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("description", default=""): cv.string,
        vol.Optional("allowed_users", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("allowed_rooms", default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("progress", default=True): cv.boolean,
        vol.Required("handler_type"): vol.In(["service", "camera_snapshot"]),
        vol.Optional("service"): cv.string,
        vol.Optional("target", default={}): dict,
        vol.Optional("data", default={}): dict,
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("caption", default="Camera snapshot"): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

_UNREGISTER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ACCOUNT): cv.string,
        vol.Required("id"): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
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


def _command_definition(data: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    handler_type = str(data["handler_type"])
    common = {
        "id": str(data["id"]),
        "trigger": str(data["trigger"]),
        "aliases": list(data.get("aliases") or []),
        "description": str(data.get("description") or ""),
        "allowed_users": list(data.get("allowed_users") or []),
        "allowed_rooms": list(data.get("allowed_rooms") or []),
        "progress": bool(data.get("progress", True)),
        "enabled": True,
    }
    if handler_type == "service":
        service = str(data.get("service") or "").strip()
        if not service:
            raise HomeAssistantError("service handler requires service")
        if data.get("entity_id") is not None:
            raise HomeAssistantError("service handler does not accept entity_id")
        common["handler"] = {
            "type": "service",
            "service": service,
            "target": dict(data.get("target") or {}),
            "data": dict(data.get("data") or {}),
        }
        return common, handler_type

    if handler_type == "camera_snapshot":
        entity_id = str(data.get("entity_id") or "").strip()
        if not entity_id:
            raise HomeAssistantError("camera_snapshot requires entity_id")
        if data.get("service") is not None or data.get("target") or data.get("data"):
            raise HomeAssistantError(
                "camera_snapshot does not accept service, target, or data"
            )
        common["handler"] = {
            "type": "camera_snapshot",
            "entity_id": entity_id,
            "caption": str(data.get("caption") or "Camera snapshot"),
        }
        return common, handler_type

    raise HomeAssistantError(f"Unsupported command handler type: {handler_type}")


async def async_register_command(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Register or explicitly replace one safe Matrix command."""
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    if account.command_registry is None:
        raise HomeAssistantError("Safe command registry is unavailable")
    definition, handler_type = _command_definition(call.data)
    command = account.command_registry.register(definition)
    await account.command_registry.async_save()
    if isinstance(command.handler, ServiceCommandHandler):
        handler_type = "service"
    elif isinstance(command.handler, CameraSnapshotCommandHandler):
        handler_type = "camera_snapshot"
    return {
        "id": command.id,
        "trigger": command.trigger,
        "handler_type": handler_type,
    }


async def async_unregister_command(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Remove one safe Matrix command by stable ID."""
    account = _select_account(hass, call.data.get(ATTR_ACCOUNT))
    if account.command_registry is None:
        raise HomeAssistantError("Safe command registry is unavailable")
    command_id = str(call.data["id"]).strip()
    removed = account.command_registry.unregister(command_id)
    if removed:
        await account.command_registry.async_save()
    return {"id": command_id, "removed": removed}


def install_v051_services(hass: HomeAssistant) -> None:
    """Install v0.5.1 safe-command management actions once."""

    def register(name: str, handler: Any, schema: vol.Schema) -> None:
        async def wrapped(call: ServiceCall) -> dict[str, Any]:
            try:
                return await handler(hass, call)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err

        hass.services.async_register(
            DOMAIN,
            name,
            wrapped,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )

    register(SERVICE_REGISTER_COMMAND, async_register_command, _REGISTER_SCHEMA)
    register(SERVICE_UNREGISTER_COMMAND, async_unregister_command, _UNREGISTER_SCHEMA)
