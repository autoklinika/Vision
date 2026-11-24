"""Offline, scene-bound inspection specifications and measured coverage.

Coordinates are millimetres; yaw is radians about +Z. This is not a motion
plan, IK solution, collision check, or a source of measured camera footprints.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Mapping

from .models import Context, Evidence, GateError, State
from .photography import CaptureBinding, CoverageProof, View
from .profiles import PROFILE_KINDS, ECUProfile, valid_quaternion, validate_profiles
from .workflow import CHECKS, _canonical

MAX_VIEWS = 128
MAX_FOOTPRINTS = 128
MAX_PCB_REGIONS = 128
MAX_GRID_CELLS = 100_000
MAX_COORDINATE_MM = 1_000_000.0


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def _number(value):
    try:
        return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _fresh(timestamp, now, max_age):
    return all(_number(v) for v in (timestamp, now, max_age)) and max_age > 0 and 0 <= now - timestamp <= max_age


def _rect(rect):
    if not isinstance(rect, (tuple, list)) or len(rect) != 4 or not all(_number(x) for x in rect) or rect[2] <= 0 or rect[3] <= 0:
        raise GateError('invalid rectangle (x, y, width, height)')
    x, y, w, h = map(float, rect)
    if (not all(math.isfinite(v) for v in (x + w, y + h, w * h))
            or max(abs(x), abs(y), abs(x + w), abs(y + h)) > MAX_COORDINATE_MM
            or x + w <= x or y + h <= y or w * h <= 0):
        raise GateError('rectangle overflow')
    return (x, y, x + w, y + h)


@dataclass(frozen=True)
class ObservedECU:
    frame_id: str
    position_mm: tuple[float, float, float]
    yaw_rad: float
    timestamp: float
    scene_revision: str
    ecu_revision: str
    declared_type: str
    variant: str
    reference: str


@dataclass(frozen=True)
class InspectionTarget:
    view_id: str
    local_xyz_mm: tuple[float, float, float]
    scene_xyz_mm: tuple[float, float, float]
    local_quaternion: tuple[float, float, float, float]
    scene_quaternion: tuple[float, float, float, float]


@dataclass(frozen=True)
class InspectionPlan:
    schema_version: str
    context: Context
    observation: ObservedECU
    profile_metadata: tuple[tuple, ...]
    targets: tuple[InspectionTarget, ...]
    pcb_regions_mm: tuple[tuple[float, float, float, float], ...]
    require_raw: bool
    min_coverage: float
    digest: str


def _plan_document(plan):
    return {'schema_version': plan.schema_version, 'context': plan.context.to_dict(),
            'observation': asdict(plan.observation), 'profile_metadata': plan.profile_metadata, 'targets': [asdict(t) for t in plan.targets],
            'pcb_regions_mm': plan.pcb_regions_mm, 'require_raw': plan.require_raw,
            'min_coverage': plan.min_coverage, 'local_frame': 'ecu_local', 'units': 'mm', 'yaw_units': 'rad'}


def create_plan(context: Context, profiles: Mapping, calibrations: Mapping, requirements: Mapping,
                observation: ObservedECU, now: float, max_age: float, *, min_coverage: float,
                require_raw: bool, extra_kinds=()) -> InspectionPlan:
    ecu = profiles.get('ecu')
    if isinstance(ecu, ECUProfile) and (not isinstance(ecu.view_targets, (tuple, list))
            or not isinstance(ecu.view_quaternions_xyzw, (tuple, list))
            or not isinstance(ecu.pcb_regions, (tuple, list))
            or len(ecu.view_targets) > MAX_VIEWS or len(ecu.pcb_regions) > MAX_PCB_REGIONS):
        raise GateError('plan geometry exceeds limits')
    if isinstance(ecu, ECUProfile) and (not ecu.view_quaternions_xyzw
            or len(ecu.view_quaternions_xyzw) != len(ecu.view_targets)
            or not all(valid_quaternion(q) for q in ecu.view_quaternions_xyzw)):
        raise GateError('NOT_READY: missing or invalid photography orientation')
    expected_kinds = PROFILE_KINDS | frozenset(extra_kinds)
    errors = validate_profiles(profiles, calibrations, requirements, extra_kinds=extra_kinds)
    if errors:
        raise GateError('; '.join(errors))
    ecu = profiles['ecu']
    if (not isinstance(ecu, ECUProfile) or not context.session_id or not context.scene_revision or not context.frame_id
            or set(context.profile_revisions) != expected_kinds
            or any(context.profile_revisions[k] != profiles[k].revision for k in expected_kinds)
            or observation.frame_id != context.frame_id or observation.scene_revision != context.scene_revision
            or observation.timestamp != context.observation_timestamp or observation.ecu_revision != ecu.revision
            or observation.declared_type != ecu.declared_type or observation.variant != ecu.variant
            or not observation.reference or not _fresh(observation.timestamp, now, max_age)
            or len(observation.position_mm) != 3 or not all(_number(x) for x in observation.position_mm)
            or not _number(observation.yaw_rad) or not _number(min_coverage) or not 0 < min_coverage <= 1
            or type(require_raw) is not bool or (require_raw and 'raw' not in profiles['capture'].capabilities)):
        raise GateError('invalid or stale plan context, observation, or requirements')
    for region in ecu.pcb_regions:
        _rect(region)
    x, y, z = observation.position_mm
    c, s = math.cos(observation.yaw_rad), math.sin(observation.yaw_rad)
    targets = []
    for i, local in enumerate(ecu.view_targets, 1):
        a, b, h = map(float, local)
        world = (float(x + c*a - s*b), float(y + s*a + c*b), float(z + h))
        if not all(math.isfinite(v) for v in world):
            raise GateError('target transform overflow')
        qx, qy, qz, qw = ecu.view_quaternions_xyzw[i - 1]
        sh, ch = math.sin(observation.yaw_rad / 2), math.cos(observation.yaw_rad / 2)
        scene_q = (ch*qx - sh*qy, ch*qy + sh*qx, ch*qz + sh*qw, ch*qw - sh*qz)
        norm = math.hypot(*scene_q)
        scene_q = tuple(v / norm for v in scene_q)
        targets.append(InspectionTarget(f'view_{i:03d}', (a, b, h), world,
                                        tuple(ecu.view_quaternions_xyzw[i - 1]), scene_q))
    observation = ObservedECU(observation.frame_id, tuple(map(float, observation.position_mm)), float(observation.yaw_rad),
                              float(observation.timestamp), observation.scene_revision, observation.ecu_revision,
                              observation.declared_type, observation.variant, observation.reference)
    metadata = tuple((k, profiles[k].identifier, profiles[k].schema_version, profiles[k].revision,
                      tuple(sorted(profiles[k].capabilities)), tuple(sorted(profiles[k].required_capabilities)),
                      tuple(sorted(profiles[k].calibration_dependencies.items())),
                      tuple(sorted(requirements.get(k, ())))) for k in sorted(expected_kinds))
    metadata += (('ecu_geometry', ecu.declared_type, ecu.variant, ecu.nominal_dimensions, ecu.max_height,
                  ecu.pcb_regions, ecu.view_targets, ecu.tolerances, ecu.view_quaternions_xyzw),)
    if extra_kinds:
        metadata += (('extra_profiles', _canonical({k: profiles[k] for k in sorted(extra_kinds)})),)
    plan = InspectionPlan('1', context, observation, metadata, tuple(targets), tuple(tuple(map(float, r)) for r in ecu.pcb_regions), require_raw, float(min_coverage), '')
    return InspectionPlan(**{**plan.__dict__, 'digest': _hash(_plan_document(plan))})


def verify_plan(plan: InspectionPlan, context: Context, profiles: Mapping, calibrations: Mapping,
                requirements: Mapping, now: float, max_age: float, *, extra_kinds=()) -> None:
    expected = create_plan(context, profiles, calibrations, requirements, plan.observation, now, max_age,
                           min_coverage=plan.min_coverage, require_raw=plan.require_raw, extra_kinds=extra_kinds)
    if plan != expected or plan.digest != _hash(_plan_document(plan)):
        raise GateError('plan or current context mismatch')


def photography_views(plan: InspectionPlan, context, profiles, calibrations, requirements, now, max_age, *, extra_kinds=()):
    verify_plan(plan, context, profiles, calibrations, requirements, now, max_age, extra_kinds=extra_kinds)
    return tuple(View(t.view_id, t.local_xyz_mm, plan.require_raw, t.local_quaternion) for t in plan.targets)


def complete_s05(workflow, plan: InspectionPlan):
    verify_plan(plan, workflow.context, workflow.profiles, workflow.calibrations, workflow.requirements, workflow.clock(), workflow.max_age, extra_kinds=workflow.extra_kinds)
    if workflow.states['S05'] != State.RUNNING:
        raise GateError('S05 is not running')
    workflow.complete(Evidence(workflow.context.session_id, 'S05', workflow.requests['S05'], workflow.context,
                               workflow.clock(), True, True, frozenset(CHECKS['S05']), 'inspection-plan:sha256:' + plan.digest, plan.digest), _verified_plan=plan)


@dataclass(frozen=True)
class SpatialFootprint:
    view_id: str
    rectangle_mm: tuple[float, float, float, float]
    verified: bool


@dataclass(frozen=True)
class SpatialCoverageEvidence:
    session_id: str
    plan_hash: str
    scene_revision: str
    profile_revisions: Mapping[str, str]
    timestamp: float
    captured_view_ids: frozenset[str]
    footprints: tuple[SpatialFootprint, ...]
    frame_id: str
    provenance_reference: str
    verified: bool
    capture_bindings: tuple[CaptureBinding, ...] = ()


def _areas(regions, footprints):
    if (not isinstance(regions, (tuple, list)) or not isinstance(footprints, (tuple, list))
            or len(regions) > MAX_PCB_REGIONS or len(footprints) > MAX_FOOTPRINTS):
        raise GateError('coverage geometry exceeds limits')
    # Coordinate compression computes the union of required regions and its
    # intersection with measured footprints, even when either set overlaps.
    xs = sorted({v for r in regions + footprints for v in (r[0], r[2])})
    ys = sorted({v for r in regions + footprints for v in (r[1], r[3])})
    if (len(xs) - 1) * (len(ys) - 1) > MAX_GRID_CELLS:
        raise GateError('coverage grid exceeds limit')
    total = covered = 0.0
    for x1, x2 in zip(xs, xs[1:]):
        for y1, y2 in zip(ys, ys[1:]):
            inside = lambda r: r[0] <= x1 and x2 <= r[2] and r[1] <= y1 and y2 <= r[3]
            if any(map(inside, regions)):
                area = (x2-x1)*(y2-y1)
                total += area
                if any(map(inside, footprints)):
                    covered += area
    if not math.isfinite(total) or not math.isfinite(covered) or total <= 0:
        raise GateError('invalid coverage area')
    return total, covered


def coverage_proof(plan: InspectionPlan, evidence: SpatialCoverageEvidence, request_id: str,
                   context, profiles, calibrations, requirements, now, max_age, *, extra_kinds=()):
    if (not isinstance(evidence.footprints, (tuple, list))
            or len(evidence.footprints) > MAX_FOOTPRINTS
            or any(not isinstance(f, SpatialFootprint) for f in evidence.footprints)):
        raise GateError('invalid or excessive footprints')
    verify_plan(plan, context, profiles, calibrations, requirements, now, max_age, extra_kinds=extra_kinds)
    ids = frozenset(t.view_id for t in plan.targets)
    if (not request_id or evidence.session_id != context.session_id or evidence.plan_hash != plan.digest
            or evidence.scene_revision != context.scene_revision or dict(evidence.profile_revisions) != dict(context.profile_revisions)
            or evidence.frame_id != 'ecu_local' or not evidence.provenance_reference or evidence.verified is not True
            or not _fresh(evidence.timestamp, now, max_age) or evidence.timestamp < plan.observation.timestamp
            or evidence.captured_view_ids != ids or not evidence.footprints
            or not isinstance(evidence.capture_bindings, tuple)
            or any(not isinstance(b, CaptureBinding) or not isinstance(b.sha256, str) or len(b.sha256) != 64 or any(c not in '0123456789abcdef' for c in b.sha256) for b in evidence.capture_bindings)
            or len(evidence.capture_bindings) != len(ids) or {b.view_id for b in evidence.capture_bindings} != ids
            or tuple(sorted(evidence.capture_bindings)) != evidence.capture_bindings
            or any(f.verified is not True or f.view_id not in ids for f in evidence.footprints)
            or {f.view_id for f in evidence.footprints} != ids):
        raise GateError('NOT_READY: invalid measured spatial evidence')
    total, covered = _areas([_rect(r) for r in plan.pcb_regions_mm], [_rect(f.rectangle_mm) for f in evidence.footprints])
    fraction = covered / total
    if fraction < plan.min_coverage:
        raise GateError('NOT_READY: insufficient measured coverage')
    return CoverageProof(context, request_id, ids, evidence.timestamp, True,
                         evidence.provenance_reference + ':sha256:' + _hash(_coverage_document(evidence)), plan.digest, evidence.capture_bindings), fraction


def _coverage_document(e):
    return {'session_id': e.session_id, 'plan_hash': e.plan_hash, 'scene_revision': e.scene_revision,
            'profile_revisions': dict(e.profile_revisions), 'timestamp': e.timestamp,
            'captured_view_ids': sorted(e.captured_view_ids), 'footprints': [asdict(f) for f in e.footprints],
            'frame_id': e.frame_id, 'provenance_reference': e.provenance_reference, 'verified': e.verified,
            'capture_bindings': [asdict(b) for b in e.capture_bindings]}


class RetryLedger:
    """Decision journal only; no stage transition, motion or shutter dispatch."""
    def __init__(self, journal):
        self.journal = journal

    def decisions(self, session_id):
        return [e.data for e in self.journal.replay(session_id) if e.kind == 'recapture_decision']

    def decide(self, plan, context, profiles, calibrations, requirements, now, max_age, *, view_id,
               attempt, request_id, failure, approved, approval_reference, qa_reference, qa_verified,
               coverage_evidence, max_attempts, extra_kinds=()):
        verify_plan(plan, context, profiles, calibrations, requirements, now, max_age, extra_kinds=extra_kinds)
        if (view_id not in {t.view_id for t in plan.targets} or not isinstance(attempt, int) or isinstance(attempt, bool)
                or not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1
                or attempt < 1 or not isinstance(request_id, str) or not request_id.strip()):
            raise GateError('invalid retry identity or bound')
        coverage_proof(plan, coverage_evidence, request_id, context, profiles, calibrations, requirements, now, max_age, extra_kinds=extra_kinds)
        record = {'session_id': context.session_id, 'plan_hash': plan.digest, 'view_id': view_id,
                  'attempt': attempt, 'request_id': request_id, 'failure': failure, 'approved': approved,
                  'approval_reference': approval_reference, 'qa_reference': qa_reference, 'qa_verified': qa_verified,
                  'coverage_hash': _hash(_coverage_document(coverage_evidence)), 'max_attempts': max_attempts}
        db = self.journal.db
        try:
            db.execute('BEGIN IMMEDIATE')
            prior = self.decisions(context.session_id)
            rows = db.execute('SELECT session_id, kind, data FROM events WHERE request_id=?', (request_id,)).fetchall()
            if any(session != context.session_id or kind != 'recapture_decision' or json.loads(data) != record
                   for session, kind, data in rows):
                raise GateError('request ID reused with changed context')
            for old in prior:
                if old['request_id'] == request_id:
                    db.commit()
                    return old
                if (old['plan_hash'], old['view_id'], old['attempt']) == (plan.digest, view_id, attempt):
                    raise GateError('attempt already decided')
            previous = [d for d in prior if d['plan_hash'] == plan.digest and d['view_id'] == view_id]
            if attempt != len(previous) + 1 or attempt > max_attempts or (previous and any(d['max_attempts'] != max_attempts for d in previous)):
                raise GateError('nonmonotonic or exhausted attempts')
            if (failure not in {'blur', 'exposure', 'crop'} or approved is not True or not approval_reference
                    or not qa_reference or qa_verified is not True):
                raise GateError('recapture requires approved verified QA failure and coverage')
            db.execute('INSERT INTO events(session_id,step_id,request_id,kind,data,timestamp) VALUES (?,?,?,?,?,?)',
                       (context.session_id, 'S08', request_id, 'recapture_decision', _json(record), now))
            db.commit()
            return record
        except Exception:
            db.rollback()
            raise


def make_manifest(plan, evidence, coverage_fraction, decisions):
    document = {'schema_version': '1', 'plan': _plan_document(plan), 'plan_hash': plan.digest,
                'coverage': _coverage_document(evidence), 'coverage_hash': _hash(_coverage_document(evidence)),
                'coverage_fraction': coverage_fraction, 'retry_decisions': list(decisions)}
    return _json({'document': document, 'sha256': _hash(document)})


def verify_manifest(serialized, plan, evidence, coverage_fraction, decisions):
    try:
        parsed = json.loads(serialized)
        if parsed != json.loads(make_manifest(plan, evidence, coverage_fraction, decisions)) or parsed['sha256'] != _hash(parsed['document']):
            raise GateError('manifest mismatch')
    except (ValueError, TypeError, KeyError) as exc:
        raise GateError('invalid or tampered manifest') from exc
