"""Config flow for Matrix Extended."""

from __future__ import annotations

from copy import deepcopy
import secrets
from typing import Any

import voluptuous as vol
import yaml
from nio import AsyncClient
from nio.responses import RoomResolveAliasResponse

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv, selector

from .client import (
    MatrixAuthenticationError,
    MatrixConnectionError,
    MatrixExtendedError,
    async_password_login,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ALLOWED_ROOMS,
    CONF_ALLOWED_USERS,
    CONF_CONTROL_PANELS,
    CONF_DEFAULT_ROOM,
    CONF_DEVICE_ID,
    CONF_DOWNLOAD_INCOMING_MEDIA,
    CONF_HOMESERVER,
    CONF_INCOMING_ENABLED,
    CONF_INCOMING_MEDIA_MAX_MB,
    CONF_INCOMING_MEDIA_RETENTION_DAYS,
    CONF_PANEL_ACTION_CONFIRMATION_REQUIRED,
    CONF_PANEL_ACTION_DATA,
    CONF_PANEL_ACTION_ID,
    CONF_PANEL_ACTION_LABEL,
    CONF_PANEL_ACTION_REACTION,
    CONF_PANEL_ACTION_SERVICE,
    CONF_PANEL_ACTION_TARGET,
    CONF_PANEL_ACTIONS,
    CONF_PANEL_ALLOWED_USERS,
    CONF_PANEL_DEBOUNCE,
    CONF_PANEL_ENABLED,
    CONF_PANEL_ENTITIES,
    CONF_PANEL_ENTITY_ID,
    CONF_PANEL_ENTITY_LABEL,
    CONF_PANEL_ID,
    CONF_PANEL_ROOM_ID,
    CONF_PANEL_TITLE,
    CONF_REQUIRE_E2EE,
    CONF_ROUTE_CONFIRM,
    CONF_ROUTE_NAME,
    CONF_ROUTE_ROOMS,
    CONF_ROUTING_PROFILES,
    CONF_STORE_KEY,
    CONF_USER_ID,
    CONF_VERIFY_SSL,
    CONF_VOICE_ASSIST_ALLOWED_ROOMS,
    CONF_VOICE_ASSIST_ALLOWED_USERS,
    CONF_VOICE_ASSIST_CONVERSATION_AGENT,
    CONF_VOICE_ASSIST_ENABLED,
    CONF_VOICE_ASSIST_LANGUAGE,
    CONF_VOICE_ASSIST_REPLY_MODE,
    CONF_VOICE_ASSIST_STT_ENTITY,
    CONF_VOICE_ASSIST_TTS_ENTITY,
    DEFAULT_INCOMING_MEDIA_MAX_MB,
    DEFAULT_INCOMING_MEDIA_RETENTION_DAYS,
    DOMAIN,
)
from .control_panels import (
    DEFAULT_PANEL_DEBOUNCE,
    dump_panel_yaml,
    load_panel_yaml,
    normalize_control_panels,
)
from .routing import normalize_routing_profiles

CONF_PASSWORD = "password"
CONF_PANEL_OPERATION = "panel_operation"
CONF_PANEL_CONFIRM = "panel_confirm"
CONF_PANEL_YAML = "panel_yaml"

_PANEL_OPERATION_DETAILS = "details"
_PANEL_OPERATION_ACTION_ADD = "action_add"
_PANEL_OPERATION_ACTION_EDIT = "action_edit"
_PANEL_OPERATION_ACTION_DELETE = "action_delete"


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
        self._panel_id: str | None = None
        self._panel_draft: dict[str, Any] | None = None
        self._panel_action_id: str | None = None
        self._panel_import_pending: dict[str, Any] | None = None

    def _value(self, key: str, default: Any = None) -> Any:
        return self._entry.options.get(key, self._entry.data.get(key, default))

    def _routes(self) -> dict[str, list[str]]:
        return normalize_routing_profiles(self._value(CONF_ROUTING_PROFILES, {}))

    def _finish(self, updates: dict[str, Any]) -> dict[str, Any]:
        options = dict(self._entry.options)
        options.update(updates)
        return self.async_create_entry(title="", data=options)

    def _account(self) -> Any:
        return self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)

    def _raw_panels(self) -> list[dict[str, Any]]:
        raw = self._value(CONF_CONTROL_PANELS, [])
        if not isinstance(raw, list):
            return []
        return [deepcopy(item) for item in raw if isinstance(item, dict)]

    def _panel_policy(self) -> tuple[set[str], set[str]]:
        account = self._account()
        policy = getattr(account, "incoming_policy", None) if account is not None else None
        if policy is None:
            raise ValueError("panel_runtime_unavailable")
        return (
            set(account.incoming_policy.allowed_users),
            set(account.incoming_policy.allowed_rooms),
        )

    def _validate_panels(self, panels: list[dict[str, Any]]) -> None:
        allowed_users, allowed_rooms = self._panel_policy()
        normalize_control_panels(
            panels,
            account_allowed_users=allowed_users,
            account_allowed_room_ids=allowed_rooms,
        )

    def _panel_room_options(self) -> list[str]:
        _, allowed_rooms = self._panel_policy()
        account = self._account()
        joined = {
            str(getattr(room, "room_id", ""))
            for room in (getattr(account, "rooms", None) or [])
            if getattr(room, "room_id", None)
        }
        rooms = allowed_rooms & joined if joined else allowed_rooms
        return sorted(rooms)

    def _panel_service_options(self) -> list[str]:
        services = self.hass.services.async_services()
        return sorted(
            f"{domain}.{service}"
            for domain, domain_services in services.items()
            for service in domain_services
        )

    @staticmethod
    def _panel_from_yaml_definition(panel: Any) -> dict[str, Any]:
        raw = yaml.safe_load(dump_panel_yaml(panel))
        if not isinstance(raw, dict):
            raise ValueError("invalid panel export")
        return raw

    def _draft_base(self) -> dict[str, Any] | None:
        return deepcopy(self._panel_draft) if self._panel_draft is not None else None

    def _load_panel_draft(self, panel_id: str) -> bool:
        for panel in self._raw_panels():
            if str(panel.get(CONF_PANEL_ID, "")) == panel_id:
                self._panel_id = panel_id
                self._panel_draft = panel
                self._panel_action_id = None
                return True
        return False

    def _validate_draft(self, draft: dict[str, Any]) -> None:
        panels = self._raw_panels()
        panel_id = str(draft.get(CONF_PANEL_ID, ""))
        replaced = False
        for index, existing in enumerate(panels):
            if str(existing.get(CONF_PANEL_ID, "")) == panel_id:
                panels[index] = deepcopy(draft)
                replaced = True
                break
        if not replaced:
            panels.append(deepcopy(draft))
        self._validate_panels(panels)

    def _save_draft(self) -> dict[str, Any]:
        draft = self._draft_base()
        if draft is None:
            raise ValueError("no panel is being edited")
        panels = self._raw_panels()
        panel_id = str(draft[CONF_PANEL_ID])
        replaced = False
        for index, existing in enumerate(panels):
            if str(existing.get(CONF_PANEL_ID, "")) == panel_id:
                panels[index] = draft
                replaced = True
                break
        if not replaced:
            panels.append(draft)
        self._validate_panels(panels)
        return self._finish({CONF_CONTROL_PANELS: panels})

    def _reset_panel_editor(self) -> None:
        self._panel_id = None
        self._panel_draft = None
        self._panel_action_id = None
        self._panel_import_pending = None

    def _panel_details_schema(
        self, draft: dict[str, Any] | None, *, include_id: bool
    ) -> vol.Schema:
        current = draft or {}
        room_options = self._panel_room_options()
        current_room = str(current.get(CONF_PANEL_ROOM_ID, ""))
        default_room = current_room or (room_options[0] if room_options else "")
        schema: dict[Any, Any] = {}
        if include_id:
            schema[
                vol.Required(
                    CONF_PANEL_ID,
                    default=str(current.get(CONF_PANEL_ID, "")),
                )
            ] = selector.TextSelector(selector.TextSelectorConfig())
        schema[
            vol.Required(
                CONF_PANEL_ROOM_ID,
                default=default_room,
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=room_options)
        )
        schema[
            vol.Required(
                CONF_PANEL_TITLE,
                default=str(current.get(CONF_PANEL_TITLE, "")),
            )
        ] = selector.TextSelector(selector.TextSelectorConfig())
        schema[
            vol.Optional(
                CONF_PANEL_ENABLED,
                default=bool(current.get(CONF_PANEL_ENABLED, True)),
            )
        ] = selector.BooleanSelector()
        schema[
            vol.Optional(
                CONF_PANEL_ENTITIES,
                default=[
                    str(item.get(CONF_PANEL_ENTITY_ID))
                    for item in current.get(CONF_PANEL_ENTITIES, [])
                    if isinstance(item, dict) and item.get(CONF_PANEL_ENTITY_ID)
                ],
            )
        ] = selector.EntitySelector(selector.EntitySelectorConfig(multiple=True))
        schema[
            vol.Optional(
                CONF_PANEL_ALLOWED_USERS,
                default=_list(current.get(CONF_PANEL_ALLOWED_USERS, [])),
            )
        ] = selector.TextSelector(selector.TextSelectorConfig(multiple=True))
        schema[
            vol.Optional(
                CONF_PANEL_DEBOUNCE,
                default=float(current.get(CONF_PANEL_DEBOUNCE, DEFAULT_PANEL_DEBOUNCE)),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.25,
                max=10.0,
                step=0.25,
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        return vol.Schema(schema)

    def _details_to_draft(
        self,
        user_input: dict[str, Any],
        *,
        existing: dict[str, Any] | None,
        include_id: bool,
    ) -> dict[str, Any]:
        previous = existing or {}
        panel_id = (
            str(user_input[CONF_PANEL_ID]).strip()
            if include_id
            else str(previous[CONF_PANEL_ID]).strip()
        )
        entities = [
            {
                CONF_PANEL_ENTITY_ID: entity_id,
                CONF_PANEL_ENTITY_LABEL: entity_id,
            }
            for entity_id in _list(user_input.get(CONF_PANEL_ENTITIES, []))
        ]
        return {
            CONF_PANEL_ID: panel_id,
            CONF_PANEL_ROOM_ID: str(user_input[CONF_PANEL_ROOM_ID]).strip(),
            CONF_PANEL_TITLE: str(user_input[CONF_PANEL_TITLE]).strip(),
            CONF_PANEL_ENABLED: bool(user_input.get(CONF_PANEL_ENABLED, True)),
            CONF_PANEL_ENTITIES: entities,
            CONF_PANEL_ACTIONS: deepcopy(previous.get(CONF_PANEL_ACTIONS, [])),
            CONF_PANEL_ALLOWED_USERS: _list(
                user_input.get(CONF_PANEL_ALLOWED_USERS, [])
            ),
            CONF_PANEL_DEBOUNCE: float(
                user_input.get(CONF_PANEL_DEBOUNCE, DEFAULT_PANEL_DEBOUNCE)
            ),
        }

    @staticmethod
    def _action_data_text(action: dict[str, Any]) -> str:
        data = action.get(CONF_PANEL_ACTION_DATA, {})
        if not isinstance(data, dict) or not data:
            return ""
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()

    def _action_schema(self, current: dict[str, Any] | None = None) -> vol.Schema:
        action = current or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_PANEL_ACTION_ID,
                    default=str(action.get(CONF_PANEL_ACTION_ID, "")),
                ): selector.TextSelector(selector.TextSelectorConfig()),
                vol.Required(
                    CONF_PANEL_ACTION_REACTION,
                    default=str(action.get(CONF_PANEL_ACTION_REACTION, "")),
                ): selector.TextSelector(selector.TextSelectorConfig()),
                vol.Required(
                    CONF_PANEL_ACTION_LABEL,
                    default=str(action.get(CONF_PANEL_ACTION_LABEL, "")),
                ): selector.TextSelector(selector.TextSelectorConfig()),
                vol.Required(
                    CONF_PANEL_ACTION_SERVICE,
                    default=str(action.get(CONF_PANEL_ACTION_SERVICE, "")),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._panel_service_options(),
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_PANEL_ACTION_TARGET,
                    default=deepcopy(action.get(CONF_PANEL_ACTION_TARGET, {})),
                ): selector.TargetSelector(),
                vol.Optional(
                    CONF_PANEL_ACTION_DATA,
                    default=self._action_data_text(action),
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_PANEL_ACTION_CONFIRMATION_REQUIRED,
                    default=bool(
                        action.get(CONF_PANEL_ACTION_CONFIRMATION_REQUIRED, False)
                    ),
                ): selector.BooleanSelector(),
            }
        )

    @staticmethod
    def _action_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
        raw_data = str(user_input.get(CONF_PANEL_ACTION_DATA, "")).strip()
        if raw_data:
            parsed_data = yaml.safe_load(raw_data)
            if not isinstance(parsed_data, dict):
                raise ValueError("action data must be a mapping")
        else:
            parsed_data = {}
        return {
            CONF_PANEL_ACTION_ID: str(user_input[CONF_PANEL_ACTION_ID]).strip(),
            CONF_PANEL_ACTION_REACTION: str(
                user_input[CONF_PANEL_ACTION_REACTION]
            ).strip(),
            CONF_PANEL_ACTION_LABEL: str(user_input[CONF_PANEL_ACTION_LABEL]).strip(),
            CONF_PANEL_ACTION_SERVICE: str(
                user_input[CONF_PANEL_ACTION_SERVICE]
            ).strip(),
            CONF_PANEL_ACTION_TARGET: deepcopy(
                user_input.get(CONF_PANEL_ACTION_TARGET, {})
            ),
            CONF_PANEL_ACTION_DATA: parsed_data,
            CONF_PANEL_ACTION_CONFIRMATION_REQUIRED: bool(
                user_input.get(CONF_PANEL_ACTION_CONFIRMATION_REQUIRED, False)
            ),
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show the settings menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "incoming",
                "media",
                "voice_assist",
                "routes",
                "control_panels",
            ],
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

    async def async_step_voice_assist(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit automatic Matrix voice-to-Assist settings."""
        if user_input is not None:
            return self._finish(
                {
                    CONF_VOICE_ASSIST_ENABLED: bool(
                        user_input.get(CONF_VOICE_ASSIST_ENABLED, False)
                    ),
                    CONF_VOICE_ASSIST_STT_ENTITY: user_input.get(
                        CONF_VOICE_ASSIST_STT_ENTITY
                    ),
                    CONF_VOICE_ASSIST_LANGUAGE: user_input.get(
                        CONF_VOICE_ASSIST_LANGUAGE
                    ),
                    CONF_VOICE_ASSIST_CONVERSATION_AGENT: user_input.get(
                        CONF_VOICE_ASSIST_CONVERSATION_AGENT
                    ),
                    CONF_VOICE_ASSIST_REPLY_MODE: user_input.get(
                        CONF_VOICE_ASSIST_REPLY_MODE, "text"
                    ),
                    CONF_VOICE_ASSIST_TTS_ENTITY: user_input.get(
                        CONF_VOICE_ASSIST_TTS_ENTITY
                    ),
                    CONF_VOICE_ASSIST_ALLOWED_USERS: _list(
                        user_input.get(CONF_VOICE_ASSIST_ALLOWED_USERS, [])
                    ),
                    CONF_VOICE_ASSIST_ALLOWED_ROOMS: _list(
                        user_input.get(CONF_VOICE_ASSIST_ALLOWED_ROOMS, [])
                    ),
                }
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_VOICE_ASSIST_ENABLED,
                    default=self._value(CONF_VOICE_ASSIST_ENABLED, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_VOICE_ASSIST_STT_ENTITY,
                    description={
                        "suggested_value": self._value(CONF_VOICE_ASSIST_STT_ENTITY)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="stt")
                ),
                vol.Optional(
                    CONF_VOICE_ASSIST_LANGUAGE,
                    description={
                        "suggested_value": self._value(CONF_VOICE_ASSIST_LANGUAGE)
                    },
                ): selector.TextSelector(selector.TextSelectorConfig()),
                vol.Optional(
                    CONF_VOICE_ASSIST_CONVERSATION_AGENT,
                    description={
                        "suggested_value": self._value(
                            CONF_VOICE_ASSIST_CONVERSATION_AGENT
                        )
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="conversation")
                ),
                vol.Optional(
                    CONF_VOICE_ASSIST_REPLY_MODE,
                    default=self._value(CONF_VOICE_ASSIST_REPLY_MODE, "text"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["text", "voice", "both"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_VOICE_ASSIST_TTS_ENTITY,
                    description={
                        "suggested_value": self._value(CONF_VOICE_ASSIST_TTS_ENTITY)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="tts")
                ),
                vol.Optional(
                    CONF_VOICE_ASSIST_ALLOWED_USERS,
                    default=self._value(CONF_VOICE_ASSIST_ALLOWED_USERS, []),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_VOICE_ASSIST_ALLOWED_ROOMS,
                    default=self._value(CONF_VOICE_ASSIST_ALLOWED_ROOMS, []),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
            }
        )
        return self.async_show_form(step_id="voice_assist", data_schema=schema)

    async def async_step_control_panels(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show graphical native Matrix control-panel management."""
        self._reset_panel_editor()
        menu = ["panel_add", "panel_import"]
        if self._raw_panels():
            menu.extend(
                [
                    "panel_edit",
                    "panel_delete",
                    "panel_repair",
                    "panel_export_select",
                ]
            )
        return self.async_show_menu(step_id="control_panels", menu_options=menu)

    async def async_step_panel_add(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new panel draft before adding actions and saving."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                draft = self._details_to_draft(
                    user_input,
                    existing=None,
                    include_id=True,
                )
                self._validate_draft(draft)
            except ValueError:
                errors["base"] = "invalid_panel"
            else:
                self._panel_id = str(draft[CONF_PANEL_ID])
                self._panel_draft = draft
                return await self.async_step_panel_manage()
        try:
            schema = self._panel_details_schema(None, include_id=True)
        except ValueError:
            return self.async_abort(reason="panel_runtime_unavailable")
        return self.async_show_form(
            step_id="panel_add",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_panel_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Choose a configured panel and open its graphical editor."""
        panels = self._raw_panels()
        if not panels:
            return await self.async_step_control_panels()
        panel_ids = sorted(str(item.get(CONF_PANEL_ID, "")) for item in panels)
        if user_input is not None:
            panel_id = str(user_input[CONF_PANEL_ID])
            if self._load_panel_draft(panel_id):
                return await self.async_step_panel_manage()
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=panel_ids)
                )
            }
        )
        return self.async_show_form(step_id="panel_edit", data_schema=schema)

    async def async_step_panel_manage(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show draft details/actions without mutating config until Save."""
        draft = self._panel_draft
        if draft is None:
            return await self.async_step_control_panels()
        menu = ["panel_edit_details", "panel_action_add"]
        if draft.get(CONF_PANEL_ACTIONS):
            menu.extend(["panel_action_edit", "panel_action_delete"])
        menu.extend(["panel_save", "panel_cancel"])
        return self.async_show_menu(step_id="panel_manage", menu_options=menu)

    async def async_step_panel_edit_details(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Edit panel room, title, entities, allowlist and debounce."""
        draft = self._draft_base()
        if draft is None:
            return await self.async_step_control_panels()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                updated = self._details_to_draft(
                    user_input,
                    existing=draft,
                    include_id=False,
                )
                self._validate_draft(updated)
            except ValueError:
                errors["base"] = "invalid_panel"
            else:
                self._panel_draft = updated
                return await self.async_step_panel_manage()
        try:
            schema = self._panel_details_schema(draft, include_id=False)
        except ValueError:
            return self.async_abort(reason="panel_runtime_unavailable")
        return self.async_show_form(
            step_id="panel_edit_details",
            data_schema=schema,
            errors=errors,
            description_placeholders={"panel_id": str(draft[CONF_PANEL_ID])},
        )

    async def async_step_panel_action_add(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Add one locally-defined safe action to the current panel draft."""
        draft = self._draft_base()
        if draft is None:
            return await self.async_step_control_panels()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                action = self._action_from_input(user_input)
                updated = deepcopy(draft)
                updated.setdefault(CONF_PANEL_ACTIONS, []).append(action)
                self._validate_draft(updated)
            except (ValueError, yaml.YAMLError):
                errors["base"] = "invalid_panel_action"
            else:
                self._panel_draft = updated
                return await self.async_step_panel_manage()
        return self.async_show_form(
            step_id="panel_action_add",
            data_schema=self._action_schema(),
            errors=errors,
        )

    async def async_step_panel_action_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Choose then edit one safe action in the current panel draft."""
        draft = self._draft_base()
        if draft is None:
            return await self.async_step_control_panels()
        actions = [
            item
            for item in draft.get(CONF_PANEL_ACTIONS, [])
            if isinstance(item, dict) and item.get(CONF_PANEL_ACTION_ID)
        ]
        if not actions:
            return await self.async_step_panel_manage()
        if self._panel_action_id is None:
            if user_input is not None:
                self._panel_action_id = str(user_input[CONF_PANEL_ACTION_ID])
                return await self.async_step_panel_action_edit()
            schema = vol.Schema(
                {
                    vol.Required(CONF_PANEL_ACTION_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=sorted(
                                str(item[CONF_PANEL_ACTION_ID]) for item in actions
                            )
                        )
                    )
                }
            )
            return self.async_show_form(
                step_id="panel_action_edit",
                data_schema=schema,
            )

        current = next(
            (
                item
                for item in actions
                if str(item[CONF_PANEL_ACTION_ID]) == self._panel_action_id
            ),
            None,
        )
        if current is None:
            self._panel_action_id = None
            return await self.async_step_panel_action_edit()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                replacement = self._action_from_input(user_input)
                updated = deepcopy(draft)
                for index, item in enumerate(updated.get(CONF_PANEL_ACTIONS, [])):
                    if str(item.get(CONF_PANEL_ACTION_ID, "")) == self._panel_action_id:
                        updated[CONF_PANEL_ACTIONS][index] = replacement
                        break
                self._validate_draft(updated)
            except (ValueError, yaml.YAMLError):
                errors["base"] = "invalid_panel_action"
            else:
                self._panel_draft = updated
                self._panel_action_id = None
                return await self.async_step_panel_manage()
        return self.async_show_form(
            step_id="panel_action_edit",
            data_schema=self._action_schema(current),
            errors=errors,
            description_placeholders={"action_id": self._panel_action_id},
        )

    async def async_step_panel_action_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Delete an action from the draft after explicit confirmation."""
        draft = self._draft_base()
        if draft is None:
            return await self.async_step_control_panels()
        actions = [
            item
            for item in draft.get(CONF_PANEL_ACTIONS, [])
            if isinstance(item, dict) and item.get(CONF_PANEL_ACTION_ID)
        ]
        if not actions:
            return await self.async_step_panel_manage()
        errors: dict[str, str] = {}
        if user_input is not None:
            action_id = str(user_input[CONF_PANEL_ACTION_ID])
            if not bool(user_input[CONF_PANEL_CONFIRM]):
                errors[CONF_PANEL_CONFIRM] = "confirm_delete"
            else:
                updated = deepcopy(draft)
                updated[CONF_PANEL_ACTIONS] = [
                    item
                    for item in updated.get(CONF_PANEL_ACTIONS, [])
                    if str(item.get(CONF_PANEL_ACTION_ID, "")) != action_id
                ]
                self._panel_draft = updated
                return await self.async_step_panel_manage()
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_ACTION_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(str(item[CONF_PANEL_ACTION_ID]) for item in actions)
                    )
                ),
                vol.Required(
                    CONF_PANEL_CONFIRM, default=False
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="panel_action_delete",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_panel_save(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate the complete draft then persist it atomically in options."""
        if self._panel_draft is None:
            return await self.async_step_control_panels()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not bool(user_input[CONF_PANEL_CONFIRM]):
                errors[CONF_PANEL_CONFIRM] = "confirm_save"
            else:
                try:
                    return self._save_draft()
                except ValueError:
                    errors["base"] = "invalid_panel"
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PANEL_CONFIRM, default=False
                ): selector.BooleanSelector()
            }
        )
        return self.async_show_form(
            step_id="panel_save",
            data_schema=schema,
            errors=errors,
            description_placeholders={"panel_id": str(self._panel_draft[CONF_PANEL_ID])},
        )

    async def async_step_panel_cancel(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Discard the in-memory draft and return to panel management."""
        self._reset_panel_editor()
        return await self.async_step_control_panels()

    async def async_step_panel_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Delete a configured panel after explicit confirmation."""
        panels = self._raw_panels()
        if not panels:
            return await self.async_step_control_panels()
        errors: dict[str, str] = {}
        if user_input is not None:
            panel_id = str(user_input[CONF_PANEL_ID])
            if not bool(user_input[CONF_PANEL_CONFIRM]):
                errors[CONF_PANEL_CONFIRM] = "confirm_delete"
            else:
                remaining = [
                    item
                    for item in panels
                    if str(item.get(CONF_PANEL_ID, "")) != panel_id
                ]
                try:
                    self._validate_panels(remaining)
                except ValueError:
                    errors["base"] = "invalid_panel"
                else:
                    return self._finish({CONF_CONTROL_PANELS: remaining})
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(
                            str(item.get(CONF_PANEL_ID, "")) for item in panels
                        )
                    )
                ),
                vol.Required(
                    CONF_PANEL_CONFIRM, default=False
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="panel_delete",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_panel_repair(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Explicitly repair a missing/redacted root without changing config."""
        panels = self._raw_panels()
        if not panels:
            return await self.async_step_control_panels()
        errors: dict[str, str] = {}
        if user_input is not None:
            panel_id = str(user_input[CONF_PANEL_ID])
            account = self._account()
            if account is None or account.panel_manager is None:
                errors["base"] = "panel_runtime_unavailable"
            else:
                try:
                    await account.panel_manager.async_repair(panel_id)
                except ValueError:
                    errors["base"] = "panel_not_needs_repair"
                except MatrixExtendedError:
                    errors["base"] = "panel_repair_failed"
                else:
                    return await self.async_step_control_panels()
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(
                            str(item.get(CONF_PANEL_ID, "")) for item in panels
                        )
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="panel_repair",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_panel_import(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Import one panel through the same safe parser and validator."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                allowed_users, allowed_rooms = self._panel_policy()
                panel = load_panel_yaml(
                    str(user_input[CONF_PANEL_YAML]),
                    account_allowed_users=allowed_users,
                    account_allowed_room_ids=allowed_rooms,
                )
                raw = self._panel_from_yaml_definition(panel)
                panels = self._raw_panels()
                existing = next(
                    (
                        item
                        for item in panels
                        if str(item.get(CONF_PANEL_ID, "")) == panel.panel_id
                    ),
                    None,
                )
                if existing is not None:
                    self._panel_import_pending = raw
                    return await self.async_step_panel_import_confirm()
                panels.append(raw)
                self._validate_panels(panels)
            except (ValueError, yaml.YAMLError):
                errors["base"] = "invalid_panel_yaml"
            else:
                return self._finish({CONF_CONTROL_PANELS: panels})
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_YAML): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                )
            }
        )
        return self.async_show_form(
            step_id="panel_import",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_panel_import_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Require explicit confirmation before replacing an imported panel."""
        pending = self._panel_import_pending
        if pending is None:
            return await self.async_step_panel_import()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not bool(user_input[CONF_PANEL_CONFIRM]):
                errors[CONF_PANEL_CONFIRM] = "confirm_replace"
            else:
                panel_id = str(pending[CONF_PANEL_ID])
                panels = self._raw_panels()
                panels = [
                    deepcopy(pending)
                    if str(item.get(CONF_PANEL_ID, "")) == panel_id
                    else item
                    for item in panels
                ]
                try:
                    self._validate_panels(panels)
                except ValueError:
                    errors["base"] = "invalid_panel_yaml"
                else:
                    return self._finish({CONF_CONTROL_PANELS: panels})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PANEL_CONFIRM, default=False
                ): selector.BooleanSelector()
            }
        )
        return self.async_show_form(
            step_id="panel_import_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"panel_id": str(pending[CONF_PANEL_ID])},
        )

    async def async_step_panel_export_select(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Choose a configured panel for YAML export."""
        panels = self._raw_panels()
        if not panels:
            return await self.async_step_control_panels()
        if user_input is not None:
            self._panel_id = str(user_input[CONF_PANEL_ID])
            return await self.async_step_panel_export()
        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=sorted(
                            str(item.get(CONF_PANEL_ID, "")) for item in panels
                        )
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="panel_export_select",
            data_schema=schema,
        )

    async def async_step_panel_export(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Display validated YAML without mutating integration options."""
        panel_id = self._panel_id
        if panel_id is None:
            return await self.async_step_panel_export_select()
        try:
            allowed_users, allowed_rooms = self._panel_policy()
            definitions = normalize_control_panels(
                self._raw_panels(),
                account_allowed_users=allowed_users,
                account_allowed_room_ids=allowed_rooms,
            )
            panel = definitions[panel_id]
        except (KeyError, ValueError):
            return await self.async_step_control_panels()
        yaml_text = dump_panel_yaml(panel)
        if user_input is not None:
            return await self.async_step_control_panels()
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PANEL_YAML, default=yaml_text
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            }
        )
        return self.async_show_form(
            step_id="panel_export",
            data_schema=schema,
            description_placeholders={"panel_id": panel_id},
        )

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
