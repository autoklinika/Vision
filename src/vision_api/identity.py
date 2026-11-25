"""Local reader accounts and short-lived, in-memory browser sessions.

Provisioning is an explicit local operation. The HTTP owner receives an existing
private accounts path and a trusted client key; forwarded request headers do not
establish identity. Reader is the default; operator only grants inspection lifecycle permission, not system, administrator, or motion authority.
It never logs passwords, cookies, session tokens, or account-file contents.
"""
import argparse
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import threading
import time

from .access import AccessDenied

ACCOUNT_SCHEMA = 'vision.identity.accounts.v1'
IDENTITY_SCHEMA = 'vision.api.identity.v1'
COOKIE_NAME = 'vision_session'
MAX_ACCOUNTS = 32
MAX_ACCOUNT_BYTES = 64 * 1024
MAX_PASSWORD_BYTES = 1024
MIN_PASSWORD_CHARACTERS = 12
MAX_SESSIONS = 64
ABSOLUTE_SECONDS = 8 * 60 * 60
IDLE_SECONDS = 30 * 60
LOGIN_WINDOW_SECONDS = 60
MAX_GLOBAL_ATTEMPTS = 20
MAX_CLIENT_ATTEMPTS = 5
MAX_PASSWORD_CHANGE_ATTEMPTS = 5
PASSWORD_CHANGE_LOCK_SECONDS = 1
MAX_COOKIE_BYTES = 4096
_KDF = 'scrypt-n32768-r8-p1'
_SCRYPT_LOCK = threading.Lock()
_USERNAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z', re.ASCII)
_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z', re.ASCII)
_HEX = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_COOKIE_KEY = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,64}\Z", re.ASCII)
_REPO = Path(__file__).resolve().parents[2]


class InvalidIdentityStore(ValueError):
    """A fixed diagnostic that must not reveal a private path or file content."""
    def __init__(self):
        super().__init__('identity store unavailable')


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = max(1, min(LOGIN_WINDOW_SECONDS, int(math.ceil(retry_after))))
        super().__init__('authentication rate limited')


class CurrentPasswordInvalid(Exception):
    """The authenticated account's current password did not match."""


class PasswordRejected(ValueError):
    """A fixed policy error; neither password is included in diagnostics."""
    def __init__(self):
        super().__init__('new password rejected')


@dataclass(frozen=True)
class _Account:
    username: str
    salt: bytes
    password_hash: bytes
    role: str = "reader"

    @property
    def fingerprint(self):
        return hashlib.sha256(b'vision-account-credential-v1\0' + self.role.encode('ascii') + b'\0' + self.salt + self.password_hash).digest()


@dataclass(frozen=True)
class _Session:
    username: str
    fingerprint: bytes
    created_at: float
    last_seen: float
    role: str = "reader"


def _username(value):
    return isinstance(value, str) and _USERNAME.fullmatch(value) is not None


def _password(value):
    if (not isinstance(value, str)
            or not MIN_PASSWORD_CHARACTERS <= len(value) <= MAX_PASSWORD_BYTES):
        raise ValueError('invalid password length')
    try:
        encoded = value.encode('utf-8')
    except UnicodeError:
        raise ValueError('invalid password') from None
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError('invalid password length')
    return encoded


def _derive(password, salt):
    # Bound memory independently of a caller's thread pool and never accept
    # attacker-selected KDF parameters from the accounts document.
    try:
        with _SCRYPT_LOCK:
            return hashlib.scrypt(password, salt=salt, n=2 ** 15, r=8, p=1,
                                  maxmem=64 * 1024 * 1024, dklen=32)
    except (ValueError, MemoryError):
        raise InvalidIdentityStore() from None


def _safe_path(value, forbidden_roots=()):
    try:
        path = Path(os.path.abspath(os.fspath(value)))
        roots = [_REPO]
        for root in forbidden_roots:
            configured = Path(os.path.abspath(os.fspath(root)))
            roots.extend((configured, configured.resolve()))
        if path.name in ('', '.', '..') or any(path == root or root in path.parents for root in roots):
            raise InvalidIdentityStore()
        # Reject symlink components before descriptor-relative traversal as
        # well as using O_NOFOLLOW for every opened component below.
        for component in (path, *path.parents):
            if component.is_symlink():
                raise InvalidIdentityStore()
        return path
    except (OSError, TypeError, ValueError, RuntimeError):
        raise InvalidIdentityStore() from None


def _open_parent(path):
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for component in path.parent.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _private_regular(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid() or info.st_nlink != 1):
        raise InvalidIdentityStore()
    return info


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidIdentityStore()
        result[key] = value
    return result


def _decode_accounts(raw):
    try:
        document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(InvalidIdentityStore()))
        if (type(document) is not dict or set(document) != {'schema', 'accounts'}
                or document['schema'] != ACCOUNT_SCHEMA
                or type(document['accounts']) is not list or len(document['accounts']) > MAX_ACCOUNTS):
            raise InvalidIdentityStore()
        accounts = {}
        for row in document['accounts']:
            if (type(row) is not dict or set(row) != {'username', 'role', 'kdf', 'salt', 'hash'}
                    or not _username(row['username']) or row['username'] in accounts
                    or row['role'] not in ('reader', 'operator') or row['kdf'] != _KDF
                    or not isinstance(row['salt'], str) or not _HEX.fullmatch(row['salt'])
                    or not isinstance(row['hash'], str) or not _HEX.fullmatch(row['hash'])):
                raise InvalidIdentityStore()
            accounts[row['username']] = _Account(row['username'], bytes.fromhex(row['salt']), bytes.fromhex(row['hash']), row['role'])
        return accounts
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise InvalidIdentityStore() from None


def _read_accounts(path, *, allow_missing=False):
    parent_fd = fd = None
    try:
        parent_fd = _open_parent(path)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=parent_fd)
        except FileNotFoundError:
            if allow_missing:
                return {}
            raise
        info = _private_regular(fd)
        if not 1 <= info.st_size <= MAX_ACCOUNT_BYTES:
            raise InvalidIdentityStore()
        with os.fdopen(fd, 'rb', closefd=False) as source:
            raw = source.read(MAX_ACCOUNT_BYTES + 1)
        if len(raw) > MAX_ACCOUNT_BYTES:
            raise InvalidIdentityStore()
        return _decode_accounts(raw)
    except (OSError, ValueError, TypeError):
        raise InvalidIdentityStore() from None
    finally:
        if fd is not None:
            os.close(fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _encoded_accounts(accounts):
    document = {'schema': ACCOUNT_SCHEMA, 'accounts': [
        {'username': account.username, 'role': account.role, 'kdf': _KDF,
         'salt': account.salt.hex(), 'hash': account.password_hash.hex()}
        for _, account in sorted(accounts.items())]}
    data = (json.dumps(document, ensure_ascii=True, separators=(',', ':')) + '\n').encode('ascii')
    if len(data) > MAX_ACCOUNT_BYTES:
        raise InvalidIdentityStore()
    return data


def _write_all(fd, data):
    pending = memoryview(data)
    while pending:
        written = os.write(fd, pending)
        if not written:
            raise OSError('private write unavailable')
        pending = pending[written:]
    os.fsync(fd)


def _publish_accounts(parent_fd, filename, data, *, existing):
    temporary = '.identity-' + secrets.token_hex(16)
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
        _write_all(fd, data)
        os.close(fd)
        fd = None
        if existing:
            os.replace(temporary, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        else:
            os.link(temporary, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                    follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


@contextmanager
def _account_transaction(path, *, timeout=5):
    """Serialize credential publication with local provisioning processes."""
    parent_fd = lock_fd = None
    locked = False
    try:
        parent_fd = _open_parent(path)
        lock_fd = os.open(path.name + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                          0o600, dir_fd=parent_fd)
        _private_regular(lock_fd)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise InvalidIdentityStore()
                time.sleep(0.01)
        yield parent_fd
    except OSError:
        raise InvalidIdentityStore() from None
    finally:
        if lock_fd is not None:
            if locked:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def provision_account(accounts_path, username, password, *, replace=False, forbidden_roots=(), role=None):
    """Create/reset an account locally; the private parent must already exist.

    This is not an HTTP action. Passwords are accepted in memory, never as CLI
    arguments. A reset generates a new salt, revoking existing sessions on their
    next account-file check even when the same password is entered again.
    """
    if not _username(username) or type(replace) is not bool or role not in (None, "reader", "operator"):
        raise ValueError('invalid account request')
    encoded = _password(password)
    path = _safe_path(accounts_path, forbidden_roots)
    with _account_transaction(path) as parent_fd:
        accounts = _read_accounts(path, allow_missing=True)
        exists = username in accounts
        if exists != replace:
            raise ValueError('account exists' if exists else 'account unavailable')
        if not exists and len(accounts) >= MAX_ACCOUNTS:
            raise ValueError('account limit reached')
        salt = secrets.token_bytes(32)
        accounts[username] = _Account(username, salt, _derive(encoded, salt),
                                      role or (accounts[username].role if exists else "reader"))
        try:
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            existing = True
        except FileNotFoundError:
            existing = False
        _publish_accounts(parent_fd, path.name, _encoded_accounts(accounts), existing=existing)


def parse_session_cookie(header, *, name=COOKIE_NAME):
    """Strict single-header parser; duplicate names or malformed values deny."""
    if not isinstance(name, str) or not _COOKIE_KEY.fullmatch(name):
        raise ValueError('invalid cookie name')
    if header is None:
        return None
    if (not isinstance(header, str) or not header or len(header) > MAX_COOKIE_BYTES
            or any(ord(c) < 32 or ord(c) > 126 for c in header)):
        raise AccessDenied()
    cookies = {}
    for segment in header.split(';'):
        key, separator, value = segment.strip(' ').partition('=')
        if (not separator or not _COOKIE_KEY.fullmatch(key) or key in cookies
                or any(ord(c) < 33 or c in '\",;\\' for c in value)):
            raise AccessDenied()
        cookies[key] = value
    token = cookies.get(name)
    if token is not None and not _TOKEN.fullmatch(token):
        raise AccessDenied()
    return token


class IdentityStore:
    """Existing accounts plus at most 64 hashed, non-persistent sessions."""
    def __init__(self, accounts_path, *, clock=time.time, forbidden_roots=()):
        if not callable(clock):
            raise ValueError('invalid clock')
        self._forbidden_roots = tuple(forbidden_roots)
        self._path = _safe_path(accounts_path, self._forbidden_roots)
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions = {}
        self._accounts = _read_accounts(self._path)
        self._attempts = deque()
        self._client_attempts = {}
        self._change_attempts = deque()
        self._account_change_attempts = {}
        self._dummy_salt = secrets.token_bytes(32)
        self._dummy_hash = secrets.token_bytes(32)
        self._last_now = None

    def _now(self):
        try:
            now = self._clock()
            if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now < 253402270000:
                raise ValueError()
            if self._last_now is not None and now < self._last_now:
                self._sessions.clear()
                raise AccessDenied()
            self._last_now = now
            return now
        except (ValueError, TypeError, OverflowError):
            self._sessions.clear()
            raise AccessDenied() from None

    def _reload(self):
        try:
            _safe_path(self._path, self._forbidden_roots)
            accounts = _read_accounts(self._path)
        except InvalidIdentityStore:
            self._sessions.clear()
            raise
        self._accounts = accounts
        for key, session in tuple(self._sessions.items()):
            account = accounts.get(session.username)
            if account is None or not hmac.compare_digest(account.fingerprint, session.fingerprint):
                del self._sessions[key]

    def _purge(self, now):
        for key, session in tuple(self._sessions.items()):
            if now >= min(session.created_at + ABSOLUTE_SECONDS, session.last_seen + IDLE_SECONDS):
                del self._sessions[key]

    def _attempt(self, client_key, now):
        cutoff = now - LOGIN_WINDOW_SECONDS
        while self._attempts and self._attempts[0] <= cutoff:
            self._attempts.popleft()
        for key, attempts in tuple(self._client_attempts.items()):
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._client_attempts[key]
        attempts = self._client_attempts.get(client_key, deque())
        deadlines = []
        if len(self._attempts) >= MAX_GLOBAL_ATTEMPTS:
            deadlines.append(self._attempts[0] + LOGIN_WINDOW_SECONDS)
        if len(attempts) >= MAX_CLIENT_ATTEMPTS:
            deadlines.append(attempts[0] + LOGIN_WINDOW_SECONDS)
        if deadlines:
            raise RateLimited(max(deadlines) - now)
        self._attempts.append(now)
        attempts.append(now)
        self._client_attempts[client_key] = attempts

    def _change_attempt(self, username, now):
        # Authenticated account identity is supplied by the existing session,
        # not a browser-selected key. This budget is independent of login.
        cutoff = now - LOGIN_WINDOW_SECONDS
        while self._change_attempts and self._change_attempts[0] <= cutoff:
            self._change_attempts.popleft()
        for key, attempts in tuple(self._account_change_attempts.items()):
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if not attempts:
                del self._account_change_attempts[key]
        attempts = self._account_change_attempts.get(username, deque())
        deadlines = []
        if len(self._change_attempts) >= MAX_GLOBAL_ATTEMPTS:
            deadlines.append(self._change_attempts[0] + LOGIN_WINDOW_SECONDS)
        if len(attempts) >= MAX_PASSWORD_CHANGE_ATTEMPTS:
            deadlines.append(attempts[0] + LOGIN_WINDOW_SECONDS)
        if deadlines:
            raise RateLimited(max(deadlines) - now)
        self._change_attempts.append(now)
        attempts.append(now)
        self._account_change_attempts[username] = attempts

    @staticmethod
    def _report(session):
        expires = min(session.created_at + ABSOLUTE_SECONDS, session.last_seen + IDLE_SECONDS)
        return {'schema': IDENTITY_SCHEMA, 'authenticated': True,
                'username': session.username, 'role': session.role,
                'expiresAt': datetime.fromtimestamp(expires, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}

    def login(self, username, password, client_key):
        # client_key is supplied by the transport's trusted peer selection;
        # this module never parses X-Forwarded-For or another request header.
        if (not isinstance(client_key, str) or not 1 <= len(client_key) <= 128
                or any(ord(c) < 33 or ord(c) > 126 for c in client_key)):
            raise AccessDenied()
        with self._lock:
            now = self._now()
            self._attempt(client_key, now)
            try:
                encoded = _password(password)
            except ValueError:
                raise AccessDenied() from None
            if not _username(username):
                raise AccessDenied()
            self._reload()
            account = self._accounts.get(username)
            derived = _derive(encoded, account.salt if account else self._dummy_salt)
            matched = hmac.compare_digest(derived, account.password_hash if account else self._dummy_hash)
            if not matched or account is None:
                raise AccessDenied()
            # A reset from another local provisioning process during the KDF
            # must not create a new session for the replaced credential.
            self._reload()
            current = self._accounts.get(username)
            if current is None or not hmac.compare_digest(current.fingerprint, account.fingerprint):
                raise AccessDenied()
            now = self._now()
            self._purge(now)
            if len(self._sessions) >= MAX_SESSIONS:
                oldest = min(self._sessions, key=lambda key: self._sessions[key].created_at)
                del self._sessions[oldest]
            token = secrets.token_urlsafe(32)
            key = hashlib.sha256(token.encode('ascii')).digest()
            session = _Session(username, account.fingerprint, now, now, account.role)
            self._sessions[key] = session
            return token, self._report(session)

    def session(self, token, touch=True):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token) or type(touch) is not bool:
            raise AccessDenied()
        key = hashlib.sha256(token.encode('ascii')).digest()
        with self._lock:
            now = self._now()
            self._reload()
            self._purge(now)
            session = self._sessions.get(key)
            if session is None:
                raise AccessDenied()
            if touch:
                session = replace(session, last_seen=now)
                self._sessions[key] = session
            return self._report(session)

    def logout(self, token):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise AccessDenied()
        with self._lock:
            self._sessions.pop(hashlib.sha256(token.encode('ascii')).digest(), None)

    def change_password(self, token, current_password, new_password):
        """Rotate only the authenticated account, without touching Vision Core.

        Current-password verification is followed by a credential compare and
        revalidation under the same file lock used by local provisioning. A
        competing reset/removal or expired session cannot overwrite its winner.
        All old sessions fail after publication, including other API owners.
        """
        with self._lock:
            session = self.session(token, touch=False)
            username = session['username']
            account = self._accounts[username]
            self._change_attempt(username, self._now())
            try:
                new_encoded = _password(new_password)
            except ValueError:
                raise PasswordRejected() from None
            try:
                current_encoded = _password(current_password)
            except ValueError:
                raise CurrentPasswordInvalid() from None
            if not hmac.compare_digest(_derive(current_encoded, account.salt), account.password_hash):
                raise CurrentPasswordInvalid()
            if hmac.compare_digest(new_encoded, current_encoded):
                raise PasswordRejected()
            salt = secrets.token_bytes(32)
            replacement = _Account(username, salt, _derive(new_encoded, salt), account.role)
            path = _safe_path(self._path, self._forbidden_roots)
            with _account_transaction(path, timeout=PASSWORD_CHANGE_LOCK_SECONDS) as parent_fd:
                # Hashing and lock acquisition may have crossed expiry, a
                # password reset or an account removal in another process.
                self.session(token, touch=False)
                current = self._accounts.get(username)
                if current is None or not hmac.compare_digest(current.fingerprint, account.fingerprint):
                    raise AccessDenied()
                accounts = dict(self._accounts)
                accounts[username] = replacement
                try:
                    _publish_accounts(parent_fd, path.name, _encoded_accounts(accounts), existing=True)
                except (OSError, InvalidIdentityStore):
                    # replace may already have committed before directory fsync
                    # failed. Reload the actual file; never roll back credentials
                    # or retain a known-stale session after an ambiguous result.
                    self._reload()
                    raise InvalidIdentityStore() from None
                self._reload()
                self.revoke_user(username)
            return {'schema': 'vision.api.password-change.v1', 'changed': True}

    def revoke_user(self, username):
        if not _username(username):
            raise ValueError('invalid account request')
        with self._lock:
            self._sessions = {key: value for key, value in self._sessions.items() if value.username != username}


def _generated_password_file(path, password):
    parent_fd = fd = None
    try:
        parent_fd = _open_parent(path)
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
        info = _private_regular(fd)
        _write_all(fd, (password + '\n').encode('ascii'))
        os.fsync(parent_fd)
        return (info.st_dev, info.st_ino)
    except Exception:
        if fd is not None:
            try:
                os.unlink(path.name, dir_fd=parent_fd)
            except OSError:
                pass
        raise
    finally:
        if fd is not None:
            os.close(fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _remove_generated(path, identity):
    parent_fd = None
    try:
        parent_fd = _open_parent(path)
        info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) == identity:
            os.unlink(path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    except OSError:
        pass
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Provision a local Vision account without printing secrets.')
    parser.add_argument('--accounts', required=True)
    parser.add_argument('--forbid-root', action='append', default=[])
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('provision', 'reset'):
        subparser = commands.add_parser(command)
        subparser.add_argument('username')
        subparser.add_argument('--role', choices=('reader', 'operator'), help='Explicit local permission; new accounts default to reader; reset preserves role.')
        subparser.add_argument('--generate-to', help='Create a new 0600 password file; never overwrite an existing file.')
    args = parser.parse_args(argv)
    generated_path = generated_identity = None
    try:
        path = _safe_path(args.accounts, args.forbid_root)
        if args.generate_to:
            generated_path = _safe_path(args.generate_to, args.forbid_root)
            if generated_path in (path, path.with_name(path.name + '.lock')):
                raise InvalidIdentityStore()
            password = secrets.token_urlsafe(32)
            generated_identity = _generated_password_file(generated_path, password)
        else:
            password = getpass.getpass('New account password: ')
            confirmation = getpass.getpass('Confirm account password: ')
            if not hmac.compare_digest(_password(password), _password(confirmation)):
                raise ValueError('password confirmation mismatch')
        provision_account(path, args.username, password, replace=args.command == 'reset',
                          forbidden_roots=args.forbid_root, role=args.role)
        return 0
    except (ValueError, OSError, EOFError, KeyboardInterrupt):
        if generated_identity is not None:
            _remove_generated(generated_path, generated_identity)
        print('Identity provisioning failed; no password is printed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
