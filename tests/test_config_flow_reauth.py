import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).parents[1] / 'custom_components' / 'matrix_extended'


def load(monkeypatch):
    vol = types.ModuleType('voluptuous')
    vol.Schema = lambda x: x
    vol.Required = lambda x, **kwargs: x
    monkeypatch.setitem(sys.modules, 'voluptuous', vol)
    nio = types.ModuleType('nio')
    nio.AsyncClient = object
    responses = types.ModuleType('nio.responses')
    responses.RoomResolveAliasResponse = object
    monkeypatch.setitem(sys.modules, 'nio', nio)
    monkeypatch.setitem(sys.modules, 'nio.responses', responses)
    package = types.ModuleType('flow_test_package')
    package.__path__ = [str(ROOT)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    ha = types.ModuleType('homeassistant')
    config_entries = types.ModuleType('homeassistant.config_entries')
    class Flow:
        def __init_subclass__(cls, **kwargs): pass
        def async_show_form(self, **kwargs): return kwargs
        def async_update_reload_and_abort(self, entry, *, data):
            entry.data = data
            return {'type': 'abort', 'reason': 'reauth_successful'}
        def async_update_and_abort(self, entry, *, data):
            entry.data = data
            return {'type': 'abort', 'reason': 'reauth_successful', 'listener': True}
        def _get_reauth_entry(self): return self.entry
    config_entries.ConfigFlow = Flow
    config_entries.OptionsFlow = type('OptionsFlow', (), {})
    config_entries.ConfigEntry = type('ConfigEntry', (), {})
    ha.config_entries = config_entries
    helpers = types.ModuleType('homeassistant.helpers')
    helpers.config_validation = types.SimpleNamespace(ensure_list=lambda x: x)
    helpers.selector = types.SimpleNamespace(TextSelector=lambda x: x, TextSelectorConfig=lambda **kwargs: kwargs, TextSelectorType=types.SimpleNamespace(PASSWORD='password'))
    for name, obj in [('homeassistant', ha), ('homeassistant.config_entries', config_entries), ('homeassistant.helpers', helpers)]: monkeypatch.setitem(sys.modules, name, obj)
    client = types.ModuleType('flow_test_package.client')
    client.MatrixAuthenticationError = type('MatrixAuthenticationError', (Exception,), {})
    client.MatrixConnectionError = type('MatrixConnectionError', (Exception,), {})
    client.async_password_login = AsyncMock()
    monkeypatch.setitem(sys.modules, client.__name__, client)
    const_spec = importlib.util.spec_from_file_location('flow_test_package.const', ROOT / 'const.py')
    const = importlib.util.module_from_spec(const_spec)
    const_spec.loader.exec_module(const)
    const.CONF_REFRESH_TOKEN = 'refresh_token'
    const.CONF_SESSION_ID = 'session_id'
    const.CONF_STORE_GENERATION = 'store_generation'
    monkeypatch.setitem(sys.modules, const.__name__, const)
    spec = importlib.util.spec_from_file_location('flow_test_package.config_flow', ROOT / 'config_flow.py')
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    return mod


def flow_with_entry(mod, soft):
    flow = mod.MatrixExtendedConfigFlow()
    flow.entry = types.SimpleNamespace(data={'homeserver': 'https://example', 'user_id': '@ha:example', 'device_id': 'OLD', 'access_token': 'old', 'refresh_token': 'old-refresh', 'store_key': 'old-key', 'allowed_users': ['@safe:example']}, options={'a': 1}, update_listeners=[])
    flow.context = {'matrix_soft_logout': soft}
    return flow


@pytest.mark.asyncio
async def test_soft_reauth_preserves_device_store_and_options(monkeypatch):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, True)
    mod.async_password_login.return_value = types.SimpleNamespace(user_id='@ha:example', device_id='OLD', access_token='new', refresh_token='new-refresh')
    result = await flow.async_step_reauth_confirm({'password': 'secret'})
    assert result['reason'] == 'reauth_successful'
    assert flow.entry.data['device_id'] == 'OLD'
    assert flow.entry.data['store_key'] == 'old-key'
    assert flow.entry.data['access_token'] == 'new'
    assert flow.entry.data['refresh_token'] == 'new-refresh'
    assert flow.entry.data['allowed_users'] == ['@safe:example']
    assert flow.entry.options == {'a': 1}
    assert 'password' not in flow.entry.data
    assert mod.async_password_login.await_args.kwargs['device_id'] == 'OLD'


@pytest.mark.asyncio
async def test_hard_reauth_rotates_store_and_removes_stale_refresh(monkeypatch):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, False)
    mod.async_password_login.return_value = types.SimpleNamespace(user_id='@ha:example', device_id='NEW', access_token='new', refresh_token=None)
    result = await flow.async_step_reauth_confirm({'password': 'secret'})
    assert result['reason'] == 'reauth_successful'
    assert flow.entry.data['device_id'] == 'NEW'
    assert flow.entry.data['store_key'] != 'old-key'
    assert len(flow.entry.data['store_generation']) == 32
    assert len(flow.entry.data['session_id']) == 32
    assert 'refresh_token' not in flow.entry.data
    assert flow.entry.data['allowed_users'] == ['@safe:example']
    assert mod.async_password_login.await_args.kwargs['device_id'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(('soft', 'user', 'device', 'error'), [
    (True, '@other:example', 'OLD', 'wrong_account'),
    (True, '@ha:example', 'NEW', 'wrong_device'),
    (False, '@ha:example', 'OLD', 'wrong_device'),
])
async def test_reauth_rejects_wrong_account_or_device(monkeypatch, soft, user, device, error):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, soft)
    original = dict(flow.entry.data)
    mod.async_password_login.return_value = types.SimpleNamespace(user_id=user, device_id=device, access_token='new', refresh_token=None)
    result = await flow.async_step_reauth_confirm({'password': 'secret'})
    assert result['errors']['base'] == error
    assert flow.entry.data == original


@pytest.mark.asyncio
async def test_reauth_reports_invalid_password_without_changing_entry(monkeypatch):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, True)
    original = dict(flow.entry.data)
    mod.async_password_login.side_effect = mod.MatrixAuthenticationError()
    result = await flow.async_step_reauth_confirm({'password': 'wrong'})
    assert result['errors']['base'] == 'invalid_auth'
    assert flow.entry.data == original


@pytest.mark.asyncio
async def test_reauth_loaded_entry_uses_update_listener_for_reload(monkeypatch):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, True)
    flow.entry.update_listeners = [object()]
    mod.async_password_login.return_value = types.SimpleNamespace(user_id='@ha:example', device_id='OLD', access_token='new', refresh_token=None)
    result = await flow.async_step_reauth_confirm({'password': 'secret'})
    assert result['listener'] is True
    assert flow.entry.data['access_token'] == 'new'


@pytest.mark.asyncio
async def test_reauth_unloaded_entry_schedules_reload(monkeypatch):
    mod = load(monkeypatch)
    flow = flow_with_entry(mod, True)
    mod.async_password_login.return_value = types.SimpleNamespace(user_id='@ha:example', device_id='OLD', access_token='new', refresh_token=None)
    result = await flow.async_step_reauth_confirm({'password': 'secret'})
    assert result['reason'] == 'reauth_successful'
    assert 'listener' not in result
