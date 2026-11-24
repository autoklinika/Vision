"""Local append-only release snapshots; directory access is an external trust boundary."""
import os
import stat
import secrets
from .models import canonical_json, identifier, load_json, record_sha256, MAX_BYTES


class ReleaseStore:
    def __init__(self, directory):
        self.directory = os.fspath(directory)
        self._dir = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        if self._dir is not None:
            os.close(self._dir)
            self._dir = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    @staticmethod
    def _name(profile_id, revision):
        # Length prefix prevents collisions even when identifiers contain underscores.
        identifier(profile_id); identifier(revision)
        return f'{len(profile_id)}_{profile_id}_{revision}.json'

    def publish(self, record, calibrations, *, catalog):
        from .promotion import to_core_ecu_profile
        to_core_ecu_profile(record, calibrations, catalog=catalog)
        data = canonical_json(record).encode('ascii')
        name = self._name(record.profile_id, record.revision)
        # Use the opened directory descriptor for ALL path operations.
        # A pathname rename/replacement after __init__ cannot redirect
        # the temporary publication file to a different directory.
        pending = '.release-' + secrets.token_hex(16)
        fd = os.open(
            pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self._dir)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            # Exclusive hard link refuses to replace an existing revision,
            # including when different processes publish concurrently.
            os.link(pending, name, src_dir_fd=self._dir,
                    dst_dir_fd=self._dir, follow_symlinks=False)
            os.fsync(self._dir)
        finally:
            os.unlink(pending, dir_fd=self._dir)
            os.fsync(self._dir)
        return record_sha256(record)

    def read(self, profile_id, revision):
        fd = os.open(self._name(profile_id, revision), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._dir)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('release must be a regular file')
            with os.fdopen(fd, 'rb', closefd=False) as stream: data = stream.read(MAX_BYTES + 1)
        finally:
            os.close(fd)
        record = load_json(data)
        if canonical_json(record).encode('ascii') != data or record.profile_id != profile_id or record.revision != revision or record.status != 'APPROVED' or record.approval is None or record.approval.digest != record_sha256(record):
            raise ValueError('invalid or tampered release')
        return record

    def require(self, record):
        if self.read(record.profile_id, record.revision) != record: raise ValueError('release snapshot mismatch')
        return record_sha256(record)
