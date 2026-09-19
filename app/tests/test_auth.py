"""Users, sessions, the auth guard and the login/users endpoints."""

from __future__ import annotations

import base64
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

import auth
import main


def _basic(login: str, password: str) -> dict:
    return {'Authorization': 'Basic ' + base64.b64encode(f'{login}:{password}'.encode()).decode()}


def _request(method='GET', path='/', headers=None, cookies=None, user=None, body=None):
    req = MagicMock(spec=web.Request)
    req.method = method
    req.path = path
    req.headers = headers or {}
    req.cookies = cookies or {}
    req.query = {}
    req.match_info = {}
    req.get = MagicMock(return_value=user)
    req.json = AsyncMock(return_value=body)
    return req


@pytest.fixture
def store(tmp_path):
    return auth.UserStore(str(tmp_path))


@pytest.fixture
def with_users(tmp_path, monkeypatch):
    s = auth.UserStore(str(tmp_path), 'root', 'rootpw')
    s.add('bob', 'bobpw', 'user')
    monkeypatch.setattr(main, 'users', s)
    return s


def test_password_hash_roundtrip():
    stored = auth.hash_password('s3cret')
    assert stored.startswith('scrypt$')
    assert auth.verify_password('s3cret', stored)
    assert not auth.verify_password('wrong', stored)
    assert not auth.verify_password('s3cret', 'garbage')


def test_parse_basic_auth():
    assert auth.parse_basic_auth(_basic('a', 'b:c')['Authorization']) == ('a', 'b:c')
    assert auth.parse_basic_auth('Bearer x') is None
    assert auth.parse_basic_auth('Basic !!!') is None
    assert auth.parse_basic_auth('') is None


def test_store_starts_open_and_persists_secret_and_users(tmp_path, store):
    assert not store.enabled
    store.add('alice', 'pw', 'admin')
    reloaded = auth.UserStore(str(tmp_path))
    assert reloaded.enabled
    assert reloaded.secret == store.secret
    assert reloaded.authenticate('alice', 'pw') == {'username': 'alice', 'role': 'admin', 'locked': False}
    assert reloaded.authenticate('alice', 'nope') is None
    assert os.path.exists(tmp_path / 'users.json')


def test_env_admin_is_created_kept_in_sync_and_locked(tmp_path):
    s = auth.UserStore(str(tmp_path), 'root', 'pw1')
    assert s.list() == [{'username': 'root', 'role': 'admin', 'locked': True}]
    first_hash = s.users['root']['password_hash']
    # Same password on restart: hash untouched, so sessions survive.
    assert auth.UserStore(str(tmp_path), 'root', 'pw1').users['root']['password_hash'] == first_hash
    # Changed env password wins over the stored one.
    s2 = auth.UserStore(str(tmp_path), 'root', 'pw2')
    assert s2.authenticate('root', 'pw2') and not s2.authenticate('root', 'pw1')
    with pytest.raises(ValueError):
        s2.update('root', password='x')
    with pytest.raises(ValueError):
        s2.delete('root')


def test_store_validation_and_last_admin_protection(store):
    store.add('admin', 'pw', 'admin')
    for bad in [('bad name', 'pw', 'user'), ('admin', 'pw', 'user'), ('x', '', 'user'), ('x', 'pw', 'root')]:
        with pytest.raises(ValueError):
            store.add(*bad)
    with pytest.raises(ValueError):
        store.update('admin', role='user')
    with pytest.raises(ValueError):
        store.delete('admin')
    store.add('second', 'pw', 'admin')
    store.update('admin', role='user')
    store.delete('admin')
    assert [u['username'] for u in store.list()] == ['second']
    with pytest.raises(ValueError):
        store.update('ghost', role='user')


def test_tokens_expire_and_die_with_the_password(store, monkeypatch):
    store.add('alice', 'pw', 'user')
    token = store.issue_token('alice')
    assert store.user_from_token(token)['username'] == 'alice'
    assert store.user_from_token(token + 'x') is None
    assert store.user_from_token('nonsense') is None
    store.update('alice', password='new')
    assert store.user_from_token(token) is None
    token = store.issue_token('alice')
    monkeypatch.setattr(auth.time, 'time', lambda: 2 ** 40)
    assert store.user_from_token(token) is None


@pytest.mark.asyncio
async def test_guard_is_open_without_users(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'users', auth.UserStore(str(tmp_path)))
    handler = AsyncMock(return_value='ok')
    assert await main.auth_guard(_request(path=main.config.URL_PREFIX + 'history'), handler) == 'ok'


@pytest.mark.asyncio
async def test_guard_protects_api_but_not_shell_login_or_direct_routes(with_users):
    prefix = main.config.URL_PREFIX
    handler = AsyncMock(return_value='ok')
    for path in ('history', 'download/x.mp4', 'settings', 'users', 'socket.io/'):
        with pytest.raises(web.HTTPUnauthorized):
            await main.auth_guard(_request(path=prefix + path), handler)
    for path in ('', 'login', 'me', 'index.html', 'watch', 'dl/x.mp3'):
        assert await main.auth_guard(_request(path=prefix + path), handler) == 'ok'
    assert await main.auth_guard(_request(method='OPTIONS', path=prefix + 'add'), handler) == 'ok'
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(path=prefix + '../secret'), handler)


@pytest.mark.asyncio
async def test_guard_accepts_session_cookie_and_basic_header(with_users):
    prefix = main.config.URL_PREFIX
    handler = AsyncMock(return_value='ok')
    cookie = {auth.SESSION_COOKIE: with_users.issue_token('bob')}
    req = _request(path=prefix + 'history', cookies=cookie)
    assert await main.auth_guard(req, handler) == 'ok'
    req.__setitem__.assert_called_with('user', {'username': 'bob', 'role': 'user', 'locked': False})
    assert await main.auth_guard(_request(path=prefix + 'history', headers=_basic('root', 'rootpw')), handler) == 'ok'
    with pytest.raises(web.HTTPUnauthorized):
        await main.auth_guard(_request(path=prefix + 'history', headers=_basic('root', 'wrong')), handler)


@pytest.mark.asyncio
async def test_login_sets_cookie_and_rejects_bad_credentials(with_users, monkeypatch):
    monkeypatch.setattr(main.asyncio, 'sleep', AsyncMock())
    resp = await main.login(_request(body={'username': 'bob', 'password': 'bobpw'}))
    assert json.loads(resp.text)['user']['username'] == 'bob'
    assert auth.SESSION_COOKIE in resp.cookies
    assert with_users.user_from_token(resp.cookies[auth.SESSION_COOKIE].value)['username'] == 'bob'
    with pytest.raises(web.HTTPUnauthorized):
        await main.login(_request(body={'username': 'bob', 'password': 'nope'}))
    main.asyncio.sleep.assert_awaited()


@pytest.mark.asyncio
async def test_me_reports_auth_state(with_users):
    resp = await main.me(_request())
    assert json.loads(resp.text) == {'auth': True, 'user': None}
    resp = await main.me(_request(cookies={auth.SESSION_COOKIE: with_users.issue_token('root')}))
    assert json.loads(resp.text)['user']['role'] == 'admin'


@pytest.mark.asyncio
async def test_users_endpoints_are_admin_only(with_users):
    bob = with_users.public('bob')
    root = with_users.public('root')
    with pytest.raises(web.HTTPForbidden):
        await main.users_list(_request(user=bob))
    with pytest.raises(web.HTTPForbidden):
        await main.settings_get(_request(user=bob))
    resp = await main.users_add(_request(user=root, body={'username': 'carol', 'password': 'pw', 'role': 'admin'}))
    assert [u['username'] for u in json.loads(resp.text)['users']] == ['bob', 'carol', 'root']
    with pytest.raises(web.HTTPBadRequest):
        await main.users_add(_request(user=root, body={'username': 'carol', 'password': 'pw'}))
    await main.users_update(_request(user=root, body={'username': 'bob', 'role': 'admin', 'password': 'pw2'}))
    assert with_users.authenticate('bob', 'pw2')['role'] == 'admin'
    with pytest.raises(web.HTTPBadRequest):
        await main.users_delete(_request(user=root, body={'username': 'root'}))
    resp = await main.users_delete(_request(user=root, body={'username': 'carol'}))
    assert [u['username'] for u in json.loads(resp.text)['users']] == ['bob', 'root']
