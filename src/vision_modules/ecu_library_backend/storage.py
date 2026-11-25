"""Private, atomic draft and asset persistence."""
import hashlib
import json
import struct
import fcntl
from contextlib import contextmanager
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from dataclasses import dataclass

from vision_modules.ecu_reference import canonical_json, load_json
from vision_modules.ecu_reference.models import thaw

REPO = Path(__file__).resolve().parents[3]
IDENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
SHA = re.compile(r'^[0-9a-f]{64}$')
GENERATION = re.compile(r'^[0-9a-f]{32}$')
MAX_DOCUMENT_BYTES = 512 * 1024
MAX_IMAGE_PIXELS = 30_000_000
MAX_IMAGE_DIMENSION = 30_000
MAX_HISTORY_REVISIONS = 4096
MAX_READ_PROFILES = 256
MAX_READ_BYTES = 8 * 1024 * 1024
READ_LOCK_TIMEOUT = 0.25


class DraftReadUnavailable(RuntimeError):
    """A fixed, transport-safe reason without filesystem exception text."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SavedRevision:
    snapshot_id: str
    etag: str
    revision: str


@dataclass(frozen=True)
class DraftReadSnapshot:
    key: str
    profile: object
    etag: str
    history: tuple[SavedRevision, ...]


class _ReadBudget:
    """One aggregate budget for all pointer and history reads in a view."""
    def __init__(self):
        self.bytes_left = MAX_READ_BYTES
        self.revisions_left = MAX_HISTORY_REVISIONS

    def revision(self):
        if self.revisions_left <= 0:
            raise DraftReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
        self.revisions_left -= 1


def _snapshot_hash(snapshot):
    data = json.dumps(snapshot, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')
    return hashlib.sha256(data).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('unsafe identifier')
    return value


def _check_path(path):
    path = Path(os.path.abspath(path))
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError('symlink path rejected')
    return path


class DraftStore:
    def __init__(self, root):
        self.root = _check_path(root)
        if self.root == REPO or REPO in self.root.parents:
            raise ValueError('data root must be outside source tree')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.root.is_dir(): raise ValueError('data root must be a directory')
        # Only directories owned by this application are tightened.
        os.chmod(self.root, 0o700)
        for name in ('drafts', 'history', 'assets'):
            p = _check_path(self.root / name)
            p.mkdir(mode=0o700, exist_ok=True)
            if not p.is_dir(): raise ValueError('invalid storage directory')
            os.chmod(p, 0o700)
        self.lock = threading.RLock()
        self._transaction_state = threading.local()

    @contextmanager
    def transaction(self):
        with self.lock:
            if getattr(self._transaction_state, "active", False):
                yield
                return
            path = _check_path(self.root / ".lock")
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("invalid lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                self._transaction_state.active = True
                yield
            finally:
                self._transaction_state.active = False
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _path(self, area, name):
        p = _check_path(self.root / area / name)
        if p.exists() and not stat.S_ISREG(p.stat().st_mode): raise ValueError('regular file required')
        return p

    def _read(self, area, name, limit=512*1024, *, budget=None):
        p = self._path(area, name)
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('regular file required')
            read_limit = limit if budget is None else min(limit, budget.bytes_left)
            with os.fdopen(fd, 'rb', closefd=False) as f: data = f.read(read_limit + 1)
            if budget is not None:
                if len(data) > budget.bytes_left:
                    raise DraftReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
                budget.bytes_left -= len(data)
            if len(data) > limit: raise ValueError('stored file too large')
            return data
        finally: os.close(fd)

    def _write(self, area, name, data, replace=False):
        directory = _check_path(self.root / area)
        self._path(area, name)
        tmp = directory / ('.tmp-' + secrets.token_hex(16))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            if replace: os.replace(tmp, directory / name)
            else: os.link(tmp, directory / name, follow_symlinks=False)
            dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if tmp.exists(): tmp.unlink()

    @staticmethod
    def etag(data): return '"' + hashlib.sha256(data).hexdigest() + '"'

    def _pointer(self, key, *, budget=None):
        try:
            pointer = json.loads(self._read('drafts', key + '.json', budget=budget))
            if (not isinstance(pointer, dict) or set(pointer) != {'key', 'generation'}
                    or pointer['key'] != key or not isinstance(pointer['generation'], str)
                    or not GENERATION.fullmatch(pointer['generation'])):
                raise ValueError('invalid draft pointer')
            return pointer['generation']
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise ValueError('invalid draft pointer') from exc

    def _snapshot(self, key, generation, *, budget=None):
        try:
            if budget is not None:
                budget.revision()
            raw = self._read('history', key + '--' + generation + '.json', budget=budget)
            snapshot = json.loads(raw)
            if (not isinstance(snapshot, dict) or set(snapshot) != {'key', 'generation', 'previous', 'sha256', 'profile', 'snapshot_sha256'}
                    or snapshot['key'] != key or snapshot['generation'] != generation
                    or (snapshot['previous'] is not None and
                        (not isinstance(snapshot['previous'], str) or not GENERATION.fullmatch(snapshot['previous'])))
                    or not isinstance(snapshot['sha256'], str) or not SHA.fullmatch(snapshot['sha256'])
                    or not isinstance(snapshot['snapshot_sha256'], str) or not SHA.fullmatch(snapshot['snapshot_sha256'])):
                raise ValueError('invalid snapshot')
            digest = snapshot.pop('snapshot_sha256')
            if _snapshot_hash(snapshot) != digest:
                raise ValueError('snapshot integrity failure')
            profile = load_json(json.dumps(snapshot['profile'], ensure_ascii=True, separators=(',', ':')))
            data = canonical_json(profile).encode('ascii')
            if (len(data) > MAX_DOCUMENT_BYTES or hashlib.sha256(data).hexdigest() != snapshot['sha256']
                    or profile.data['metadata']['profile_id'] != key):
                raise ValueError('snapshot integrity failure')
            return profile, snapshot['previous']
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError) as exc:
            raise ValueError('invalid snapshot') from exc

    def _chain(self, key, *, budget=None):
        generation = self._pointer(key, budget=budget)
        result = []
        seen = set()
        while generation is not None:
            if generation in seen: raise ValueError('snapshot cycle')
            if len(result) >= MAX_HISTORY_REVISIONS: raise ValueError('history too long')
            seen.add(generation)
            profile, previous = self._snapshot(key, generation, budget=budget)
            result.append((generation, profile))
            generation = previous
        return result

    def get(self, key):
        identifier(key)
        with self.lock:
            generation, profile = self._chain(key)[0]
            return profile, self.etag(generation.encode('ascii'))

    def save(self, key, profile, match=None, create=False):
        identifier(key)
        m = profile.data['metadata']; pr = profile.data['provenance_release']
        if m['profile_id'] != key: raise ValueError('profile key mismatch')
        if m['status'] != 'DRAFT' or m['template_only'] or m['content_sha256'] is not None or m['approval_scopes'] or pr['release_approval'] is not None or pr['released_snapshot_sha256'] is not None:
            raise ValueError('only unsigned drafts may be saved')
        data = canonical_json(profile).encode('ascii')
        if len(data) > MAX_DOCUMENT_BYTES: raise ValueError('profile too large')
        with self.transaction():
            previous = None
            if create:
                if self._path('drafts', key + '.json').exists(): raise FileExistsError('draft exists')
            else:
                chain = self._chain(key)
                if len(chain) >= MAX_HISTORY_REVISIONS: raise ValueError('history too long')
                previous, old = chain[0]
                etag = self.etag(previous.encode('ascii'))
                om = old.data['metadata']; op = old.data['provenance_release']
                if om['status'] != 'DRAFT' or om['template_only'] or om['content_sha256'] is not None or om['approval_scopes'] or op['release_approval'] is not None or op['released_snapshot_sha256'] is not None: raise ValueError('stored revision is immutable')
                if any(om[k] != m[k] for k in ('profile_id','family_id','variant_id','profile_revision')): raise ValueError('revision key mismatch')
                if not match or match != etag: raise FileExistsError('ETag conflict')
            for existing_key in self.keys():
                if existing_key != key:
                    other, _ = self.get(existing_key)
                    other_m = other.data['metadata']
                    if all(other_m[k] == m[k] for k in ('family_id', 'variant_id', 'profile_revision')):
                        raise FileExistsError('family/variant/revision already exists')
            generation = secrets.token_hex(16)
            snapshot = {'key': key, 'generation': generation, 'previous': previous,
                        'sha256': hashlib.sha256(data).hexdigest(), 'profile': thaw(profile.data)}
            snapshot['snapshot_sha256'] = _snapshot_hash(snapshot)
            snapshot_data = json.dumps(snapshot, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
            if len(snapshot_data) > MAX_DOCUMENT_BYTES: raise ValueError('snapshot too large')
            pointer = json.dumps({'key': key, 'generation': generation}, separators=(',', ':')).encode('ascii')
            self._write('history', key + '--' + generation + '.json', snapshot_data)
            self._write('drafts', key + '.json', pointer, replace=not create)
            return self.etag(generation.encode('ascii'))

    def history(self, key):
        identifier(key)
        with self.lock:
            result = []
            for generation, profile in self._chain(key):
                result.append({'snapshot_id': generation, 'etag': self.etag(generation.encode('ascii')), 'revision': profile.data['metadata']['profile_revision'], 'profile': thaw(profile.data)})
            return list(reversed(result))

    def keys(self):
        result = []
        for p in (self.root / 'drafts').iterdir():
            if p.name.endswith('.json') and IDENT.fullmatch(p.name[:-5]):
                self._path('drafts', p.name); result.append(p.name[:-5])
        return sorted(result)

    def _read_keys(self):
        """Bound directory enumeration before loading any profile history."""
        result = []
        examined = 0
        directory = _check_path(self.root / 'drafts')
        with os.scandir(directory) as entries:
            for entry in entries:
                examined += 1
                if examined > MAX_READ_PROFILES * 2:
                    raise DraftReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
                if entry.name.endswith('.json') and IDENT.fullmatch(entry.name[:-5]):
                    self._path('drafts', entry.name)
                    result.append(entry.name[:-5])
                    if len(result) > MAX_READ_PROFILES:
                        raise DraftReadUnavailable('LIBRARY_LIMIT_EXCEEDED')
        return tuple(sorted(result))

    def read_snapshot(self):
        """Read a bounded, immutable committed view without initializing files.

        Writers use the same owner lock and ``.lock`` inode. A missing lock is
        accepted only as an empty initial store and returns that empty snapshot
        directly; no later directory traversal can accidentally read a first
        publication without its lock. The complete lineage is verified before
        any projected data is returned. An over-budget view fails as a whole.
        """
        if not self.lock.acquire(timeout=READ_LOCK_TIMEOUT):
            raise DraftReadUnavailable('LIBRARY_BUSY')
        fd = None
        locked = False
        try:
            # Re-entrant reads cannot observe the middle of an owner mutation.
            if getattr(self._transaction_state, 'active', False):
                raise DraftReadUnavailable('LIBRARY_BUSY')
            path = _check_path(self.root / '.lock')
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                if self._read_keys():
                    raise DraftReadUnavailable('LIBRARY_INCONSISTENT')
                return ()
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DraftReadUnavailable('LIBRARY_INCONSISTENT')
            deadline = time.monotonic() + READ_LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DraftReadUnavailable('LIBRARY_BUSY')
                    time.sleep(min(0.01, remaining))
            budget = _ReadBudget()
            result = []
            identities = set()
            for key in self._read_keys():
                chain = self._chain(key, budget=budget)
                current_generation, current = chain[0]
                metadata = current.data['metadata']
                identity = tuple(metadata[k] for k in ('profile_id', 'family_id', 'variant_id', 'profile_revision'))
                if identity[1:] in identities:
                    raise DraftReadUnavailable('LIBRARY_INCONSISTENT')
                identities.add(identity[1:])
                history = []
                for generation, profile in reversed(chain):
                    m = profile.data['metadata']; p = profile.data['provenance_release']
                    if (tuple(m[k] for k in ('profile_id', 'family_id', 'variant_id', 'profile_revision')) != identity
                            or m['schema_version'] != '1' or m['template_only'] is not False
                            or m['status'] != 'DRAFT' or m['content_sha256'] is not None
                            or m['approval_scopes'] or p['release_approval'] is not None
                            or p['released_snapshot_sha256'] is not None):
                        raise DraftReadUnavailable('LIBRARY_INCONSISTENT')
                    history.append(SavedRevision(generation, self.etag(generation.encode('ascii')), m['profile_revision']))
                result.append(DraftReadSnapshot(key, current,
                    self.etag(current_generation.encode('ascii')), tuple(history)))
            return tuple(result)
        except DraftReadUnavailable:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise DraftReadUnavailable('LIBRARY_UNAVAILABLE') from exc
        finally:
            if fd is not None:
                if locked:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            self.lock.release()

    def put_asset(self, data):
        if len(data) > 8*1024*1024: raise ValueError('asset too large')
        mime = image_type(data)
        digest = hashlib.sha256(data).hexdigest()
        with self.lock:
            try: self._write('assets', digest, data)
            except FileExistsError:
                if self._read('assets', digest, 8*1024*1024) != data: raise ValueError('asset hash mismatch')
        return {'sha': digest, 'sha256': digest, 'relative_path': 'assets/' + digest, 'mime': mime, 'size': len(data), 'verified': False, 'status': 'UNVERIFIED'}

    def get_asset(self, sha):
        if not isinstance(sha, str) or not SHA.fullmatch(sha): raise ValueError('invalid asset hash')
        data = self._read('assets', sha, 8*1024*1024)
        if hashlib.sha256(data).hexdigest() != sha: raise ValueError('asset hash mismatch')
        return data, image_type(data)


def _image_dimensions(data, mime):
    if mime == 'image/png':
        if len(data) < 33 or data[8:16] != b'\x00\x00\x00\x0dIHDR':
            raise ValueError('invalid PNG header')
        return struct.unpack('>II', data[16:24])
    pos = 2
    sof = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
    while pos < len(data):
        if data[pos] != 0xff: raise ValueError('invalid JPEG header')
        while pos < len(data) and data[pos] == 0xff: pos += 1
        if pos >= len(data): break
        marker = data[pos]; pos += 1
        if marker in (0xd8, 0xd9, 0xda, 0x00): break
        if marker == 0x01 or 0xd0 <= marker <= 0xd7: continue
        if pos + 2 > len(data): break
        length = int.from_bytes(data[pos:pos+2], 'big')
        if length < 2 or pos + length > len(data): break
        if marker in sof:
            if length < 8: break
            height, width = struct.unpack('>HH', data[pos+3:pos+7])
            return width, height
        pos += length
    raise ValueError('invalid JPEG header')


def _check_dimensions(width, height):
    if (not width or not height or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION
            or width * height > MAX_IMAGE_PIXELS):
        raise ValueError('invalid or excessive image dimensions')


def image_type(data):
    """Validate dimensions before and after decoding bounded image data."""
    if not isinstance(data, bytes) or not data or len(data) > 8 * 1024 * 1024:
        raise ValueError('invalid or oversized image')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        mime = 'image/png'
    elif data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        mime = 'image/jpeg'
    else:
        raise ValueError('invalid JPEG or PNG image')
    width, height = _image_dimensions(data, mime)
    _check_dimensions(width, height)
    import cv2
    import numpy as np
    try:
        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except Exception as exc:
        raise ValueError('invalid image') from exc
    if decoded is None or not decoded.size:
        raise ValueError('invalid image')
    _check_dimensions(decoded.shape[1], decoded.shape[0])
    if decoded.shape[:2] != (height, width): raise ValueError('image dimensions mismatch')
    return mime
