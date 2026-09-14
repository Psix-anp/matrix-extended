"""Binary sensors for Matrix Extended."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import MatrixAccount
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Matrix connection health."""
    account: MatrixAccount = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            MatrixConnectedBinarySensor(config_entry, account),
            MatrixE2EEReadyBinarySensor(config_entry, account),
        ]
    )


class MatrixConnectedBinarySensor(BinarySensorEntity):
    """Expose whether the Matrix homeserver is currently reachable."""

    _attr_has_entity_name = True
    _attr_translation_key = "connected"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        self._account = account
        self._attr_unique_id = f"{entry.entry_id}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Matrix {entry.title}",
        )

    @property
    def is_on(self) -> bool:
        """Return connection state."""
        return bool(self._account.status.connected)

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime status updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._account.status.add_listener(self.async_write_ha_state)
        )


class MatrixE2EEReadyBinarySensor(BinarySensorEntity):
    """Expose whether the connected account has an encrypted default room."""

    _attr_has_entity_name = True
    _attr_translation_key = "e2ee_ready"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        self._account = account
        self._attr_unique_id = f"{entry.entry_id}_e2ee_ready"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Matrix {entry.title}",
        )

    @property
    def is_on(self) -> bool:
        """Return conservative E2EE readiness."""
        return bool(
            self._account.status.connected
            and self._account.status.default_room_encrypted is True
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._account.status.add_listener(self.async_write_ha_state)
        )
