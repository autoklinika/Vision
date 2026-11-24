"""S05 preparation using approved recipes and explicit capture calibration.

This module calculates predicted optical coverage only. An external verifier
must authenticate the complete PreparedInspection before the coordinator
accepts S05; approved flags and hashes do not authenticate their own contents.
"""
from dataclasses import dataclass, fields
import hashlib
import json
import math
import re

from vision_core.models import GateError, State
from vision_core.repeatability import ObservedECU, create_plan, _areas, _rect
from vision_core.workflow import _canonical
from .geometry import (finite_number, vector, footprint_polygon,
                       inscribed_rectangle, project_point, image_contains)


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value):
        raise GateError('nonempty bounded identifier required')


def _reference(value):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise GateError('SHA-256 provenance reference required')


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise GateError('SHA-256 snapshot digest required')


def _digest(value):
    return hashlib.sha256(json.dumps(_canonical(value), sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, kw_only=True)
class CameraCalibration:
    calibration_id: str
    revision: str
    capture_profile_revision: str
    configuration_ref: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    usable_image_xywh_px: tuple[float, float, float, float]
    rectified: bool
    approved: bool
    source: str
    reference: str

    def __post_init__(self):
        for item in (self.calibration_id, self.revision, self.capture_profile_revision, self.source):
            _identifier(item)
        _reference(self.configuration_ref); _reference(self.reference)
        if (type(self.width) is not int or type(self.height) is not int
                or not 1 <= self.width <= 16384 or not 1 <= self.height <= 16384
                or self.width*self.height > 134_217_728):
            raise GateError('invalid capture image dimensions')
        if (not all(finite_number(v) for v in (self.fx, self.fy, self.cx, self.cy))
                or not 1e-9 < self.fx <= 1e9 or not 1e-9 < self.fy <= 1e9
                or not 0 <= self.cx <= self.width or not 0 <= self.cy <= self.height):
            raise GateError('invalid calibrated capture intrinsics')
        rectangle = vector(self.usable_image_xywh_px, 4)
        x, y, width, height = rectangle
        if min(x, y) < 0 or min(width, height) <= 0 or x+width > self.width or y+height > self.height:
            raise GateError('useful image rectangle must be inside capture image')
        object.__setattr__(self, 'usable_image_xywh_px', rectangle)
        if type(self.rectified) is not bool or type(self.approved) is not bool:
            raise GateError('explicit rectification and approval states required')


@dataclass(frozen=True, kw_only=True)
class PlanningPolicy:
    policy_id: str
    revision: str
    approved: bool
    source: str
    reference: str
    qa_policy_refs: tuple[str, ...]
    capture_configuration_ref: str
    physical_state: str
    recipe: str
    reference_sha256: str
    pcb_plane_z_mm: float
    plane_reference: str
    min_coverage: float
    require_raw: bool
    require_each_view_roi: bool

    def __post_init__(self):
        for item in (self.policy_id, self.revision, self.source, self.physical_state, self.recipe):
            _identifier(item)
        for item in (self.reference, self.capture_configuration_ref, self.plane_reference):
            _reference(item)
        _sha(self.reference_sha256)
        if (not isinstance(self.qa_policy_refs, (tuple, list)) or not 0 < len(self.qa_policy_refs) <= 128
                or len(set(self.qa_policy_refs)) != len(self.qa_policy_refs)):
            raise GateError('unique QA policy references required')
        for item in self.qa_policy_refs:
            _identifier(item)
        object.__setattr__(self, 'qa_policy_refs', tuple(sorted(self.qa_policy_refs)))
        if (not finite_number(self.pcb_plane_z_mm) or abs(self.pcb_plane_z_mm) > 1_000_000
                or not finite_number(self.min_coverage) or not 0 < self.min_coverage <= 1):
            raise GateError('explicit valid PCB plane and coverage threshold required')
        if any(type(v) is not bool for v in (self.approved, self.require_raw, self.require_each_view_roi)):
            raise GateError('explicit planning policy flags required')


@dataclass(frozen=True)
class ViewBinding:
    view_id: str
    reference_view_id: str
    roi_ids: tuple[str, ...]
    aim_point_mm: tuple[float, float, float]
    working_distance_mm: float
    quality_policy_ref: str


@dataclass(frozen=True)
class PredictedFootprint:
    view_id: str
    rectangle_xywh_mm: tuple[float, float, float, float]
    polygon_xy_mm: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ViewCoverage:
    view_id: str
    fraction: float
    roi_fractions: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class PreparedInspection:
    core_plan: object
    camera_calibration: CameraCalibration
    policy: PlanningPolicy
    view_bindings: tuple[ViewBinding, ...]
    footprints: tuple[PredictedFootprint, ...]
    coverage_fraction: float
    per_view_coverage: tuple[ViewCoverage, ...]
    record_sha256: str
    reference_sha256: str
    observation_reference: str
    prepared_at: float
    digest: str


def preparation_document(prepared):
    return {f.name: getattr(prepared, f.name) for f in fields(prepared) if f.name != 'digest'}


def _context(runtime, now):
    engine = runtime.engine
    engine._require_usable()
    if not all(engine.states[f'S{i:02d}'] == State.SUCCEEDED for i in range(1, 5)):
        raise GateError('S05 requires accepted S01–S04')
    if engine.config_pin != engine._pin():
        raise GateError('pinned Core configuration changed')
    if dict(engine.calibrations) != dict(runtime.calibrations):
        raise GateError('Runtime and Core calibrations differ')
    runtime._selection_check()
    if runtime._compile() != runtime.bundle or engine.profiles['ecu'] != runtime.bundle.core_profile:
        raise GateError('compiled ECU recipe changed')
    receipt = runtime._observation
    if receipt is None:
        raise GateError('accepted Runtime observation must be rehydrated before planning')
    runtime._validate_observation(receipt)
    context = engine.context
    if (receipt.session_id != context.session_id or receipt.profile_revisions != context.profile_revisions
            or receipt.frame_id != context.frame_id or receipt.scene_revision != context.scene_revision
            or receipt.rgb.timestamp != context.observation_timestamp):
        raise GateError('accepted observation and Core context differ')
    observation_ref = runtime._ref(receipt)
    history = engine.journal.replay(context.session_id)
    for step, kind in (('S03', 'localization_accepted'), ('S04', 'result_accepted')):
        accepted = [e for e in history if e.step_id == step and e.kind == kind]
        if len(accepted) != 1 or accepted[0].data['evidence']['reference'] != observation_ref:
            raise GateError('observation differs from accepted Runtime evidence')
    if (not finite_number(now) or not finite_number(context.observation_timestamp)
            or not 0 <= now-context.observation_timestamp <= engine.max_age):
        raise GateError('stale or invalid planning observation')
    qx, qy, qz, qw = receipt.quaternion_xyzw
    if math.hypot(qx, qy) > 1e-6:
        raise GateError('V1 Core supports yaw-only ECU pose; roll/pitch requires a full-pose contract')
    return ObservedECU(context.frame_id, receipt.position_mm, 2*math.atan2(qz, qw),
        context.observation_timestamp, context.scene_revision, runtime.record.revision,
        runtime.record.family, runtime.record.variant, observation_ref)


def _prepare(runtime, camera_calibration, policy, now, prepared_at):
    if not isinstance(camera_calibration, CameraCalibration) or not isinstance(policy, PlanningPolicy):
        raise GateError('typed capture calibration and planning policy required')
    engine = runtime.engine
    observation = _context(runtime, now)
    capture = engine.profiles['capture']
    c = camera_calibration
    if (c.approved is not True or c.rectified is not True
            or c.capture_profile_revision != capture.revision
            or engine.calibrations.get(c.calibration_id) != c.revision
            or capture.calibration_dependencies.get(c.calibration_id) != c.revision
            or c.source == runtime.declaration.operator_id):
        raise GateError('NOT_READY: approved calibrated rectified capture configuration required')
    if (policy.approved is not True or policy.source == runtime.declaration.operator_id
            or policy.capture_configuration_ref != c.configuration_ref
            or policy.physical_state != runtime.physical_state or policy.recipe != runtime.recipe
            or policy.reference_sha256 != runtime.bundle.reference_sha256
            or policy.qa_policy_refs != tuple(sorted(runtime.bundle.qa_policy_refs))):
        raise GateError('NOT_READY: planning policy does not match the approved selected recipe')
    if not finite_number(prepared_at) or not 0 <= now-prepared_at <= engine.max_age:
        raise GateError('stale or future S05 preparation')
    plan = create_plan(engine.context, engine.profiles, engine.calibrations,
        engine.requirements, observation, now, engine.max_age,
        min_coverage=policy.min_coverage, require_raw=policy.require_raw,
        extra_kinds=engine.extra_kinds)
    data = runtime.reference_profile.data
    recipes = [r for r in data['photography_recipes']['recipes']
               if r['state_id'] == runtime.physical_state and r['recipe_id'] == runtime.recipe]
    if len(recipes) != 1:
        raise GateError('exactly one selected photography recipe required')
    recipes_by_view = {v['view_id']: v for v in recipes[0]['views']}
    rois = {r['roi_id']: r for r in data['pcb_definition']['regions_of_interest']}
    if len(runtime.record.views) != len(plan.targets):
        raise GateError('approved record view count differs from Core plan')
    bindings, footprints, view_coverage = [], [], []
    for record_view, target in zip(runtime.record.views, plan.targets):
        view = recipes_by_view.get(record_view.view_id)
        if view is None:
            raise GateError('required record view missing from selected photography recipe')
        goal = view['camera_goal']
        if (tuple(goal['translation_mm']) != target.local_xyz_mm
                or tuple(goal['quaternion_xyzw']) != target.local_quaternion):
            raise GateError('Core/record/reference view order or optical goal mismatch')
        aim = tuple(view['aim_point_mm'])
        if abs(aim[2]-policy.pcb_plane_z_mm) > 1e-6:
            raise GateError('view aim point is outside the explicitly calibrated PCB plane')
        distance = math.dist(target.local_xyz_mm, aim)
        near, far = view['working_distance_range_mm']
        if not near <= distance <= far:
            raise GateError('approved view violates its working-distance interval')
        if not image_contains(project_point(target.local_xyz_mm, target.local_quaternion, aim, c),
                              c.usable_image_xywh_px):
            raise GateError('approved aim point is outside useful capture image')
        polygon = footprint_polygon(target.local_xyz_mm, target.local_quaternion, c, policy.pcb_plane_z_mm)
        rectangle = inscribed_rectangle(polygon)
        selected_rois = [rois[r] for r in view['roi_refs']]
        if any(r['state_id'] != runtime.physical_state or r['verified'] is not True for r in selected_rois):
            raise GateError('required view ROI belongs to a different or unverified physical state')
        fractions = []
        for roi in selected_rois:
            total, covered = _areas([_rect(roi['rectangle_xywh_mm'])], [_rect(rectangle)])
            fractions.append((roi['roi_id'], min(1.0, covered/total)))
        total, covered = _areas([_rect(r['rectangle_xywh_mm']) for r in selected_rois], [_rect(rectangle)])
        fraction = min(1.0, covered/total)
        if policy.require_each_view_roi and any(f < policy.min_coverage for _, f in fractions):
            raise GateError('NOT_READY: required view does not conservatively cover every assigned ROI')
        bindings.append(ViewBinding(target.view_id, record_view.view_id, tuple(view['roi_refs']),
            aim, distance, view['quality_policy_ref']))
        footprints.append(PredictedFootprint(target.view_id, rectangle, polygon))
        view_coverage.append(ViewCoverage(target.view_id, fraction, tuple(fractions)))
    total, covered = _areas([_rect(r) for r in plan.pcb_regions_mm],
                            [_rect(f.rectangle_xywh_mm) for f in footprints])
    fraction = min(1.0, covered/total)
    if fraction < policy.min_coverage:
        raise GateError('NOT_READY: insufficient conservative predicted PCB coverage')
    result = PreparedInspection(plan, c, policy, tuple(bindings), tuple(footprints), fraction,
        tuple(view_coverage), runtime.bundle.record_sha256, runtime.bundle.reference_sha256,
        observation.reference, prepared_at, '')
    return PreparedInspection(**{**result.__dict__, 'digest': _digest(preparation_document(result))})


def prepare_plan(runtime, *, camera_calibration, policy, now=None):
    """Prepare every approved view; no stage transition, optimizer, or dispatch.

    Calibration must describe the capture camera/lens configuration, not the
    Luxonis localization image. The explicit PCB plane and numerical QA policy
    require provenance verification by the caller before S05 can be accepted.
    Required views stay in the approved record order; none is discarded merely
    because another view overlaps it.
    """
    when = runtime.clock() if now is None else now
    return _prepare(runtime, camera_calibration, policy, when, when)


def verify_prepared(prepared, runtime, *, now=None):
    """Rebuild against live selection, calibration, scene and observation state."""
    if not isinstance(prepared, PreparedInspection):
        raise GateError('typed S05 preparation required')
    when = runtime.clock() if now is None else now
    expected = _prepare(runtime, prepared.camera_calibration, prepared.policy, when, prepared.prepared_at)
    if prepared != expected or prepared.digest != _digest(preparation_document(prepared)):
        raise GateError('S05 preparation content or bound inputs changed')
