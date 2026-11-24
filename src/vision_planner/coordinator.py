"""S05–S06 orchestration over the existing Core, without motion execution.

The external verifier authenticates the entire preparation, robot/tool
configuration and scene lease. Digests bind data; they do not authenticate it.
The lease authority must freeze the relevant PlanningScene for the job's
duration. Matching two snapshots alone cannot establish that guarantee.
"""
from dataclasses import dataclass
import hashlib
import json
import math

from vision_core import Evidence, GateError, State
from vision_core.ports import Request
from vision_core.planning import PlanningProof, PreparationProof
from vision_core.workflow import CHECKS, _canonical
from vision_runtime.contracts import ObservationReceipt
from .preparation import PreparedInspection, prepare_plan, verify_prepared
from .moveit_adapter import (AdapterConfig, SceneSnapshot, SegmentResult,
                             validate_segment, validate_snapshot)

MAX_MOTION_POINTS = 8192
MAX_MOTION_SCALARS = 262_144
MAX_BINDING_BYTES = 8 * 1024 * 1024


def digest(value):
    serialized = json.dumps(_canonical(value), sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode()
    if len(serialized) > MAX_BINDING_BYTES:
        raise GateError('planning binding exceeds byte limit')
    return hashlib.sha256(serialized).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1024


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _ref(value):
    return isinstance(value, str) and value.startswith('sha256:') and _sha(value[7:])


@dataclass(frozen=True)
class MotionSetup:
    """Approved provenance for model bounds and the Sony optical-to-link pose.

    Values are supplied by station configuration, never inferred from Luxonis.
    ``environment`` describes the evidence, not an execution permission.
    """
    robot_profile_revision: str
    tool_profile_revision: str
    capture_profile_revision: str
    robot_model_calibration_id: str
    tool_calibration_id: str
    calibration_revision: str
    model_revision: str
    camera_configuration_ref: str
    config_hash: str
    source: str
    reference: str
    approved: bool
    environment: str
    stationary_position_tolerance_rad: float
    stationary_velocity_tolerance_rad_s: float

    def __post_init__(self):
        if (not all(_text(getattr(self, name)) for name in (
                'robot_profile_revision', 'tool_profile_revision', 'capture_profile_revision',
                'robot_model_calibration_id', 'tool_calibration_id', 'calibration_revision',
                'model_revision', 'camera_configuration_ref', 'source'))
                or not _sha(self.config_hash) or not _ref(self.reference)
                or type(self.approved) is not bool
                or self.environment not in ('simulation', 'station_plan_only')
                or any(not _number(v) or not 0 < v <= 0.1 for v in (
                    self.stationary_position_tolerance_rad,
                    self.stationary_velocity_tolerance_rad_s))):
            raise GateError('invalid motion setup')


@dataclass(frozen=True)
class SceneLease:
    """Externally authenticated ownership of one localized PlanningScene.

    ``reference`` identifies the authority's private evidence. The authority
    must prevent scene changes, including transient changes between snapshots.
    """
    request: Request
    preparation_hash: str
    scene_hash: str
    config_hash: str
    robot_model_name: str
    issued_at: float
    expires_at: float
    source: str
    reference: str

    def __post_init__(self):
        if (not isinstance(self.request, Request) or self.request.step_id != 'S06'
                or not all(_sha(v) for v in (self.preparation_hash, self.scene_hash, self.config_hash))
                or not all(_text(v) for v in (self.robot_model_name, self.source))
                or not _ref(self.reference) or not _number(self.issued_at)
                or not _number(self.expires_at) or self.issued_at < 0
                or self.expires_at <= self.issued_at):
            raise GateError('invalid scene lease')


@dataclass(frozen=True)
class PreparationBinding:
    request: Request
    preparation: PreparedInspection


@dataclass(frozen=True)
class SceneBinding:
    request: Request
    preparation_hash: str
    preparation: PreparedInspection
    observation: ObservationReceipt
    configuration: AdapterConfig
    setup: MotionSetup
    lease: SceneLease
    snapshot: SceneSnapshot


@dataclass(frozen=True)
class MotionPlan:
    request: Request
    inspection_plan_hash: str
    preparation_hash: str
    configuration: AdapterConfig
    setup: MotionSetup
    lease: SceneLease
    initial_scene: SceneSnapshot
    final_scene: SceneSnapshot
    segments: tuple[SegmentResult, ...]
    timestamp: float
    digest: str

    def __post_init__(self):
        object.__setattr__(self, 'segments', tuple(self.segments))


def _motion_document(plan):
    return {k: v for k, v in plan.__dict__.items() if k != 'digest'}


class InspectionPlanner:
    """One owner of planning calls, attached to a strict Runtime session.

    The supplied backend exposes snapshot and plan_segment only. No execute,
    controller, driver, camera shutter, or PARK call exists in this module.
    """
    def __init__(self, runtime, *, trust_verifier):
        if not callable(trust_verifier):
            raise GateError('independent planning verifier required')
        if getattr(runtime.engine, 'strict_planning', False) is not True:
            raise GateError('strict_planning must be enabled before S01')
        self.runtime = runtime
        self.engine = runtime.engine
        self.trust_verifier = trust_verifier
        self.prepared = None
        self.motion = None

    def _trust(self, kind, payload):
        before = digest(payload)
        accepted = self.trust_verifier(kind, payload)
        if digest(payload) != before:
            raise GateError('planning payload changed during independent verification: ' + kind)
        if accepted is not True:
            raise GateError('independent planning verification failed: ' + kind)

    def _start(self, stage, request):
        if (not isinstance(request, Request) or request.step_id != stage
                or request.context != self.engine.context):
            raise GateError('correlated planning request required')
        self.engine.start(stage, request.request_id)

    def _failed(self, stage, exc):
        if self.engine.states[stage] == State.RUNNING:
            self.engine.stop(stage, State.FAILED, str(exc) or 'planning failed')

    def prepare(self, request, *, camera_calibration, policy):
        self._start('S05', request)
        try:
            prepared = prepare_plan(self.runtime, camera_calibration=camera_calibration, policy=policy)
            self._trust('preparation', PreparationBinding(request, prepared))
            verify_prepared(prepared, self.runtime)
            stamp = self.engine.clock()
            proof = PreparationProof(self.engine.context, request.request_id,
                                     prepared.core_plan.digest, prepared.digest, stamp,
                                     'inspection-preparation:sha256:' + prepared.digest)
            self.engine.complete(Evidence(self.engine.context.session_id, 'S05', request.request_id,
                self.engine.context, stamp, True, True, frozenset(CHECKS['S05']),
                proof.reference, prepared.core_plan.digest),
                _verified_plan=prepared.core_plan, _verified_preparation=proof)
            self.prepared = prepared
            return prepared
        except Exception as exc:
            self._failed('S05', exc)
            if isinstance(exc, ValueError) and not isinstance(exc, GateError):
                raise GateError(str(exc)) from exc
            raise

    def _setup(self, config, setup):
        engine, prepared = self.engine, self.prepared
        if not isinstance(config, AdapterConfig) or not isinstance(setup, MotionSetup):
            raise GateError('typed motion configuration required')
        if (setup.approved is not True or setup.source == self.runtime.declaration.operator_id
                or setup.config_hash != config.digest
                or setup.robot_profile_revision != engine.profiles['robot'].revision
                or setup.tool_profile_revision != engine.profiles['tool'].revision
                or setup.capture_profile_revision != engine.profiles['capture'].revision
                or setup.model_revision != config.model_revision
                or setup.calibration_revision != config.calibration_revision
                or setup.camera_configuration_ref != prepared.camera_calibration.configuration_ref
                or engine.calibrations.get(setup.robot_model_calibration_id) != setup.model_revision
                or engine.profiles['robot'].calibration_dependencies.get(setup.robot_model_calibration_id) != setup.model_revision
                or engine.calibrations.get(setup.tool_calibration_id) != setup.calibration_revision
                or engine.profiles['tool'].calibration_dependencies.get(setup.tool_calibration_id) != setup.calibration_revision):
            raise GateError('motion setup does not match pinned robot/tool/camera configuration')

    def _snapshot(self, snapshot, config, *, initial=None):
        validate_snapshot(snapshot, config)
        if (not isinstance(snapshot, SceneSnapshot) or not _sha(snapshot.scene_hash)
                or not _text(snapshot.robot_model_name) or not _text(snapshot.reference)
                or snapshot.joint_names != tuple(l.name for l in config.joint_limits)
                or len(snapshot.joint_positions) != len(config.joint_limits)
                or len(snapshot.joint_velocities) != len(config.joint_limits)
                or not _number(snapshot.timestamp)
                or not 0 <= self.engine.clock() - snapshot.timestamp <= min(self.engine.max_age, config.max_state_age_s)
                or not _number(snapshot.received_at)
                or not self.engine.dispatch_times['S06'] <= snapshot.received_at <= self.engine.clock()):
            raise GateError('invalid, stale or pre-dispatch PlanningScene snapshot')
        for limit, position, velocity in zip(config.joint_limits, snapshot.joint_positions, snapshot.joint_velocities):
            if (not _number(position) or not limit.lower <= position <= limit.upper
                    or not _number(velocity) or abs(velocity) > self._current_setup.stationary_velocity_tolerance_rad_s):
                raise GateError('robot is not a stationary, bounded planning seed')
        if initial is not None:
            if (snapshot.scene_hash != initial.scene_hash
                    or snapshot.robot_model_name != initial.robot_model_name
                    or snapshot.timestamp < initial.timestamp
                    or snapshot.received_at < initial.received_at
                    or any(abs(a-b) > self._current_setup.stationary_position_tolerance_rad
                           for a, b in zip(snapshot.joint_positions, initial.joint_positions))):
                raise GateError('PlanningScene or live robot state changed during planning')

    def _lease(self, lease, request, snapshot, config, setup):
        if (not isinstance(lease, SceneLease) or lease.request != request
                or lease.preparation_hash != self.prepared.digest
                or lease.scene_hash != snapshot.scene_hash or lease.config_hash != config.digest
                or lease.robot_model_name != snapshot.robot_model_name
                or lease.source == self.runtime.declaration.operator_id
                or lease.issued_at < self.engine.dispatch_times['S06']
                or not lease.issued_at <= self.engine.clock() < lease.expires_at):
            raise GateError('missing, expired or unrelated frozen-scene lease')
        self._trust('scene_lease', SceneBinding(request, self.prepared.digest,
            self.prepared, self.runtime._observation, config, setup, lease, snapshot))
        if not lease.issued_at <= self.engine.clock() < lease.expires_at:
            raise GateError('frozen-scene lease expired during independent verification')

    def plan_motion(self, request, *, backend, setup, scene_lease_factory):
        """Plan required views sequentially; failure never dispatches execution.

        The lease factory is called after the fresh initial snapshot. It must
        obtain a real lease from the scene owner (synthetic authority in tests).
        Releasing a lease belongs to that owner; this method grants no control.
        """
        self._start('S06', request)
        try:
            if (self.prepared is None or self.prepared.digest != self.engine.accepted_preparation_hash
                    or self.prepared.core_plan.digest != self.engine.accepted_plan_hash):
                raise GateError('accepted S05 preparation must be available unchanged')
            verify_prepared(self.prepared, self.runtime)
            config = backend.config
            self._setup(config, setup)
            self._current_setup = setup
            self._trust('motion_setup', (request, self.prepared, config, setup))
            initial = backend.snapshot()
            self._snapshot(initial, config)
            if not callable(scene_lease_factory):
                raise GateError('scene ownership authority required')
            lease = scene_lease_factory(request, self.prepared, config, initial)
            self._lease(lease, request, initial, config, setup)
            start = initial.joint_positions
            segments = []
            total_points = total_scalars = 0
            for target in self.prepared.core_plan.targets:
                self._lease(lease, request, initial, config, setup)
                if backend.config != config:
                    raise GateError('adapter configuration changed')
                segment = backend.plan_segment(target.view_id, self.engine.context.frame_id,
                    target.scene_xyz_mm, target.scene_quaternion, start, initial.scene_hash)
                validate_segment(segment, config)
                if (segment.view_id != target.view_id or segment.frame_id != self.engine.context.frame_id
                        or segment.camera_xyz_mm != target.scene_xyz_mm
                        or segment.camera_quaternion != target.scene_quaternion
                        or segment.requested_start_joints != start
                        or segment.config_hash != config.digest
                        or segment.started_at < self.engine.dispatch_times['S06']
                        or not segment.started_at <= segment.completed_at <= self.engine.clock()
                        or (segments and segment.started_at < segments[-1].completed_at)):
                    raise GateError('motion segment does not match requested view, seed or time')
                self._snapshot(segment.scene_before, config, initial=initial)
                self._snapshot(segment.scene_after, config, initial=initial)
                total_points += len(segment.points)
                total_scalars += sum(1 + len(p.positions) + len(p.velocities) + len(p.accelerations)
                                     for p in segment.points)
                if total_points > MAX_MOTION_POINTS or total_scalars > MAX_MOTION_SCALARS:
                    raise GateError('aggregate motion plan exceeds resource limits')
                segments.append(segment)
                start = segment.end_joints
            final = backend.snapshot()
            self._snapshot(final, config, initial=initial)
            self._lease(lease, request, final, config, setup)
            if (backend.config != config or not segments
                    or final.received_at < segments[-1].completed_at):
                raise GateError('planning ended without a current matching final snapshot')
            verify_prepared(self.prepared, self.runtime)
            plan = MotionPlan(request, self.prepared.core_plan.digest, self.prepared.digest,
                              config, setup, lease, initial, final, tuple(segments), self.engine.clock(), '')
            plan = MotionPlan(**{**plan.__dict__, 'digest': digest(_motion_document(plan))})
            self._trust('motion_binding', plan)
            # The verifier is external; recheck freshness and pins after it returns.
            verify_prepared(self.prepared, self.runtime)
            self._lease(lease, request, final, config, setup)
            self._setup(backend.config, setup)
            self._snapshot(final, config, initial=initial)
            if digest(_motion_document(plan)) != plan.digest:
                raise GateError('motion result changed during independent verification')
            proof = PlanningProof(self.engine.context, request.request_id,
                plan.inspection_plan_hash, plan.preparation_hash, plan.digest,
                plan.timestamp, 'motion-plan:sha256:' + plan.digest)
            self.engine.complete(Evidence(self.engine.context.session_id, 'S06', request.request_id,
                self.engine.context, plan.timestamp, True, True, frozenset(CHECKS['S06']),
                proof.reference, plan.inspection_plan_hash), _verified_motion=proof)
            self.motion = plan
            return plan
        except Exception as exc:
            self._failed('S06', exc)
            if isinstance(exc, ValueError) and not isinstance(exc, GateError):
                raise GateError(str(exc)) from exc
            raise
