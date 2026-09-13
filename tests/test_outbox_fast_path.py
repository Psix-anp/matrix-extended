from pathlib import Path

ROOT = Path(__file__).parents[1]
INIT = ROOT / "custom_components" / "matrix_extended" / "__init__.py"


def _send_handler_source() -> str:
    text = INIT.read_text()
    return text.split("async def _async_handle_send", 1)[1].split(
        "\n\nasync def _async_handle_reply", 1
    )[0]


def test_known_disconnected_send_queues_before_live_matrix_io() -> None:
    handler = _send_handler_source()
    guard = "if not account.status.connected:"
    live_send = "events = await _async_execute_send("

    assert guard in handler
    assert "await account.outbox.async_enqueue(payload, delivery_id=delivery_id)" in handler
    assert 'delivery = _fire_delivery(hass, account, delivery_id, "queued")' in handler
    assert "return _delivery_response(delivery)" in handler
    assert handler.index(guard) < handler.index(live_send)
