"""Offline, descriptor-relative verification of controlled reference assets."""
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from .validation import _path, _id

MAX_ASSET_BYTES = 128 * 1024 * 1024
# Metadata is checked, never interpreted as image content.
MIMES = {'photo': {'image/png', 'image/jpeg'}, 'image': {'image/png', 'image/jpeg'},
         'thermal': {'image/png', 'image/tiff'}, 'drawing': {'image/png', 'image/jpeg', 'application/pdf'},
         'collision_geometry': {'model/stl', 'application/sla', 'application/octet-stream'}}

@dataclass(frozen=True)
class VerifiedAsset:
    asset_id: str
    sha256: str
    bytes: int

class AssetStore:
    def __init__(self, directory):
        self._dir = os.open(os.fspath(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    def close(self):
        if self._dir is not None:
            os.close(self._dir); self._dir = None
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def verify_asset(self, asset):
        try:
            _id(asset['asset_id']); _id(asset['physical_state_id']); _id(asset['source_id'])
            path = asset['relative_path']; _path(path)
            if len(path) > 4096 or any(len(p) > 255 for p in path.split('/')): raise ValueError('asset path too long')
            size = asset['bytes']; digest = asset['sha256']
            if type(size) is not int or not 0 < size <= MAX_ASSET_BYTES: raise ValueError('invalid asset size')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest): raise ValueError('invalid asset digest')
            if asset['mime'] not in MIMES.get(asset['kind'], set()) or asset['verified'] is not True or not asset['privacy_class']:
                raise ValueError('invalid asset metadata')
            current = os.dup(self._dir)
            try:
                parts = path.split('/')
                for part in parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                    os.close(current); current = child
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
                try:
                    st = os.fstat(fd)
                    if not stat.S_ISREG(st.st_mode) or st.st_size != size: raise ValueError('asset size or type mismatch')
                    h = hashlib.sha256(); total = 0
                    while True:
                        chunk = os.read(fd, min(1024 * 1024, MAX_ASSET_BYTES + 1 - total))
                        if not chunk: break
                        total += len(chunk)
                        if total > MAX_ASSET_BYTES: raise ValueError('asset too large')
                        h.update(chunk)
                    if total != size or h.hexdigest() != digest.lower(): raise ValueError('asset digest or size mismatch')
                    return VerifiedAsset(asset['asset_id'], h.hexdigest(), total)
                finally: os.close(fd)
            finally: os.close(current)
        except (OSError, KeyError, TypeError) as exc:
            raise ValueError('asset verification failed') from exc
