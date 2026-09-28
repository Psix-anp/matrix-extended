from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
COMP = ROOT / "custom_components" / "matrix_extended"


class FakeToDeviceMessage:
    def __init__(self, event_type, recipient, recipient_device, content):
        self.type = event_type
        self.recipient = recipient
        self.recipient_device = recipient_device
        self.content = content


class FakeToDeviceError:
    def __init__(self, message="failed"):
        self.message = message


def load_transport():
    nio = types.ModuleType("nio")
    builders = types.ModuleType("nio.event_builders")
    responses = types.ModuleType("nio.responses")
    builders.ToDeviceMessage = FakeToDeviceMessage
    responses.ToDeviceError = FakeToDeviceError
    sys.modules["nio"] = nio
    sys.modules["nio.event_builders"] = builders
    sys.modules["nio.responses"] = responses

    pkg_name = "matrix_extended_widget_transport_v060b2_testpkg"
    package = types.ModuleType(pkg_name)
    package.__path__ = [str(COMP)]
    sys.modules[pkg_name] = package
    sys.modules.pop(f"{pkg_name}.widget_transport", None)
    return importlib.import_module(f"{pkg_name}.widget_transport")


class FakeNioClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.callbacks = []
        self.sent = []

    def add_to_device_callback(self, callback, event_filter):
        self.callbacks.append((callback, event_filter))

    async def to_device(self, message):
        self.sent.append(message)
        if self.error is not None:
            raise self.error
        return self.response


def test_callback_registration_delegates_to_nio():
    mod = load_transport()
    nio_client = FakeNioClient()
    transport = mod.WidgetTransport(nio_client)
    callback = object()
    event_filter = object()
    transport.add_callback(callback, event_filter)
    assert nio_client.callbacks == [(callback, event_filter)]


@pytest.mark.asyncio
async def test_send_preserves_exact_target_device_id():
    mod = load_transport()
    nio_client = FakeNioClient(response=object())
    transport = mod.WidgetTransport(nio_client)
    await transport.async_send(
        "io.psix.matrix_extended.widget.v1",
        "@ha:matrix.test",
        "BOTDEVICE",
        {"schema": 1},
    )
    message = nio_client.sent[0]
    assert message.type == "io.psix.matrix_extended.widget.v1"
    assert message.recipient == "@ha:matrix.test"
    assert message.recipient_device == "BOTDEVICE"
    assert message.content == {"schema": 1}


@pytest.mark.asyncio
async def test_send_all_devices_only_when_explicitly_requested():
    mod = load_transport()
    nio_client = FakeNioClient(response=object())
    transport = mod.WidgetTransport(nio_client)
    await transport.async_send("x", "@user:matrix.test", "*", {"op": "state"})
    assert nio_client.sent[0].recipient_device == "*"


@pytest.mark.asyncio
async def test_nio_error_response_becomes_widget_transport_send_error():
    mod = load_transport()
    nio_client = FakeNioClient(response=FakeToDeviceError("denied"))
    transport = mod.WidgetTransport(nio_client)
    with pytest.raises(mod.WidgetTransportSendError, match="denied"):
        await transport.async_send("x", "@u:m", "D", {})


@pytest.mark.asyncio
async def test_transport_exception_becomes_connection_error():
    mod = load_transport()
    nio_client = FakeNioClient(error=RuntimeError("network down"))
    transport = mod.WidgetTransport(nio_client)
    with pytest.raises(mod.WidgetTransportConnectionError, match="network down"):
        await transport.async_send("x", "@u:m", "D", {})
