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
    CONF_INCOMING_MEDIA_MAX_MB,
    CONF_INCOMING_MEDIA_RETENTION_DAYS,
    CONF_REQUIRE_E2EE,
    CONF_ROUTE_CONFIRM,
    CONF_ROUTE_NAME,
    CONF_ROUTE_ROOMS,
    CONF_ROUTING_PROFILES,
    CONF_STORE_KEY,
    CONF_USER_ID,
    CONF_VERIFY_SSL,
    DEFAULT_INCOMING_MEDIA_MAX_MB,
    DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
    DOMAIN,
)
from .routing import normalize_routing_profiles

CONF_PASSWORD = "password"


async def _async_validate_default_room(
    *,
    homeserver: str,
    user_id: str,
    access_token: str,
    device_id: str,
    verify_ssl: bool,
    room: str,
) -> None:
    """Validate a room ID or resolve a room alias."""
    if room.startswith("!"):
        return
    if not room.startswith("#"):
        raise ValueError("invalid_room")
    client = AsyncClient(homeserver, user_id, device_id=device_id, ssl=verify_ssl)
    client.restore_login(
        user_id=user_id,
        device_id=device_id,
        access_token=access_token,
    )
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
    MINOR_VERSION = 4

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return MatrixExtendedOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Set up Matrix Extended from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            homeserver = user_input[CONF_HOMESERVER].rstrip("/")
            verify_ssl = user_input[CONF_VERIFY_SSL]
            try:
                details = await async_password_login(
                    homeserver,
                    user_input[CONF_USER_ID],
                    user_input[CONF_PASSWORD],
                    verify_ssl,
                )
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
                allowed_users = _list(user_input.get(CONF_ALLOWED_USERS)) or [
                    details.user_id
                ]
                allowed_rooms = _list(user_input.get(CONF_ALLOWED_ROOMS)) or [
                    user_input[CONF_DEFAULT_ROOM]
                ]
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
                        CONF_DOWNLOAD_INCOMING_MEDIA: user_input[
                            CONF_DOWNLOAD_INCOMING_MEDIA
                        ],
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
    """Edit Matrix Extended settings through graphical Home Assistant forms."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._route_name: str | None = None

    def _value(self, key: str, default: Any = None) -> Any:
        return self._entry.options.get(key, self._entry.data.get(key, default))

    def _routes(self) -> dict[str, list[str]]:
        return normalize_routing_profiles(self._value(CONF_ROUTING_PROFILES, {}))

    def _finish(self, updates: dict[str, Any]) -> dict[str, Any]:
        options = dict(self._entry.options)
        options.update(updates)
        return self.async_create_entry(title="", data=options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show the settings menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "incoming", "media", "routes"],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit connection defaults and encryption policy."""
        errors: dict[str, str] = {}
        if user_input is not None:
            room = str(user_input[CONF_DEFAULT_ROOM]).strip()
            verify_ssl = bool(user_input[CONF_VERIFY_SSL])
            try:
                await _async_validate_default_room(
                    homeserver=self._entry.data[CONF_HOMESERVER],
                    user_id=self._entry.data[CONF_USER_ID],
                    access_token=self._entry.data[CONF_ACCESS_TOKEN],
                    device_id=self._entry.data[CONF_DEVICE_ID],
                    verify_ssl=verify_ssl,
                    room=room,
                )
            except ValueError:
                errors[CONF_DEFAULT_ROOM] = "invalid_room"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                connection_data = dict(self._entry.data)
                connection_data[CONF_DEFAULT_ROOM] = room
                connection_data[CONF_VERIFY_SSL] = verify_ssl
                self.hass.config_entries.async_update_entry(
                    self._entry, data=connection_data
                )
                options = dict(self._entry.options)
                options.pop(CONF_DEFAULT_ROOM, None)
                options.pop(CONF_VERIFY_SSL, None)
                options[CONF_REQUIRE_E2EE] = bool(user_input[CONF_REQUIRE_E2EE])
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEFAULT_ROOM,
                    default=self._entry.data[CONF_DEFAULT_ROOM],
                ): selector.TextSelector(selector.TextSelectorConfig()),
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=self._entry.data.get(CONF_VERIFY_SSL, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_REQUIRE_E2EE,
                    default=self._value(CONF_REQUIRE_E2EE, True),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="general", data_schema=schema, errors=errors
        )

    async def async_step_incoming(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit inbound event security allowlists."""
        errors: dict[str, str] = {}
        if user_input is not None:
            enabled = bool(user_input[CONF_INCOMING_ENABLED])
            users = _list(user_input[CONF_ALLOWED_USERS])
            rooms = _list(user_input[CONF_ALLOWED_ROOMS])
            if enabled and not users:
                errors[CONF_ALLOWED_USERS] = "required_when_incoming"
            if enabled and not rooms:
                errors[CONF_ALLOWED_ROOMS] = "required_when_incoming"
            if not errors:
                return self._finish(
                    {
                        CONF_INCOMING_ENABLED: enabled,
                        CONF_ALLOWED_USERS: users,
                        CONF_ALLOWED_ROOMS: rooms,
                    }
                )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INCOMING_ENABLED,
                    default=self._value(CONF_INCOMING_ENABLED, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ALLOWED_USERS,
                    default=self._value(
                        CONF_ALLOWED_USERS, [self._entry.data[CONF_USER_ID]]
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_ALLOWED_ROOMS,
                    default=self._value(
                        CONF_ALLOWED_ROOMS,
                        [self._entry.data[CONF_DEFAULT_ROOM]],
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            }
        )
        return self.async_show_form(
            step_id="incoming", data_schema=schema, errors=errors
        )

    async def async_step_media(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit incoming media download and retention settings."""
        if user_input is not None:
            return self._finish(
                {
                    CONF_DOWNLOAD_INCOMING_MEDIA: bool(
                        user_input[CONF_DOWNLOAD_INCOMING_MEDIA]
                    ),
                    CONF_INCOMING_MEDIA_RETENTION_DAYS: int(
                        user_input[CONF_INCOMING_MEDIA_RETENTION_DAYS]
                    ),
                    CONF_INCOMING_MEDIA_MAX_MB: int(
                        user_input[CONF_INCOMING_MEDIA_MAX_MB]
                    ),
                }
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DOWNLOAD_INCOMING_MEDIA,
                    default=self._value(CONF_DOWNLOAD_INCOMING_MEDIA, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_INCOMING_MEDIA_RETENTION_DAYS,
                    default=self._value(
                        CONF_INCOMING_MEDIA_RETENTION_DAYS,
                        DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=365,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_INCOMING_MEDIA_MAX_MB,
                    default=self._value(
                        CONF_INCOMING_MEDIA_MAX_MB, DEFAULT_INCOMING_MEDIA_MAX_MB
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=16,
                        max=4096,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="media", data_schema=schema)

    async def async_step_routes(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show graphical notification-route management."""
        menu = ["route_add"]
        if self._routes():
            menu.extend(["route_edit", "route_delete"])
        return self.async_show_menu(step_id="routes", menu_options=menu)

    async def async_step_route_add(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Add a named Matrix notification route."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_ROUTE_NAME]).strip()
            rooms = _list(user_input[CONF_ROUTE_ROOMS])
            routes = self._routes()
            if not name:
                errors[CONF_ROUTE_NAME] = "invalid_route_name"
            elif name in routes:
                errors[CONF_ROUTE_NAME] = "route_exists"
            if not rooms:
                errors[CONF_ROUTE_ROOMS] = "route_needs_rooms"
            if not errors:
                routes[name] = rooms
                return self._finish({CONF_ROUTING_PROFILES: routes})

        schema = vol.Schema(
            {
                vol.Required(CONF_ROUTE_NAME): selector.TextSelector(
                    selector.TextSelectorConfig()
                ),
                vol.Required(CONF_ROUTE_ROOMS): selector.TextSelector(
                    selector.TextSelectorConfig(multiple=True)
                ),
            }
        )
        return self.async_show_form(
            step_id="route_add", data_schema=schema, errors=errors
        )

    async def async_step_route_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Choose a route to edit."""
        routes = self._routes()
        if not routes:
            return await self.async_step_routes()
        if user_input is not None:
            self._route_name = str(user_input[CONF_ROUTE_NAME])
            return await self.async_step_route_edit_details()

        schema = vol.Schema(
            {
                vol.Required(CONF_ROUTE_NAME): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=sorted(routes))
                )
            }
        )
        return self.async_show_form(step_id="route_edit", data_schema=schema)

    async def async_step_route_edit_details(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit rooms in the selected route."""
        routes = self._routes()
        name = self._route_name
        if name is None or name not in routes:
            return await self.async_step_route_edit()
        errors: dict[str, str] = {}
        if user_input is not None:
            rooms = _list(user_input[CONF_ROUTE_ROOMS])
            if not rooms:
                errors[CONF_ROUTE_ROOMS] = "route_needs_rooms"
            else:
                routes[name] = rooms
                return self._finish({CONF_ROUTING_PROFILES: routes})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROUTE_ROOMS, default=routes[name]
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True))
            }
        )
        return self.async_show_form(
            step_id="route_edit_details",
            data_schema=schema,
            errors=errors,
            description_placeholders={"route_name": name},
        )

    async def async_step_route_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Delete a named route after explicit confirmation."""
        routes = self._routes()
        if not routes:
            return await self.async_step_routes()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input[CONF_ROUTE_NAME])
            if not bool(user_input[CONF_ROUTE_CONFIRM]):
                errors[CONF_ROUTE_CONFIRM] = "confirm_delete"
            elif name in routes:
                routes.pop(name)
                return self._finish({CONF_ROUTING_PROFILES: routes})

        schema = vol.Schema(
            {
                vol.Required(CONF_ROUTE_NAME): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=sorted(routes))
                ),
                vol.Required(
                    CONF_ROUTE_CONFIRM, default=False
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="route_delete", data_schema=schema, errors=errors
        )
