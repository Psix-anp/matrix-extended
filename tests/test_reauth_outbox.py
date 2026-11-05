import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_auth_failure_keeps_pending_delivery_for_after_reauth():
    component = Path(__file__).parents[1] / "custom_components/matrix_extended/__init__.py"
    node = next(node for node in ast.parse(component.read_text(encoding="utf-8")).body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_outbox_worker")

    class MatrixExtendedError(Exception):
        pass

    class MatrixAuthenticationError(MatrixExtendedError):
        pass

    class MatrixConnectionError(MatrixExtendedError):
        pass

    class MatrixEncryptionRequiredError(MatrixExtendedError):
        pass

    class Outbox:
        pending_item = SimpleNamespace(delivery_id="notification", payload={})

        def pending(self):
            return [self.pending_item] if self.pending_item else []

        async def async_remove(self, delivery_id):
            self.pending_item = None

    async def send(*args, **kwargs):
        raise MatrixAuthenticationError("session expired")

    async def stop_on_retry(delay):
        raise asyncio.CancelledError

    outbox = Outbox()
    errors = []
    account = SimpleNamespace(outbox=outbox, status=SimpleNamespace(
        connected=True, last_error=None, mark_error=errors.append))
    delivery_states = []
    scope = {
        "asyncio": SimpleNamespace(CancelledError=asyncio.CancelledError, sleep=stop_on_retry),
        "HomeAssistant": object, "MatrixAccount": object, "HomeAssistantError": RuntimeError,
        "_async_execute_send": send, "_OUTBOX_RETRY_SECONDS": 5,
        "_LOGGER": SimpleNamespace(warning=lambda *args: None),
        "_fire_delivery": lambda hass, account, delivery_id, status, **kw: delivery_states.append(status),
        "MatrixConnectionError": MatrixConnectionError,
        "MatrixAuthenticationError": MatrixAuthenticationError,
        "MatrixEncryptionRequiredError": MatrixEncryptionRequiredError,
        "MatrixExtendedError": MatrixExtendedError,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(component), "exec"), scope)
    with pytest.raises(asyncio.CancelledError):
        await scope["_async_outbox_worker"](None, account)
    assert outbox.pending_item.delivery_id == "notification"
    assert delivery_states == []
    assert errors == ["session expired"]
