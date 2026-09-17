"""Basic auth middleware and the direct-route key check."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import main


def _basic(login: str, password: str) -> dict:
    return {'Authorization': 'Basic ' + base64.b64encode(f'{login}:{password}'.encode()).decode()}


def _request(method='GET', path='/', headers=None, query=None):
    req = MagicMock(spec=web.Request)
    req.method = method
    req.path = path
    req.headers = headers or {}
    req.query = query or {}
    req.match_info = {}
    return req


@pytest.fixture
def basic_auth(monkeypatch):
    monkeypatch.setattr(main.config, 'BASIC_AUTH_USERNAME', 'flo')
    monkeypatch.setattr(main.config, 'BASIC_AUTH_PASSWORD', 'secret')
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES_KEY', '')


@pytest.mark.asyncio
async def test_auth_guard_is_a_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(main.config, 'BASIC_AUTH_USERNAME', '')
    handler = AsyncMock(return_value='ok')
    assert await main.auth_guard(_request(), handler) == 'ok'


@pytest.mark.asyncio
async def test_auth_guard_challenges_without_or_with_wrong_credentials(basic_auth):
    handler = AsyncMock()
    with pytest.raises(web.HTTPUnauthorized) as exc:
        await main.auth_guard(_request(), handler)
    assert exc.value.headers['WWW-Authenticate'].startswith('Basic ')
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(headers=_basic('flo', 'nope')), handler)
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(headers={'Authorization': 'Bearer x'}), handler)
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(headers={'Authorization': 'Basic not-base64!'}), handler)
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_guard_passes_correct_credentials_and_preflights(basic_auth, monkeypatch):
    handler = AsyncMock(return_value='ok')
    assert await main.auth_guard(_request(headers=_basic('flo', 'secret')), handler) == 'ok'
    assert await main.auth_guard(_request(method='OPTIONS'), handler) == 'ok'
    # Only the first colon separates login and password.
    monkeypatch.setattr(main.config, 'BASIC_AUTH_PASSWORD', 'se:cr:et')
    assert await main.auth_guard(_request(headers=_basic('flo', 'se:cr:et')), handler) == 'ok'


@pytest.mark.asyncio
async def test_direct_routes_skip_basic_auth_only_when_they_have_their_own_key(basic_auth, monkeypatch):
    handler = AsyncMock(return_value='ok')
    prefix = main.config.URL_PREFIX
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(path=prefix + 'dl/x.mp3'), handler)
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES_KEY', 'k')
    assert await main.auth_guard(_request(path=prefix + 'dl/x.mp3'), handler) == 'ok'
    assert await main.auth_guard(_request(path=prefix + 'watch'), handler) == 'ok'
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(path=prefix + 'history'), handler)


@pytest.mark.asyncio
async def test_direct_serve_requires_the_key_when_configured(monkeypatch):
    monkeypatch.setattr(main.config, 'DIRECT_ROUTES_KEY', 'k')
    calls = []

    async def fake_fetch(source, ext, ts, tmpdir, ytdl_opts, allow_private):
        calls.append(source)
        path = os.path.join(tmpdir, 'media.mp4')
        Path(path).write_bytes(b'\x00')
        return path, 't'

    monkeypatch.setattr(main, '_run_direct_fetch', fake_fetch)
    with pytest.raises(web.HTTPForbidden):
        await main.watch(_request(query={'v': 'dQw4w9WgXcQ'}))
    with pytest.raises(web.HTTPForbidden):
        await main.watch(_request(query={'v': 'dQw4w9WgXcQ', 'key': 'wrong'}))
    assert calls == []

    resp = await main.watch(_request(query={'v': 'dQw4w9WgXcQ', 'key': 'k'}))
    resp._tmpdir.cleanup()
    resp = await main.watch(_request(query={'v': 'dQw4w9WgXcQ'}, headers={'X-Api-Key': 'k'}))
    resp._tmpdir.cleanup()
    assert calls == ['dQw4w9WgXcQ', 'dQw4w9WgXcQ']
