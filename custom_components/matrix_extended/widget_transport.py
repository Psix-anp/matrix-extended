"""Matrix to-device transport adapter for the native Widget protocol."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nio.event_builders import ToDeviceMessage
from nio.responses import ToDeviceError


class WidgetTransportError(Exception):
    """Base Widget transport error."""


class WidgetTransportConnectionError(WidgetTransportError):
    """The homeserver request failed before a Matrix response was received."""


class WidgetTransportSendError(WidgetTransportError):
    """Matrix rejected a Widget to-device event."""


class WidgetTransport:
    """Thin matrix-nio adapter with no authorization policy."""

    def __init__(self, nio_client: Any) -> None:
        self._nio_client = nio_client

    def add_callback(self, callback: Any, event_filter: Any) -> None:
        self._nio_client.add_to_device_callback(callback, event_filter)

    async def async_send(
        self,
        event_type: str,
        user_id: str,
        device_id: str,
        content: Mapping[str, Any],
    ) -> None:
        message = ToDeviceMessage(
            str(event_type),
            str(user_id),
            str(device_id),
            dict(content),
        )
        try:
            response = await self._nio_client.to_device(message)
        except Exception as err:
            raise WidgetTransportConnectionError(str(err)) from err
        if isinstance(response, ToDeviceError):
            detail = getattr(response, "message", None) or str(response)
            raise WidgetTransportSendError(str(detail))
