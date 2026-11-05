from types import SimpleNamespace
import asyncio
import pytest
from test_client_e2ee import client_module, AsyncClient, LoginResponse, WhoamiResponse, ErrorResponse

class Transport:
    def __init__(self, status, body):
        self.status, self.body = status, body
    async def json(self):
        return self.body

@pytest.mark.asyncio
async def test_login_requests_refresh_and_preserves_device(client_module, monkeypatch):
    seen = {}
    async def login_raw(self, body):
        seen.update(body)
        response = LoginResponse()
        response.user_id, response.device_id, response.access_token = '@a:x', 'DEV', 'access'
        response.transport_response = Transport(200, {'refresh_token': 'refresh'})
        return response
    monkeypatch.setattr(AsyncClient, 'login_raw', login_raw, raising=False)
    result = await client_module.async_password_login('https://x', '@a:x', 'pass', True, device_id='DEV')
    assert seen['refresh_token'] is True and seen['device_id'] == 'DEV'
    assert result.refresh_token == 'refresh'

@pytest.mark.asyncio
async def test_expired_access_refreshes_and_persists_before_retry(client_module, monkeypatch):
    saved = []
    async def persist(access, refresh):
        saved.append((access, refresh))
    client = client_module.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='r1', on_credentials_updated=persist)
    nio = AsyncClient.last_instance
    async def whoami():
        if nio.access_token == 'old':
            err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'; err.soft_logout = True
            return err
        assert saved == [('new', 'r2')]
        return WhoamiResponse()
    async def send(method, path, data, headers=None):
        return Transport(200, {'access_token': 'new', 'refresh_token': 'r2'})
    nio.whoami = whoami
    nio.send = send
    await client.async_connect()
    assert nio.access_token == 'new'

@pytest.mark.asyncio
async def test_no_refresh_token_reports_soft_logout(client_module):
    errors = []
    async def failed(error): errors.append(error)
    client = client_module.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', on_auth_failed=failed)
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'; err.soft_logout = True
    AsyncClient.last_instance.whoami_response = err
    with pytest.raises(client_module.MatrixAuthenticationError) as caught:
        await client.async_connect()
    assert caught.value.soft_logout is True
    assert errors == [caught.value]

@pytest.mark.asyncio
async def test_refresh_temporary_failure_does_not_trigger_reauthentication(client_module):
    failures = []
    async def failed(error): failures.append(error)
    client = client_module.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='r1', on_auth_failed=failed)
    nio = AsyncClient.last_instance
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'
    nio.whoami_response = err
    async def send(*args): return Transport(503, {'error': 'unavailable'})
    nio.send = send
    with pytest.raises(client_module.MatrixConnectionError):
        await client.async_connect()
    assert not failures

@pytest.mark.asyncio
async def test_parallel_expiry_refreshes_once(client_module):
    calls, saves = [], []
    async def persist(access, refresh): saves.append((access, refresh))
    client = client_module.MatrixClient(homeserver='https://x', user_id='@a:x', access_token='old', device_id='DEV', verify_ssl=True, store_path='store', store_key='key', refresh_token='r1', on_credentials_updated=persist)
    nio = AsyncClient.last_instance
    nio.access_token = 'old'
    async def send(*args):
        calls.append(1)
        await asyncio.sleep(0)
        return Transport(200, {'access_token': 'new', 'refresh_token': 'r2'})
    nio.send = send
    err = ErrorResponse(); err.status_code = 'M_UNKNOWN_TOKEN'
    await asyncio.gather(client._async_recover_auth(err, 'old'), client._async_recover_auth(err, 'old'))
    assert len(calls) == 1
    assert saves == [('new', 'r2')]
    assert nio.access_token == 'new'
