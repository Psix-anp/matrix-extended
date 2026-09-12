"""Modern notify entities for Matrix Extended."""

from __future__ import annotations

from hashlib import sha256
from html import escape
from typing import Any, override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import MatrixAccount, MatrixEncryptionRequiredError, MatrixExtendedError
from .const import DOMAIN
from .content import build_text_content
from .rooms import MatrixRoomInfo


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up default and per-room Matrix notify entities."""
    account: MatrixAccount = hass.data[DOMAIN][config_entry.entry_id]
    # Use the matrix-nio room state captured by the initial full sync. A reload
    # refreshes the room entity set when membership changes.
    rooms_snapshot = account.client.rooms_snapshot()
    account.rooms = rooms_snapshot
    entities: list[NotifyEntity] = [MatrixExtendedNotifyEntity(config_entry, account)]
    entities.extend(
        MatrixRoomNotifyEntity(config_entry, account, room)
        for room in rooms_snapshot
    )
    async_add_entities(entities)


class MatrixBaseNotifyEntity(NotifyEntity):
    """Common Matrix notify behavior."""

    _attr_has_entity_name = True
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        self._account = account
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Matrix {entry.title}",
        )

    async def _async_send_to(
        self,
        room: str,
        message: str,
        title: str | None,
    ) -> None:
        if title:
            body = f"{title}\n{message}"
            formatted = f"<strong>{escape(title)}</strong><br>{escape(message)}"
        else:
            body = message
            formatted = None
        content = build_text_content(body, formatted_body=formatted)
        try:
            await self._account.client.async_send_content(room, content)
            self._account.status.mark_send_success()
        except MatrixEncryptionRequiredError as err:
            self._account.status.mark_error(str(err), connected=True)
            raise
        except MatrixExtendedError as err:
            self._account.status.mark_error(str(err))
            raise


class MatrixExtendedNotifyEntity(MatrixBaseNotifyEntity):
    """Send notifications to the selected default Matrix room."""

    _attr_name = None

    def __init__(self, entry: ConfigEntry, account: MatrixAccount) -> None:
        super().__init__(entry, account)
        self._attr_unique_id = f"{entry.entry_id}_notify"

    @override
    async def async_send_message(
        self, message: str, title: str | None = None
    ) -> None:
        """Send to the configured default room."""
        await self._async_send_to(self._account.default_room, message, title)


class MatrixRoomNotifyEntity(MatrixBaseNotifyEntity):
    """Send notifications directly to one joined Matrix room."""

    def __init__(
        self,
        entry: ConfigEntry,
        account: MatrixAccount,
        room: MatrixRoomInfo,
    ) -> None:
        super().__init__(entry, account)
        self._room = room
        digest = sha256(room.room_id.encode()).hexdigest()[:16]
        self._attr_unique_id = f"{entry.entry_id}_notify_room_{digest}"
        self._attr_name = room.display_name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful room metadata without creating extra entities."""
        return {
            "room_id": self._room.room_id,
            "canonical_alias": self._room.canonical_alias,
            "encrypted": self._room.encrypted,
            "joined_members": self._room.joined_count,
        }

    @override
    async def async_send_message(
        self, message: str, title: str | None = None
    ) -> None:
        """Send directly to this Matrix room."""
        await self._async_send_to(self._room.room_id, message, title)
