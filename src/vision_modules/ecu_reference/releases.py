"""Append-only canonical reference snapshots; digests are not authentication."""
import os
import secrets
import stat
from .codec import MAX_BYTES, canonical_json, content_sha256, load_json
from .validation import _id

class ReferenceReleaseStore:
    def __init__(self, directory): self._dir = os.open(os.fspath(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    def close(self):
        if self._dir is not None: os.close(self._dir); self._dir = None
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    @staticmethod
    def _name(profile_id, revision):
        _id(profile_id); _id(revision)
        return f'{len(profile_id)}_{profile_id}_{revision}.json'
    @staticmethod
    def _validate(profile):
        d = profile.data; m = d['metadata']; p = d['provenance_release']; digest = content_sha256(profile)
        if (m['schema_version'] != '1' or m['template_only'] is not False or m['status'] != 'APPROVED'
            or m['content_sha256'] != digest or p['released_snapshot_sha256'] != digest
            or not p['release_approval'] or p['release_approval']['content_sha256'] != digest):
            raise ValueError('invalid reference release approval or digest')
        return digest
    def publish(self, profile):
        digest = self._validate(profile); m = profile.data['metadata']; data = canonical_json(profile).encode('ascii')
        if len(data) > MAX_BYTES: raise ValueError('canonical release exceeds size limit')
        name = self._name(m['profile_id'], m['profile_revision']); pending = '.reference-' + secrets.token_hex(16)
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self._dir)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
            os.link(pending, name, src_dir_fd=self._dir, dst_dir_fd=self._dir, follow_symlinks=False)
            os.fsync(self._dir)
        finally:
            os.unlink(pending, dir_fd=self._dir); os.fsync(self._dir)
        return digest
    def read(self, profile_id, revision):
        try:
            fd = os.open(self._name(profile_id, revision), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._dir)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('release must be regular')
                with os.fdopen(fd, 'rb', closefd=False) as stream: data = stream.read(MAX_BYTES + 1)
            finally: os.close(fd)
            profile = load_json(data); self._validate(profile); m = profile.data['metadata']
            if canonical_json(profile).encode('ascii') != data or (m['profile_id'], m['profile_revision']) != (profile_id, revision): raise ValueError('release snapshot mismatch')
            return profile
        except OSError as exc: raise ValueError('reference release unavailable') from exc
    def require(self, profile):
        digest = self._validate(profile); m = profile.data['metadata']
        if canonical_json(self.read(m['profile_id'], m['profile_revision'])) != canonical_json(profile): raise ValueError('reference release changed')
        return digest
