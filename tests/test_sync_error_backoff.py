from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys

import pytest
import pytest_asyncio

ROOT = Path(__file__).parents[1]
CLIENT_PATH = ROOT / "custom_components" / "matrix_extended" / "client.py"


_STUBBED_PACKAGES = ("nio", "aiohttp")


def _stubbable_modules() -> list[str]:
    return [
        name
        for name in sys.modules
        if name.split(".")[0] in _STUBBED_PACKAGES
    ]


@pytest.fixture(scope="module")
def nio_responses():
    """Real matrix-nio; other test modules leave stub ``nio``/``aiohttp`` behind."""
    with pytest.MonkeyPatch.context() as patch:
        for name in _stubbable_modules():
            patch.delitem(sys.modules, name)
        responses = importlib.import_module("nio.responses")
        yield responses
        for name in _stubbable_modules():
            sys.modules.pop(name, None)


@pytest.fixture
def mod(monkeypatch, nio_responses):
    spec = importlib.util.spec_from_file_location(
        "matrix_extended_client_sync_backoff", CLIENT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_delay_doubles_from_one_second_and_is_capped(mod) -> None:
    delays = [mod.sync_backoff_delay(n) for n in range(1, 12)]
    assert delays[:7] == [1, 2, 4, 8, 16, 32, 60]
    assert set(delays[6:]) == {60}
    assert mod.sync_backoff_delay(10_000) == 60
    assert mod.sync_backoff_delay(0) == 1


def test_delay_never_exceeds_cap_even_with_jitter(mod) -> None:
    assert mod.sync_backoff_delay(50, jitter=1.2) == 60


@pytest.mark.asyncio
async def test_repeated_sync_errors_back_off_with_bounded_jitter(mod, nio_responses) -> None:
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    backoff = mod.SyncErrorBackoff(sleep=fake_sleep)
    for _ in range(12):
        await backoff.on_sync_error(
            nio_responses.SyncError("'next_batch' is a required property")
        )

    assert len(slept) == 12
    for attempt, delay in enumerate(slept, start=1):
        base = min(60, 2 ** (attempt - 1))
        assert 0.8 * base <= delay <= min(60, 1.2 * base)
    assert slept[-1] > slept[0]
    assert max(slept) <= 60
    assert backoff.failures == 12


@pytest.mark.asyncio
async def test_jitter_factor_comes_from_injected_source(mod, nio_responses) -> None:
    seen: list[tuple[float, float]] = []
    slept: list[float] = []

    def uniform(low: float, high: float) -> float:
        seen.append((low, high))
        return 1.0

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    backoff = mod.SyncErrorBackoff(sleep=fake_sleep, uniform=uniform)
    for _ in range(3):
        await backoff.on_sync_error(nio_responses.SyncError("boom"))
    assert slept == [1, 2, 4]
    assert seen == [(0.8, 1.2)] * 3


@pytest.mark.asyncio
async def test_successful_sync_resets_the_backoff(mod, nio_responses) -> None:
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    backoff = mod.SyncErrorBackoff(sleep=fake_sleep, uniform=lambda low, high: 1.0)
    for _ in range(4):
        await backoff.on_sync_error(nio_responses.SyncError("boom"))
    await backoff.on_sync_ok(object())
    assert backoff.failures == 0
    await backoff.on_sync_error(nio_responses.SyncError("boom"))
    assert slept == [1, 2, 4, 8, 1]


@pytest.mark.asyncio
async def test_success_without_prior_failures_is_a_noop(mod) -> None:
    backoff = mod.SyncErrorBackoff()
    await backoff.on_sync_ok(object())
    assert backoff.failures == 0


@pytest_asyncio.fixture
async def homeserver(nio_responses):
    """Fake homeserver behind a proxy: /sync answers 502 with an empty body."""
    from aiohttp import web

    state = {"sync_calls": 0, "errors": 0, "healthy_after": None}

    async def sync(request: web.Request) -> web.Response:
        state["sync_calls"] += 1
        healthy_after = state["healthy_after"]
        if healthy_after is not None and state["sync_calls"] > healthy_after:
            await asyncio.sleep(0.05)  # stand-in for the long poll
            return web.json_response({"next_batch": f"s{state['sync_calls']}"})
        state["errors"] += 1
        return web.Response(status=502, body=b"")

    async def keys_upload(request: web.Request) -> web.Response:
        return web.json_response({"one_time_key_counts": {"signed_curve25519": 50}})

    app = web.Application()
    app.router.add_get("/_matrix/client/v3/sync", sync)
    app.router.add_post("/_matrix/client/v3/keys/upload", keys_upload)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    state["url"] = f"http://127.0.0.1:{port}"
    try:
        yield state
    finally:
        await runner.cleanup()


def _make_client(mod, url: str, tmp_path: Path):
    client = mod.MatrixClient(
        homeserver=url,
        user_id="@ha:example",
        access_token="token",
        device_id="DEVICE",
        verify_ssl=False,
        store_path=str(tmp_path),
        store_key="secret-key",
    )
    client._client.restore_login(
        user_id="@ha:example", device_id="DEVICE", access_token="token"
    )
    return client


@pytest.mark.asyncio
async def test_proxy_502_with_empty_body_backs_off_instead_of_spinning(
    mod, homeserver, tmp_path
) -> None:
    """nio returns SyncError (does not raise) for a 5xx with no JSON body."""
    client = _make_client(mod, homeserver["url"], tmp_path)
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)
        if len(slept) == 5:
            homeserver["healthy_after"] = homeserver["sync_calls"]
        await real_sleep(0.01)

    client._sync_backoff._sleep = fake_sleep
    await client.async_start_listener()
    try:
        for _ in range(500):
            if client._sync_backoff.failures == 0 and len(slept) >= 5:
                break
            await real_sleep(0.01)
    finally:
        await client.async_close()

    assert len(slept) == 5
    for attempt, delay in enumerate(slept, start=1):
        base = 2 ** (attempt - 1)
        assert 0.8 * base <= delay <= 1.2 * base
    # Exactly one request per backoff pause: the loop did not spin on the 502s.
    assert homeserver["errors"] == len(slept)
    assert client._sync_backoff.failures == 0


@pytest.mark.asyncio
async def test_client_registers_sync_response_callbacks(
    mod, nio_responses, homeserver, tmp_path
) -> None:
    client = _make_client(mod, homeserver["url"], tmp_path)
    try:
        registered = {
            (cb.func.__func__.__name__, cb.filter)
            for cb in client._client.response_callbacks
            if getattr(cb.func, "__self__", None) is client._sync_backoff
        }
        assert registered == {
            ("on_sync_error", nio_responses.SyncError),
            ("on_sync_ok", nio_responses.SyncResponse),
        }
    finally:
        await client.async_close()
