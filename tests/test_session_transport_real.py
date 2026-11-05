from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys

from aiohttp import web
import nio as real_nio
import nio.responses as real_nio_responses
import pytest
from test_client_e2ee import client_module

@pytest.fixture
def real_client_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "nio", real_nio)
    monkeypatch.setitem(sys.modules, "nio.responses", real_nio_responses)
    name = 'matrix_real_transport_test'
    path = Path(__file__).parents[1] / 'custom_components/matrix_extended/client.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    actual_config = module.AsyncClientConfig
    module.AsyncClientConfig = lambda **kwargs: actual_config(**{**kwargs, "encryption_enabled": False})
    return module

@pytest.mark.asyncio
@pytest.mark.parametrize('transient_first', [False, True])
async def test_real_nio_soft_logout_recovers_after_transient_refresh(real_client_module, tmp_path, transient_first):
    mod = real_client_module
    refreshes = []
    saved = []
    async def whoami(request):
        if request.headers.get('Authorization') == 'Bearer new-access':
            return web.json_response({'user_id': '@a:x'})
        return web.json_response({'errcode': 'M_UNKNOWN_TOKEN', 'error': 'expired', 'soft_logout': True}, status=401)
    async def refresh(request):
        refreshes.append(await request.json())
        if transient_first and len(refreshes) == 1:
            return web.Response(status=503, text='server unavailable', content_type='text/html')
        return web.json_response({'access_token': 'new-access', 'refresh_token': 'new-refresh'})
    app = web.Application()
    app.router.add_get('/_matrix/client/v3/account/whoami', whoami)
    app.router.add_post('/_matrix/client/v3/refresh', refresh)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async def persist(access, token): saved.append((access, token))
    client = mod.MatrixClient(homeserver=f'http://127.0.0.1:{port}', user_id='@a:x', access_token='old-access', device_id='DEV', verify_ssl=True, store_path=str(tmp_path), store_key='key', refresh_token='old-refresh', on_credentials_updated=persist)
    client._client.access_token = 'old-access'
    try:
        if transient_first:
            with pytest.raises(mod.MatrixConnectionError):
                await client._client.whoami()
        response = await client._client.whoami()
        assert isinstance(response, mod.WhoamiResponse)
        assert client._client.access_token == 'new-access'
        assert saved == [('new-access', 'new-refresh')]
        assert len(refreshes) == (2 if transient_first else 1)
    finally:
        await client.async_close()
        await runner.cleanup()

@pytest.mark.asyncio
async def test_stale_soft_logout_does_not_erase_new_token(client_module):
    mod = client_module
    from test_client_e2ee import AsyncClient, ErrorResponse
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='r')
    nio = AsyncClient.last_instance
    client._login_access_token = 'new'
    nio.access_token = ''  # nio cleared it for a response to the old request
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'; err.soft_logout = True
    await client._async_recover_auth(err, 'old')
    assert nio.access_token == 'new'

@pytest.mark.asyncio
async def test_login_does_not_forward_password_on_redirect(real_client_module):
    mod = real_client_module
    leaked = []
    async def login(request):
        raise web.HTTPTemporaryRedirect('/capture')
    async def capture(request):
        leaked.append(await request.read())
        return web.json_response({'user_id': '@a:x', 'device_id': 'DEV', 'access_token': 'a'})
    app = web.Application(); app.router.add_post('/_matrix/client/v3/login', login); app.router.add_post('/capture', capture)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        with pytest.raises(mod.MatrixConnectionError):
            await mod.async_password_login(f'http://127.0.0.1:{port}', '@a:x', 'secret-password', True)
        assert leaked == []
    finally:
        await runner.cleanup()

@pytest.mark.asyncio
async def test_refresh_rejection_is_cached_and_uses_its_soft_logout(client_module):
    mod = client_module
    errors = []
    async def failed(error): errors.append(error)
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='secret-refresh', on_auth_failed=failed)
    from test_client_e2ee import AsyncClient, ErrorResponse
    nio = AsyncClient.last_instance; nio.access_token = 'old'
    calls = []
    async def send(*args):
        calls.append(1)
        from test_session_transport import Transport
        return Transport(401, {'errcode': 'M_UNKNOWN_TOKEN', 'soft_logout': False})
    nio.send = send
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'; err.soft_logout = True
    for _ in range(2):
        with pytest.raises(mod.MatrixAuthenticationError) as caught:
            await client._async_recover_auth(err, 'old')
        assert caught.value.soft_logout is False
    assert len(calls) == len(errors) == 1

@pytest.mark.asyncio
async def test_html_refresh_401_is_not_definitive(client_module):
    mod = client_module
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='r')
    from test_client_e2ee import AsyncClient, ErrorResponse
    nio = AsyncClient.last_instance; nio.access_token = ''
    class Html:
        status = 401
        async def json(self): raise ValueError('secret-refresh')
    async def send(*args): return Html()
    nio.send = send
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'
    with pytest.raises(mod.MatrixConnectionError) as caught:
        await client._async_recover_auth(err, 'old')
    assert 'secret-refresh' not in str(caught.value)
    assert nio.access_token == 'old'

def test_login_details_repr_redacts_tokens(real_client_module):
    detail = real_client_module.LoginDetails('@a:x', 'access-secret', 'DEV', 'refresh-secret')
    assert 'access-secret' not in repr(detail) and 'refresh-secret' not in repr(detail)

@pytest.mark.asyncio
async def test_nested_key_share_failure_aborts_final_send_and_invalidates(client_module, monkeypatch):
    mod = client_module
    from test_client_e2ee import AsyncClient
    calls, invalidated = [], []
    async def low_send(self, kind):
        calls.append(kind)
        if kind == 'share': raise OSError('network down')
        return object()
    async def room_send(self, **kwargs):
        await asyncio.gather(self._send('share'), return_exceptions=True)
        return await self._send('event')
    monkeypatch.setattr(AsyncClient, '_send', low_send, raising=False)
    monkeypatch.setattr(AsyncClient, 'room_send', room_send)
    monkeypatch.setattr(AsyncClient, 'invalidate_outbound_session', lambda self, room: invalidated.append(room), raising=False)
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key')
    with pytest.raises(mod.MatrixConnectionError):
        await client.async_send_event_prepared([mod.PreparedRoom('!r:x', True)], 'm.room.message', {})
    assert calls == ['share']
    assert invalidated == ['!r:x']

@pytest.mark.asyncio
async def test_real_upload_replays_full_body_after_refresh(real_client_module, tmp_path):
    mod = real_client_module
    bodies = []
    async def upload(request):
        bodies.append(await request.read())
        if request.headers.get('Authorization') == 'Bearer old':
            return web.json_response({'errcode': 'M_UNKNOWN_TOKEN', 'error': 'expired', 'soft_logout': True}, status=401)
        return web.json_response({'content_uri': 'mxc://x/file'})
    async def refresh(request):
        return web.json_response({'access_token': 'new', 'refresh_token': 'r2'})
    app = web.Application(); app.router.add_post('/_matrix/media/v3/upload', upload); app.router.add_post('/_matrix/client/v3/refresh', refresh)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = mod.MatrixClient(homeserver=f'http://127.0.0.1:{port}', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path=str(tmp_path), store_key='key', refresh_token='r1')
    client._client.access_token = 'old'
    try:
        result = await client.async_upload(b'full test payload', filename='a.txt', content_type='text/plain')
        assert result.mxc_uri == 'mxc://x/file'
        assert bodies == [b'full test payload', b'full test payload']
    finally:
        await client.async_close(); await runner.cleanup()


@pytest.mark.asyncio
async def test_refresh_does_not_forward_token_on_redirect(real_client_module, tmp_path):
    mod = real_client_module
    leaked = []
    async def whoami(request):
        return web.json_response({'errcode': 'M_UNKNOWN_TOKEN', 'error': 'expired', 'soft_logout': True}, status=401)
    async def refresh(request): raise web.HTTPTemporaryRedirect('/capture')
    async def capture(request):
        leaked.append(await request.read())
        return web.json_response({'access_token': 'new'})
    app = web.Application(); app.router.add_get('/_matrix/client/v3/account/whoami', whoami); app.router.add_post('/_matrix/client/v3/refresh', refresh); app.router.add_post('/capture', capture)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = mod.MatrixClient(homeserver=f'http://127.0.0.1:{port}', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path=str(tmp_path), store_key='key', refresh_token='secret-refresh')
    client._client.access_token = 'old'
    try:
        with pytest.raises(mod.MatrixConnectionError): await client._client.whoami()
        assert leaked == []
    finally:
        await client.async_close(); await runner.cleanup()

@pytest.mark.asyncio
async def test_failed_key_claim_clears_own_sharing_event_for_retry(client_module, monkeypatch):
    mod = client_module
    from test_client_e2ee import AsyncClient
    attempts = []
    async def share(self, room_id, **kwargs):
        if room_id in self.sharing_session:
            await self.sharing_session[room_id].wait()
        event = asyncio.Event()
        self.sharing_session[room_id] = event
        attempts.append(1)
        if len(attempts) == 1:
            raise mod.MatrixConnectionError('key claim failed')
        self.sharing_session.pop(room_id)
        event.set()
    monkeypatch.setattr(AsyncClient, 'share_group_session', share, raising=False)
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key')
    client._client.sharing_session = {}
    with pytest.raises(mod.MatrixConnectionError):
        await client._client.share_group_session('!room:x')
    await asyncio.wait_for(client._client.share_group_session('!room:x'), timeout=0.2)
    assert len(attempts) == 2

@pytest.mark.asyncio
async def test_failed_concurrent_share_preserves_existing_event(client_module, monkeypatch):
    mod = client_module
    from test_client_e2ee import AsyncClient
    async def share(self, room_id, **kwargs):
        raise RuntimeError('already sharing')
    monkeypatch.setattr(AsyncClient, 'share_group_session', share, raising=False)
    client = mod.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key')
    existing = asyncio.Event()
    client._client.sharing_session = {'!room:x': existing}
    with pytest.raises(RuntimeError): await client._client.share_group_session('!room:x')
    assert client._client.sharing_session['!room:x'] is existing
    assert not existing.is_set()
