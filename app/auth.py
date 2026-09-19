"""Users, password hashing and stateless session tokens.

An instance without users is open, as MeTube always was. The first user
normally comes from ADMIN_USERNAME / ADMIN_PASSWORD; an admin manages further
users from the UI. Everything lives in ``STATE_DIR/users.json`` together with
the secret that signs session tokens.
"""

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import time

from state_store import AtomicJsonStore

SESSION_COOKIE = 'metube_session'
SESSION_TTL = 30 * 24 * 3600
ROLES = ('admin', 'user')
USERNAME_RE = re.compile(r'^[A-Za-z0-9._@-]{1,64}$')
_SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1, 'dklen': 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f'scrypt${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split('$')
        if algo != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def parse_basic_auth(header: str):
    """``(username, password)`` from an ``Authorization: Basic`` header, else ``None``."""
    scheme, _, token = (header or '').partition(' ')
    if scheme.lower() != 'basic':
        return None
    try:
        name, _, password = base64.b64decode(token.strip(), validate=True).decode('utf-8').partition(':')
    except (binascii.Error, UnicodeDecodeError):
        return None
    return name, password


class UserStore:
    def __init__(self, state_dir: str, env_username: str = '', env_password: str = ''):
        self._store = AtomicJsonStore(os.path.join(state_dir, 'users.json'), kind='users')
        data = self._store.load() or {}
        self.users: dict[str, dict] = {
            name: user for name, user in (data.get('users') or {}).items()
            if isinstance(user, dict) and isinstance(user.get('password_hash'), str) and user.get('role') in ROLES
        }
        saved_secret = data.get('secret')
        self.secret = saved_secret if isinstance(saved_secret, str) and saved_secret else secrets.token_hex(32)
        self.env_username = env_username
        changed = self.secret != saved_secret
        if env_username:
            # The environment admin is authoritative: (re)create it whenever the
            # stored record does not match, and never let the UI edit it.
            current = self.users.get(env_username)
            if not current or current['role'] != 'admin' or not verify_password(env_password, current['password_hash']):
                self.users[env_username] = {'password_hash': hash_password(env_password), 'role': 'admin'}
                changed = True
        if changed:
            self.save()

    @property
    def enabled(self) -> bool:
        return bool(self.users)

    def save(self) -> None:
        self._store.save({'secret': self.secret, 'users': self.users})

    def public(self, name: str) -> dict:
        return {'username': name, 'role': self.users[name]['role'], 'locked': name == self.env_username}

    def list(self) -> list[dict]:
        return [self.public(name) for name in sorted(self.users)]

    def authenticate(self, name: str, password: str):
        user = self.users.get(name)
        if user and verify_password(password, user['password_hash']):
            return self.public(name)
        return None

    def add(self, name: str, password: str, role: str) -> dict:
        if not USERNAME_RE.fullmatch(name or ''):
            raise ValueError('username must be 1-64 characters: letters, digits, . _ @ -')
        if name in self.users:
            raise ValueError('user already exists')
        self._check_role(role)
        self._check_password(password)
        self.users[name] = {'password_hash': hash_password(password), 'role': role}
        self.save()
        return self.public(name)

    def update(self, name: str, password=None, role=None) -> dict:
        self._check_editable(name)
        if role is not None:
            self._check_role(role)
            if role != 'admin' and self._is_last_admin(name):
                raise ValueError('cannot demote the last admin')
        if password is not None:
            self._check_password(password)
        if role is not None:
            self.users[name]['role'] = role
        if password is not None:
            self.users[name]['password_hash'] = hash_password(password)
        self.save()
        return self.public(name)

    def delete(self, name: str) -> None:
        self._check_editable(name)
        if self._is_last_admin(name):
            raise ValueError('cannot delete the last admin')
        del self.users[name]
        self.save()

    def _check_editable(self, name: str) -> None:
        if name not in self.users:
            raise ValueError('unknown user')
        if name == self.env_username:
            raise ValueError('this user comes from ADMIN_USERNAME / ADMIN_PASSWORD and cannot be changed here')

    @staticmethod
    def _check_role(role) -> None:
        if role not in ROLES:
            raise ValueError(f'role must be one of {list(ROLES)}')

    @staticmethod
    def _check_password(password) -> None:
        if not isinstance(password, str) or not password:
            raise ValueError('password must not be empty')

    def _is_last_admin(self, name: str) -> bool:
        admins = [n for n, u in self.users.items() if u['role'] == 'admin']
        return admins == [name]

    # Sessions are stateless signed tokens. The signature covers a fragment of
    # the password hash, so a password change or a deleted user invalidates
    # every session of that user without any server-side session list.
    def _sign(self, name: str, exp: int) -> str:
        msg = f'{name}|{exp}|{self.users[name]["password_hash"][-16:]}'.encode()
        return hmac.new(self.secret.encode(), msg, hashlib.sha256).hexdigest()

    def issue_token(self, name: str) -> str:
        exp = int(time.time()) + SESSION_TTL
        payload = base64.urlsafe_b64encode(f'{name}|{exp}'.encode()).decode().rstrip('=')
        return f'{payload}.{self._sign(name, exp)}'

    def user_from_token(self, token: str):
        try:
            payload, sig = token.split('.')
            name, exp = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode().split('|')
            exp = int(exp)
        except (ValueError, UnicodeDecodeError):
            return None
        if name not in self.users or exp < time.time() or not hmac.compare_digest(sig, self._sign(name, exp)):
            return None
        return self.public(name)
