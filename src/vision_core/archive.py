"""Private, no-replacement archive for adapter-provided original bytes."""
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise ValueError('unsafe identifier')
    return value


class Archive:
    def __init__(self, root: str, session_id: str):
        # Open every existing component without following symlinks.
        path = Path(root).absolute()
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nxt
            session = _name(session_id)
            try:
                os.mkdir(session, 0o700, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                pass
            self.fd = os.open(session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        finally:
            os.close(fd)
        self.path = path / session

    def close(self):
        os.close(self.fd)

    def _read(self, name: str) -> bytes:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}', name) or '..' in name:
            raise ValueError('invalid archive entry')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_mode & 0o222:
                raise ValueError('archive entry is not a regular file')
            with os.fdopen(fd, 'rb', closefd=False) as f:
                return f.read()
        finally:
            os.close(fd)

    def write(self, name: str, data: bytes) -> str:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}', name) or '..' in name or not data:
            raise ValueError('invalid archive entry')
        temp = '.tmp-' + uuid.uuid4().hex
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                os.fchmod(f.fileno(), 0o400)
                os.fsync(f.fileno())
            # Hard-link publication is atomic and fails if the destination exists.
            os.link(temp, name, src_dir_fd=self.fd, dst_dir_fd=self.fd, follow_symlinks=False)
            os.fsync(self.fd)
        finally:
            os.unlink(temp, dir_fd=self.fd)
            os.fsync(self.fd)
        expected = digest(data)
        if digest(self._read(name)) != expected:
            raise ValueError('stored copy hash mismatch')
        return expected

    def verify(self, name: str, expected: str) -> None:
        if digest(self._read(name)) != expected:
            raise ValueError('archive integrity mismatch')

    def manifest(self, document: dict) -> tuple[str, str]:
        data = json.dumps(document, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
        name = 'manifest-v1.json'
        return name, self.write(name, data)
