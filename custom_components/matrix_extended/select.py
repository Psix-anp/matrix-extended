"""Room selection entities for Matrix Extended."""

from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import MatrixAccount
from .const import CONF_DEFAULT_ROOM, DOMAIN
from .rooms import build_room_labels


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matrix room selectors."""
    account: MatrixAccount = hass.data[DOMAIN][config_entry.entry_id]
    if not account.rooms:
        return
    async_add_entities([MatrixDefaultRoomSelect(hass, config_entry, account)])


class MatrixDefaultRoomSelect(SelectEntity):
    """Select the default outbound Matrix room."""

    _attr_has_entity_name = True
    _attr_translation_key = "default_room"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        account: MatrixAccount,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._account = account
        self._labels = build_room_labels(account.rooms or [])
        self._room_to_label = {room_id: label for label, room_id in self._labels.items()}
        self._attr_options = list(self._labels)
        self._attr_unique_id = f"{entry.entry_id}_default_room_select"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Matrix {entry.title}",
        )

    @property
    @override
    def current_option(self) -> str | None:
        """Return the currently configured default room label."""
        return self._room_to_label.get(self._account.default_room_id)

    @override
    async def async_select_option(self, option: str) -> None:
        """Set and persist the default room."""
        room_id = self._labels.get(option)
        if room_id is None:
            raise ValueError(f"Unknown Matrix room option: {option}")
        room = next(
            (item for item in (self._account.rooms or []) if item.room_id == room_id),
            None,
        )
        self._account.default_room = room_id
        self._account.default_room_id = room_id
        if room is not None:
            self._account.status.set_default_room_encryption(room.encrypted)
        data = dict(self._entry.data)
        data[CONF_DEFAULT_ROOM] = room_id
        self._hass.config_entries.async_update_entry(self._entry, data=data)
        self.async_write_ha_state()
