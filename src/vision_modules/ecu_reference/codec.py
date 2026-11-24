"""Bounded JSON decoding and deterministic snapshot serialization."""
import hashlib
import json
import math
from .models import ReferenceProfile, thaw
from .validation import validate_preview

MAX_BYTES = 512 * 1024
MAX_DEPTH = 32
MAX_COLLECTION = 1024
MAX_STRING = 4096


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _bounds(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError('maximum nesting exceeded')
    if isinstance(value, (dict, list)):
        if len(value) > MAX_COLLECTION:
            raise ValueError('collection too large')
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for key, item in items:
            if isinstance(key, str) and len(key) > MAX_STRING:
                raise ValueError('key too long')
            _bounds(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > MAX_STRING or any(ord(c) < 32 for c in value):
            raise ValueError('invalid string')
    elif type(value) in (int, float):
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError('number out of range')
    elif value is not None and type(value) is not bool:
        raise ValueError('invalid JSON value')


def load_json(data):
    try:
        if isinstance(data, str):
            data = data.encode('utf-8')
        if not isinstance(data, bytes) or len(data) > MAX_BYTES:
            raise ValueError('invalid or oversized JSON')
        value = json.loads(data.decode('utf-8'), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        _bounds(value)
        validate_preview(value)
        return ReferenceProfile._validated(value)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON') from exc


def canonical_json(profile):
    if not isinstance(profile, ReferenceProfile):
        raise ValueError('reference profile required')
    return json.dumps(thaw(profile.data), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def content_sha256(profile):
    """Hash V1 domain and all snapshot content except digest and endorsement."""
    if not isinstance(profile, ReferenceProfile):
        raise ValueError('reference profile required')
    data = thaw(profile.data)
    data['metadata'].pop('content_sha256', None)
    data['provenance_release'].pop('release_approval', None)
    data['provenance_release'].pop('released_snapshot_sha256', None)
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(b'ecu-reference-profile-v1\0' + canonical.encode('ascii')).hexdigest()
