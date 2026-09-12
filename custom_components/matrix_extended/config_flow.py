"""Config flow for Matrix Extended."""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from nio import AsyncClient
from nio.responses import RoomResolveAliasResponse

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv, selector

from .client import MatrixAuthenticationError, MatrixConnectionError, async_password_login
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ALLOWED_ROOMS,
    CONF_ALLOWED_USERS,
    CONF_DEFAULT_ROOM,
    CONF_DEVICE_ID,
    CONF_DOWNLOAD_INCOMING_MEDIA,
    CONF_HOMESERVER,
    CONF_INCOMING_ENABLED,
    CONF_REQUIRE_E2EE,
    CONF_ROUTING_PROFILES,
    CONF_STORE_KEY,
    CONF_USER_ID,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from .routing import normalize_routing_profiles

CONF_PASSWORD = "password"


async def _async_validate_default_room(*, homeserver: str, user_id: str, access_token: str, device_id: str, verify_ssl: bool, room: str) -> None:
    if room.startswith("!"):
        return
    if not room.startswith("#"):
        raise ValueError("invalid_room")
    client = AsyncClient(homeserver, user_id, device_id=device_id, ssl=verify_ssl)
    client.restore_login(user_id=user_id, device_id=device_id, access_token=access_token)
    try:
        response = await client.room_resolve_alias(room)
        if not isinstance(response, RoomResolveAliasResponse):
            raise ValueError("invalid_room")
    finally:
        await client.close()


def _list(value: Any) -> list[str]:
    return [str(item).strip() for item in cv.ensure_list(value) if str(item).strip()]


class MatrixExtendedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Matrix Extended config flow."""

    VERSION = 1
    MINOR_VERSION = 3

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return MatrixExtendedOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set up Matrix Extended from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            homeserver = user_input[CONF_HOMESERVER].rstrip("/")
            verify_ssl = user_input[CONF_VERIFY_SSL]
            try:
                details = await async_password_login(homeserver, user_input[CONF_USER_ID], user_input[CONF_PASSWORD], verify_ssl)
                await _async_validate_default_room(
                    homeserver=homeserver,
                    user_id=details.user_id,
                    access_token=details.access_token,
                    device_id=details.device_id,
                    verify_ssl=verify_ssl,
                    room=user_input[CONF_DEFAULT_ROOM],
                )
            except MatrixAuthenticationError:
                errors["base"] = "invalid_auth"
            except ValueError:
                errors[CONF_DEFAULT_ROOM] = "invalid_room"
            except MatrixConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{homeserver}|{details.user_id}")
                self._abort_if_unique_id_configured()
                allowed_users = _list(user_input.get(CONF_ALLOWED_USERS)) or [details.user_id]
                allowed_rooms = _list(user_input.get(CONF_ALLOWED_ROOMS)) or [user_input[CONF_DEFAULT_ROOM]]
                return self.async_create_entry(
                    title=details.user_id,
                    data={
                        CONF_HOMESERVER: homeserver,
                        CONF_USER_ID: details.user_id,
                        CONF_ACCESS_TOKEN: details.access_token,
                        CONF_DEVICE_ID: details.device_id,
                        CONF_DEFAULT_ROOM: user_input[CONF_DEFAULT_ROOM],
                        CONF_VERIFY_SSL: verify_ssl,
                        CONF_REQUIRE_E2EE: user_input[CONF_REQUIRE_E2EE],
                        CONF_STORE_KEY: secrets.token_urlsafe(32),
                        CONF_INCOMING_ENABLED: user_input[CONF_INCOMING_ENABLED],
                        CONF_ALLOWED_USERS: allowed_users,
                        CONF_ALLOWED_ROOMS: allowed_rooms,
                        CONF_DOWNLOAD_INCOMING_MEDIA: user_input[CONF_DOWNLOAD_INCOMING_MEDIA],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOMESERVER): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
                ),
                vol.Required(CONF_USER_ID): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_DEFAULT_ROOM): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Optional(CONF_VERIFY_SSL, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_REQUIRE_E2EE, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_INCOMING_ENABLED, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_ALLOWED_USERS, default=[]): selector.TextSelector(
                    selector.TextSelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_ALLOWED_ROOMS, default=[]): selector.TextSelector(
                    selector.TextSelectorConfig(multiple=True)
                ),
                vol.Optional(
                    CONF_DOWNLOAD_INCOMING_MEDIA, default=True
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class MatrixExtendedOptionsFlow(config_entries.OptionsFlow):
    """Edit inbound security, media and routing settings without re-authentication."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                routing_profiles = normalize_routing_profiles(
                    user_input.get(CONF_ROUTING_PROFILES, {})
                )
            except ValueError:
                errors[CONF_ROUTING_PROFILES] = "invalid_routes"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_REQUIRE_E2EE: user_input[CONF_REQUIRE_E2EE],
                        CONF_INCOMING_ENABLED: user_input[CONF_INCOMING_ENABLED],
                        CONF_ALLOWED_USERS: _list(user_input[CONF_ALLOWED_USERS]),
                        CONF_ALLOWED_ROOMS: _list(user_input[CONF_ALLOWED_ROOMS]),
                        CONF_DOWNLOAD_INCOMING_MEDIA: user_input[CONF_DOWNLOAD_INCOMING_MEDIA],
                        CONF_ROUTING_PROFILES: routing_profiles,
                    },
                )

        value = lambda key, default: self._entry.options.get(
            key, self._entry.data.get(key, default)
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REQUIRE_E2EE, default=value(CONF_REQUIRE_E2EE, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_INCOMING_ENABLED, default=value(CONF_INCOMING_ENABLED, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ALLOWED_USERS,
                    default=value(CONF_ALLOWED_USERS, [self._entry.data[CONF_USER_ID]]),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_ALLOWED_ROOMS,
                    default=value(
                        CONF_ALLOWED_ROOMS, [self._entry.data[CONF_DEFAULT_ROOM]]
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_DOWNLOAD_INCOMING_MEDIA,
                    default=value(CONF_DOWNLOAD_INCOMING_MEDIA, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ROUTING_PROFILES,
                    default=value(CONF_ROUTING_PROFILES, {}),
                ): selector.ObjectSelector(),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
