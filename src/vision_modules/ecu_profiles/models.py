"""Immutable, strictly decoded catalog records; all coordinates are millimetres."""
from dataclasses import dataclass, fields, asdict
from datetime import date, datetime
import hashlib
import json
import math
import re

MAX_BYTES = 512 * 1024
LIMIT = 1_000_000
IDENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
SHA = re.compile(r'^[0-9a-f]{64}$')


def identifier(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('invalid identifier')
    return value


def frame_identifier(value):
    if not isinstance(value, str) or len(value) > 255 or not value:
        raise ValueError('invalid frame identifier')
    if any(not IDENT.fullmatch(segment) for segment in value.split('/')):
        raise ValueError('invalid frame identifier')
    return value


def number(value, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > LIMIT or (positive and value <= 0):
        raise ValueError('invalid bounded number')
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError('missing or invalid text')
    return value


def timestamp(value):
    text(value)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError('timezone-aware timestamp required') from exc


def day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise ValueError('invalid date') from exc


def vector(value, size, positive=False):
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise ValueError('invalid vector')
    return tuple(number(x, positive) for x in value)


@dataclass(frozen=True)
class Provenance:
    status: str
    date: str
    instrument: str | None
    datum: str | None
    uncertainty_mm: float | None
    reference: str
    def __post_init__(self):
        if self.status not in ('FIELD_NOTE', 'DRAFT_NOTE', 'MEASURED', 'VERIFIED'): raise ValueError('invalid provenance status')
        day(self.date); text(self.reference)
        if self.instrument is not None: text(self.instrument)
        if self.datum is not None: identifier(self.datum)
        if self.uncertainty_mm is not None: number(self.uncertainty_mm, True)

@dataclass(frozen=True)
class Measurement:
    values: tuple
    provenance: Provenance
    def __post_init__(self):
        if not isinstance(self.provenance, Provenance): raise ValueError('invalid provenance')
        if not isinstance(self.values, (tuple, list)) or not self.values: raise ValueError('empty measurement')
        object.__setattr__(self, 'values', tuple(number(x) for x in self.values))

@dataclass(frozen=True)
class Connector:
    connector_id: str
    color: str
    position: Measurement | None
    identity_required: bool
    def __post_init__(self):
        identifier(self.connector_id)
        if self.color not in ('black', 'gray', 'other'): raise ValueError('invalid color')
        if type(self.identity_required) is not bool: raise ValueError('invalid identity requirement')
        if self.position is not None and (not isinstance(self.position, Measurement) or len(self.position.values) != 3): raise ValueError('invalid connector position')

@dataclass(frozen=True)
class ViewTarget:
    view_id: str
    position: Measurement
    quaternion_xyzw: tuple | None
    tolerance_mm: float
    capture_required: bool
    orientation_provenance: Provenance | None = None
    def __post_init__(self):
        identifier(self.view_id)
        if not isinstance(self.position, Measurement) or len(self.position.values) != 3: raise ValueError('invalid view position')
        if self.quaternion_xyzw is not None:
            q = vector(self.quaternion_xyzw, 4)
            if abs(math.hypot(*q)-1) > 1e-5: raise ValueError('invalid quaternion')
            object.__setattr__(self, 'quaternion_xyzw', q)
        if self.orientation_provenance is not None and not isinstance(self.orientation_provenance, Provenance): raise ValueError('invalid orientation provenance')
        number(self.tolerance_mm, True)
        if self.capture_required is not True: raise ValueError('view must require capture')

@dataclass(frozen=True)
class FieldNote:
    connector_color: str
    reported_height_mm: float
    provenance: Provenance
    def __post_init__(self):
        if self.connector_color not in ('black', 'gray', 'other'): raise ValueError('invalid note color')
        number(self.reported_height_mm, True)
        if not isinstance(self.provenance, Provenance) or self.provenance.status != 'FIELD_NOTE': raise ValueError('field note provenance required')

@dataclass(frozen=True)
class ApprovalEvidence:
    profile_id: str
    revision: str
    digest: str
    reviewer_id: str
    time: str
    reference: str
    def __post_init__(self):
        for x in (self.profile_id, self.revision, self.reviewer_id): identifier(x)
        if not isinstance(self.digest, str) or not SHA.fullmatch(self.digest): raise ValueError('invalid approval digest')
        timestamp(self.time); text(self.reference)

@dataclass(frozen=True)
class ECURecord:
    schema_version: int
    profile_id: str
    family: str
    variant: str
    variant_is_manufacturer: bool
    revision: str
    status: str
    declared_type: str
    connectors: tuple[Connector, ...]
    field_notes: tuple[FieldNote, ...]
    envelope: Measurement | None
    pcb_regions: tuple[Measurement, ...]
    views: tuple[ViewTarget, ...]
    capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    calibration_dependencies: tuple[tuple[str, str], ...]
    approval: ApprovalEvidence | None
    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1: raise ValueError('unsupported schema')
        for x in (self.profile_id, self.family, self.variant, self.revision, self.declared_type): identifier(x)
        if type(self.variant_is_manufacturer) is not bool or self.status not in ('DRAFT', 'READY_FOR_REVIEW', 'APPROVED'): raise ValueError('invalid record status')
        for name, cls in (('connectors', Connector), ('field_notes', FieldNote), ('pcb_regions', Measurement), ('views', ViewTarget)):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or len(values) > 128 or any(not isinstance(v, cls) for v in values): raise ValueError('invalid collection')
            object.__setattr__(self, name, tuple(values))
        if self.envelope is not None and (not isinstance(self.envelope, Measurement) or len(self.envelope.values) != 3): raise ValueError('invalid envelope')
        if any(len(r.values) != 4 for r in self.pcb_regions): raise ValueError('invalid region')
        for seq in (self.connectors, self.views):
            ids = [getattr(x, 'connector_id', None) or x.view_id for x in seq]
            if len(ids) != len(set(ids)): raise ValueError('duplicate feature id')
        for name in ('capabilities', 'required_capabilities'):
            values = getattr(self, name)
            if not isinstance(values, (tuple, list)) or len(values) > 128: raise ValueError('invalid capabilities')
            for v in values: identifier(v)
            if len(set(values)) != len(values): raise ValueError('duplicate capability')
            object.__setattr__(self, name, tuple(sorted(values)))
        deps = self.calibration_dependencies
        if not isinstance(deps, (list, tuple)) or len(deps) > 128: raise ValueError('invalid calibration dependencies')
        pairs = []
        for pair in deps:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2: raise ValueError('invalid calibration dependency')
            pairs.append((identifier(pair[0]), identifier(pair[1])))
        if len({p[0] for p in pairs}) != len(pairs): raise ValueError('duplicate calibration')
        object.__setattr__(self, 'calibration_dependencies', tuple(sorted(pairs)))
        if self.approval is not None and not isinstance(self.approval, ApprovalEvidence): raise ValueError('invalid approval')


def document(record, *, endorsement=True):
    if not isinstance(record, ECURecord): raise ValueError('record required')
    result = asdict(record)
    # Approval changes release state, not the content reviewed by the human.
    if not endorsement:
        result.pop('approval')
        result['status'] = 'READY_FOR_REVIEW'
    return result


def canonical_json(record):
    return json.dumps(document(record), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def record_sha256(record):
    data = json.dumps(document(record, endorsement=False), sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(data.encode('ascii')).hexdigest()


def _object(cls, obj, convert=None):
    if not isinstance(obj, dict) or set(obj) != {f.name for f in fields(cls)}: raise ValueError('unknown or missing fields for ' + cls.__name__)
    values = dict(obj)
    for key, fn in (convert or {}).items(): values[key] = fn(values[key])
    return cls(**values)


def _measurement(obj):
    return _object(Measurement, obj, {'provenance': lambda x: _object(Provenance, x)})


def _optional(fn):
    return lambda x: None if x is None else fn(x)


def _array(fn):
    def convert(x):
        if not isinstance(x, list): raise ValueError('array required')
        return tuple(fn(v) for v in x)
    return convert


def load_json(data):
    if isinstance(data, str): data = data.encode('utf-8')
    if not isinstance(data, bytes) or len(data) > MAX_BYTES: raise ValueError('invalid or oversized JSON')
    def unique(pairs):
        d = {}
        for k, v in pairs:
            if k in d: raise ValueError('duplicate JSON key')
            d[k] = v
        return d
    try:
        obj = json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        return _object(ECURecord, obj, {
            'connectors': _array(lambda x: _object(Connector, x, {'position': _optional(_measurement)})),
            'field_notes': _array(lambda x: _object(FieldNote, x, {'provenance': lambda p: _object(Provenance, p)})),
            'envelope': _optional(_measurement), 'pcb_regions': _array(_measurement),
            'views': _array(lambda x: _object(ViewTarget, x, {'position': _measurement, 'orientation_provenance': _optional(lambda p: _object(Provenance, p))})),
            'approval': _optional(lambda x: _object(ApprovalEvidence, x))})
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON record') from exc
