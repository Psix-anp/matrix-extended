"""Diagnostic sensors for Matrix Extended."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    """Set up Matrix diagnostic sensors."""
    account: MatrixAccount = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            MatrixStaticSensor(config_entry, account, "user_id", account.user_id),
            MatrixStaticSensor(config_entry, account, "device_id", account.device_id),
            MatrixStaticSensor(
                config_entry, account, "default_room", account.default_room
            ),
            MatrixEncryptionSensor(config_entry, account),
            MatrixLastSendSensor(config_entry, account),
            MatrixLastReceiveSensor(config_entry, account),
            MatrixLastErrorSensor(config_entry, account),
        ]
    )


class MatrixBaseSensor(SensorEntity):
    """Base Matrix diagnostic sensor."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, account: MatrixAccount, suffix: str) -> None:
        self._account = account
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Matrix {entry.title}",
        )


class MatrixStaticSensor(MatrixBaseSensor):
    """Static account metadata."""

    def __init__(
        self,
        entry: ConfigEntry,
        account: MatrixAccount,
        translation_key: str,
        value: str,
    ) -> None:
        super().__init__(entry, account, translation_key)
        self._attr_translation_key = translation_key
        self._value = value

    @property
    def native_value(self) -> str:
        return self._value


class MatrixDynamicSensor(MatrixBaseSensor):
    """Base sensor backed by MatrixRuntimeStatus."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._account.status.add_listener(self.async_write_ha_state)
        )


class MatrixEncryptionSensor(MatrixDynamicSensor):
    """Default-room encryption state."""

    _attr_translation_key = "default_room_encryption"

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        super().__init__(entry, account, "default_room_encryption")

    @property
    def native_value(self) -> str:
        encrypted = self._account.status.default_room_encrypted
        if encrypted is True:
            return "encrypted"
        if encrypted is False:
            return "not_encrypted"
        return "unknown"


class MatrixLastSendSensor(MatrixDynamicSensor):
    """Timestamp of the most recent successful Matrix send."""

    _attr_translation_key = "last_send"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        super().__init__(entry, account, "last_send")

    @property
    def native_value(self) -> Any:
        return self._account.status.last_send


class MatrixLastReceiveSensor(MatrixDynamicSensor):
    """Most recent authorized incoming Matrix event kind and metadata."""

    _attr_translation_key = "last_receive"

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        super().__init__(entry, account, "last_receive")

    @property
    def native_value(self) -> str | None:
        return self._account.status.last_receive_type

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        received_at = self._account.status.last_receive
        payload = self._account.status.last_receive_payload
        if received_at is None and not payload:
            return None
        attributes = dict(payload)
        if received_at is not None:
            attributes["received_at"] = received_at.isoformat()
        return attributes


class MatrixLastErrorSensor(MatrixDynamicSensor):
    """Most recent Matrix transport/security error."""

    _attr_translation_key = "last_error"

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        super().__init__(entry, account, "last_error")

    @property
    def native_value(self) -> str | None:
        error = self._account.status.last_error
        if error is None:
            return None
        return error[:255]

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        error = self._account.status.last_error
        if error is None or len(error) <= 255:
            return None
        return {"full_error": error}
