from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, got {count}")
    file.write_text(text.replace(old, new, 1))


replace_once(
    "custom_components/matrix_extended/__init__.py",
    "    payload = _delivery_payload(account, delivery_id, status, events, error)\n    hass.bus.async_fire(EVENT_DELIVERY, payload)\n",
    "    payload = _delivery_payload(account, delivery_id, status, events, error)\n    account.status.mark_delivery(status)\n    hass.bus.async_fire(EVENT_DELIVERY, payload)\n",
)

replace_once(
    "custom_components/matrix_extended/v05_services.py",
    "    hass.bus.async_fire(EVENT_DELIVERY, payload)\n    return payload\n",
    "    account.status.mark_delivery(status)\n    hass.bus.async_fire(EVENT_DELIVERY, payload)\n    return payload\n",
)

replace_once(
    "custom_components/matrix_extended/receiver.py",
    "            self._hass.bus.async_fire(\n                EVENT_COMMAND,\n",
    "            self._account.status.mark_command(\n                {\n                    \"command_id\": result.command_id,\n                    \"sender\": event.sender,\n                    \"room_id\": room.room_id,\n                    \"handler_type\": result.handler_type,\n                    \"status\": result.status,\n                    \"error\": result.error,\n                }\n            )\n            self._hass.bus.async_fire(\n                EVENT_COMMAND,\n",
)
