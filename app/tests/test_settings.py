"""Runtime settings (GET/POST /settings) and the DIRECT_ROUTES toggle."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import main


def _json_request(body):
    req = MagicMock(spec=web.Request)
    req.json = AsyncMock(return_value=body)
    return req


@pytest.fixture
def unlocked(monkeypatch):
    store = MagicMock()
    store.load = MagicMock(return_value={'kind': 'settings', 'DIRECT_ROUTES_KEY': 'old'})
    monkeypatch.setattr(main, '_settings_store', store)
    monkeypatch.setattr(main, '_settings_locked', {'DIRECT_ROUTES': False, 'DIRECT_ROUTES_KEY': False})
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES', True)
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES_KEY', '')
    return store


@pytest.mark.asyncio
async def test_settings_get_reports_values_and_locks(unlocked):
    resp = await main.settings_get(MagicMock(spec=web.Request))
    assert json.loads(resp.text) == {
        'direct_routes': True,
        'direct_routes_key': '',
        'locked': {'direct_routes': False, 'direct_routes_key': False},
    }


@pytest.mark.asyncio
async def test_settings_update_applies_persists_and_keeps_other_saved_keys(unlocked):
    resp = await main.settings_update(_json_request({'direct_routes': False}))
    assert main.config.DIRECT_ROUTES is False
    assert json.loads(resp.text)['direct_routes'] is False
    unlocked.save.assert_called_once_with({'DIRECT_ROUTES_KEY': 'old', 'DIRECT_ROUTES': False})

    await main.settings_update(_json_request({'direct_routes_key': '  k1  '}))
    assert main.config.DIRECT_ROUTES_KEY == 'k1'


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [{'direct_routes': 'yes'}, {'direct_routes': 1}, {'direct_routes_key': 5}])
async def test_settings_update_rejects_wrong_types(unlocked, body):
    with pytest.raises(web.HTTPBadRequest):
        await main.settings_update(_json_request(body))
    unlocked.save.assert_not_called()


@pytest.mark.asyncio
async def test_settings_update_refuses_env_locked_fields(unlocked, monkeypatch):
    monkeypatch.setattr(main, '_settings_locked', {'DIRECT_ROUTES': True, 'DIRECT_ROUTES_KEY': False})
    with pytest.raises(web.HTTPBadRequest):
        await main.settings_update(_json_request({'direct_routes': False}))
    assert main.config.DIRECT_ROUTES is True
    unlocked.save.assert_not_called()


def test_saved_settings_apply_only_when_unlocked_and_well_typed(monkeypatch):
    store = MagicMock()
    store.load = MagicMock(return_value={'DIRECT_ROUTES': False, 'DIRECT_ROUTES_KEY': 123})
    monkeypatch.setattr(main, '_settings_store', store)
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES', True)
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES_KEY', 'env')

    monkeypatch.setattr(main, '_settings_locked', {'DIRECT_ROUTES': True, 'DIRECT_ROUTES_KEY': False})
    main._apply_saved_settings()
    assert main.config.DIRECT_ROUTES is True      # locked by env
    assert main.config.DIRECT_ROUTES_KEY == 'env'  # wrong type in file, ignored

    monkeypatch.setattr(main, '_settings_locked', {'DIRECT_ROUTES': False, 'DIRECT_ROUTES_KEY': False})
    main._apply_saved_settings()
    assert main.config.DIRECT_ROUTES is False


@pytest.mark.asyncio
async def test_direct_routes_answer_404_while_disabled(monkeypatch):
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES', False)
    req = MagicMock(spec=web.Request)
    req.query = {'v': 'dQw4w9WgXcQ'}
    req.match_info = {'name': 'x.mp3'}
    with pytest.raises(web.HTTPNotFound):
        await main.watch(req)
    with pytest.raises(web.HTTPNotFound):
        await main.dl(req)
