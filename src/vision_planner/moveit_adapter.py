"""Optional ROS 2 / MoveIt service adapter. This module cannot execute motion.

The caller owns the node, its executor, scene ownership and authentication. A
scene digest detects changed contents; it does not authenticate the source or
lock the scene between service calls. Coordinates at this boundary are mm,
quaternions are XYZW and joint coordinates are radians.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from numbers import Real
import re
import time
from types import SimpleNamespace

from vision_core.models import GateError


SERVICE_NAMES = (('scene', '/get_planning_scene'), ('ik', '/compute_ik'),
                 ('fk', '/compute_fk'), ('validity', '/check_state_validity'),
                 ('plan', '/plan_kinematic_path'))
MAX_SCENE_BYTES = 32 * 1024 * 1024


def _number(value, name='number'):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise GateError('invalid ' + name)
    return float(value)


def _vector(value, size, name):
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise GateError('invalid ' + name)
    return tuple(_number(x, name) for x in value)


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise GateError('invalid ' + name)
    return value


def _quat(value):
    q = _vector(value, 4, 'quaternion')
    if abs(math.hypot(*q) - 1) > 1e-5:
        raise GateError('quaternion must be unit length')
    return q


def _unit_quat(value):
    """Use a normalized copy for geometry, retaining received bytes in receipts."""
    q = _quat(value)
    norm = math.hypot(*q)
    return tuple(v / norm for v in q)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _qmul(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return (w*X + x*W + y*Z - z*Y, w*Y - x*Z + y*W + z*X,
            w*Z + x*Y - y*X + z*W, w*W - x*X - y*Y - z*Z)


def _orientation_error(a, b):
    """Shortest quaternion angle, stable even when acos(dot) would round to 0."""
    a, b = _unit_quat(a), _unit_quat(b)
    relative = _qmul((-a[0], -a[1], -a[2], a[3]), b)
    return 2 * math.atan2(math.hypot(*relative[:3]), abs(relative[3]))


def _rotate(q, xyz):
    return _qmul(_qmul(q, (*xyz, 0.0)), (-q[0], -q[1], -q[2], q[3]))[:3]


def camera_to_link(camera_xyz_mm, camera_quaternion, link_camera_xyz_mm, link_camera_quaternion):
    """T_scene_link = T_scene_camera @ inverse(T_link_camera)."""
    p, q = _vector(camera_xyz_mm, 3, 'camera position'), _unit_quat(camera_quaternion)
    t, r = _vector(link_camera_xyz_mm, 3, 'tool translation'), _unit_quat(link_camera_quaternion)
    link_q = _unit_quat(_qmul(q, (-r[0], -r[1], -r[2], r[3])))
    offset = _rotate(link_q, t)
    return tuple(p[i] - offset[i] for i in range(3)), link_q


def link_to_camera(link_xyz_mm, link_quaternion, link_camera_xyz_mm, link_camera_quaternion):
    p, q = _vector(link_xyz_mm, 3, 'link position'), _unit_quat(link_quaternion)
    t, r = _vector(link_camera_xyz_mm, 3, 'tool translation'), _unit_quat(link_camera_quaternion)
    offset = _rotate(q, t)
    return tuple(p[i] + offset[i] for i in range(3)), _unit_quat(_qmul(q, r))


@dataclass(frozen=True)
class JointLimit:
    name: str
    lower: float
    upper: float
    max_velocity: float
    max_acceleration: float

    def __post_init__(self):
        _text(self.name, 'joint name')
        for key in ('lower', 'upper', 'max_velocity', 'max_acceleration'):
            object.__setattr__(self, key, _number(getattr(self, key), key))
        if not (-1000 <= self.lower < self.upper <= 1000) or not 0 < self.max_velocity <= 1000 or not 0 < self.max_acceleration <= 10000:
            raise GateError('invalid joint limits')


@dataclass(frozen=True)
class AdapterConfig:
    group_name: str
    ik_link_name: str
    joint_limits: tuple[JointLimit, ...]
    link_camera_xyz_mm: tuple[float, float, float]
    link_camera_quaternion: tuple[float, float, float, float]
    model_revision: str
    calibration_revision: str
    service_names: tuple[tuple[str, str], ...] = SERVICE_NAMES
    planning_time_s: float = 3.0
    service_timeout_s: float = 5.0
    segment_timeout_s: float = 120.0
    velocity_scale: float = 0.1
    acceleration_scale: float = 0.1
    joint_tolerance: float = 1e-4
    position_tolerance_mm: float = 1.0
    orientation_tolerance_rad: float = 0.01
    sample_step_rad: float = 0.05
    max_samples: int = 4096
    max_points: int = 2048
    max_state_age_s: float = 2.0
    joint_state_topic: str | None = None
    start_velocity_tolerance_rad_s: float = 1e-6

    def __post_init__(self):
        for key in ('group_name', 'ik_link_name', 'model_revision', 'calibration_revision'):
            _text(getattr(self, key), key)
        if not isinstance(self.joint_limits, (tuple, list)) or not 1 <= len(self.joint_limits) <= 32 or any(not isinstance(x, JointLimit) for x in self.joint_limits):
            raise GateError('explicit joint limits required')
        object.__setattr__(self, 'joint_limits', tuple(self.joint_limits))
        if len(set(self.joint_names)) != len(self.joint_names):
            raise GateError('duplicate joint names')
        p = _vector(self.link_camera_xyz_mm, 3, 'tool translation')
        if max(map(abs, p)) > 10000:
            raise GateError('tool translation exceeds bound')
        object.__setattr__(self, 'link_camera_xyz_mm', p)
        object.__setattr__(self, 'link_camera_quaternion', _quat(self.link_camera_quaternion))
        if not isinstance(self.service_names, (tuple, list)) or len(self.service_names) != 5:
            raise GateError('five explicit service names required')
        services = tuple(tuple(x) for x in self.service_names)
        if any(len(x) != 2 for x in services) or {x[0] for x in services} != {x[0] for x in SERVICE_NAMES} or any(not isinstance(v, str) or not re.fullmatch(r'/[A-Za-z0-9_/]+', v) or len(v) > 256 for _, v in services) or len({x[1] for x in services}) != 5:
            raise GateError('invalid service mapping')
        object.__setattr__(self, 'service_names', tuple(sorted(services)))
        if self.joint_state_topic is not None and (not isinstance(self.joint_state_topic,str) or not re.fullmatch(r'/[A-Za-z0-9_/]+',self.joint_state_topic) or len(self.joint_state_topic)>256):
            raise GateError('invalid explicit joint-state topic')
        for key in ('planning_time_s', 'service_timeout_s', 'segment_timeout_s', 'velocity_scale', 'acceleration_scale', 'joint_tolerance', 'position_tolerance_mm', 'orientation_tolerance_rad', 'sample_step_rad', 'max_state_age_s','start_velocity_tolerance_rad_s'):
            object.__setattr__(self, key, _number(getattr(self, key), key))
        if not (0 < self.planning_time_s <= 60 and self.planning_time_s <= self.service_timeout_s <= 60 and self.service_timeout_s <= self.segment_timeout_s <= 600 and 0 < self.velocity_scale <= 1 and 0 < self.acceleration_scale <= 1 and 0 < self.joint_tolerance <= 0.01 and 0 < self.position_tolerance_mm <= 10 and 0 < self.orientation_tolerance_rad <= 0.1 and 0 < self.sample_step_rad <= 0.1 and 0 < self.max_state_age_s <= 60):
            raise GateError('invalid planning policy bounds')
        if type(self.max_samples) is not int or not 1 <= self.max_samples <= 10000 or type(self.max_points) is not int or not 1 <= self.max_points <= 4096:
            raise GateError('invalid planning resource bounds')
        if not 0 <= self.start_velocity_tolerance_rad_s <= 0.001:
            raise GateError('invalid trajectory start-velocity tolerance')

    @property
    def joint_names(self):
        return tuple(x.name for x in self.joint_limits)

    @property
    def digest(self):
        return _hash(asdict(self))


@dataclass(frozen=True)
class SceneSnapshot:
    scene_hash: str
    joint_names: tuple[str, ...]
    joint_positions: tuple[float, ...]
    joint_velocities: tuple[float, ...]
    timestamp: float
    robot_model_name: str
    reference: str
    received_at: float


@dataclass(frozen=True)
class TrajectoryPoint:
    time_from_start_s: float
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    accelerations: tuple[float, ...]


@dataclass(frozen=True)
class SegmentResult:
    view_id: str
    frame_id: str
    camera_xyz_mm: tuple[float, float, float]
    camera_quaternion: tuple[float, float, float, float]
    requested_start_joints: tuple[float, ...]
    ik_joints: tuple[float, ...]
    points: tuple[TrajectoryPoint, ...]
    scene_before: SceneSnapshot
    scene_after: SceneSnapshot
    config_hash: str
    started_at: float
    completed_at: float
    fk_camera_xyz_mm: tuple[float, float, float]
    fk_camera_quaternion: tuple[float, float, float, float]
    checked_state_count: int
    digest: str

    @property
    def start_joints(self):
        return self.points[0].positions

    @property
    def end_joints(self):
        return self.points[-1].positions


def verify_segment_digest(segment):
    if not isinstance(segment, SegmentResult):
        raise GateError('typed segment required')
    document = asdict(segment)
    document.pop('digest')
    if _hash(document) != segment.digest:
        raise GateError('segment digest mismatch')


def validate_snapshot(snapshot, config):
    """Validate a neutral snapshot without treating its hash as authentication."""
    if not isinstance(snapshot, SceneSnapshot) or not isinstance(config, AdapterConfig):
        raise GateError('typed scene snapshot/config required')
    if not isinstance(snapshot.scene_hash, str) or not re.fullmatch('[0-9a-f]{64}', snapshot.scene_hash):
        raise GateError('invalid scene digest')
    if type(snapshot.joint_names) is not tuple or snapshot.joint_names != config.joint_names:
        raise GateError('snapshot joint names mismatch')
    if type(snapshot.joint_positions) is not tuple or type(snapshot.joint_velocities) is not tuple:
        raise GateError('immutable snapshot joint data required')
    positions = _vector(snapshot.joint_positions, len(config.joint_limits), 'snapshot joint positions')
    if any(not limit.lower <= value <= limit.upper for value,limit in zip(positions,config.joint_limits)):
        raise GateError('snapshot joint bounds exceeded')
    if snapshot.joint_velocities:
        velocity = _vector(snapshot.joint_velocities, len(positions), 'snapshot velocities')
        if any(abs(v) > lim.max_velocity for v,lim in zip(velocity,config.joint_limits)):
            raise GateError('snapshot joint velocity bounds exceeded')
    if _number(snapshot.timestamp, 'snapshot timestamp') < 0:
        raise GateError('invalid snapshot timestamp')
    if not 0 <= _number(snapshot.received_at,'snapshot receipt time')-snapshot.timestamp <= config.max_state_age_s:
        raise GateError('snapshot source timestamp is stale or future')
    _text(snapshot.robot_model_name, 'robot model')
    if snapshot.reference != 'moveit-scene:sha256:' + snapshot.scene_hash:
        raise GateError('snapshot reference mismatch')


def validate_segment(segment, config):
    """Recheck an adapter result at the coordinator's separate trust boundary.

    These are consistency checks, not source authentication or proof that a
    mutable remote PlanningScene stayed locked. The caller supplies that proof.
    """
    if not isinstance(segment,SegmentResult) or not isinstance(config, AdapterConfig) or segment.config_hash != config.digest:
        raise GateError('segment configuration mismatch')
    _text(segment.view_id, 'view id'); _text(segment.frame_id, 'frame id')
    xyz = _vector(segment.camera_xyz_mm, 3, 'target position')
    if max(map(abs, xyz)) > 1_000_000:
        raise GateError('target coordinates exceed bound')
    q = _quat(segment.camera_quaternion)
    for name in ('camera_xyz_mm','camera_quaternion','requested_start_joints','ik_joints','points','fk_camera_xyz_mm','fk_camera_quaternion'):
        if type(getattr(segment,name)) is not tuple:
            raise GateError('immutable segment data required')
    validate_snapshot(segment.scene_before, config)
    validate_snapshot(segment.scene_after, config)
    if segment.scene_before.scene_hash != segment.scene_after.scene_hash or segment.scene_before.robot_model_name != segment.scene_after.robot_model_name:
        raise GateError('segment scene changed')
    start_time = _number(segment.started_at, 'segment start time')
    end_time = _number(segment.completed_at, 'segment end time')
    if not 0 <= start_time <= end_time or end_time-start_time > config.segment_timeout_s:
        raise GateError('invalid segment time interval')
    if not start_time <= segment.scene_before.received_at <= segment.scene_after.received_at <= end_time:
        raise GateError('segment state snapshot receipt time mismatch')
    if max(abs(x-y) for x,y in zip(segment.scene_before.joint_positions, segment.scene_after.joint_positions)) > config.joint_tolerance:
        raise GateError('measured robot state drifted')
    if not 1 <= len(segment.points) <= config.max_points or any(not isinstance(p,TrajectoryPoint) for p in segment.points):
        raise GateError('invalid trajectory points')
    for positions in (segment.requested_start_joints,segment.ik_joints):
        _vector(positions,len(config.joint_limits),'joint positions')
        if any(not limit.lower <= value <= limit.upper for value,limit in zip(positions,config.joint_limits)):
            raise GateError('segment joint bounds exceeded')
    previous = None
    samples = 1
    for point in segment.points:
        if any(type(getattr(point,name)) is not tuple for name in ('positions','velocities','accelerations')):
            raise GateError('immutable trajectory point required')
        p = _vector(point.positions,len(config.joint_limits),'point positions')
        v = _vector(point.velocities,len(p),'point velocities')
        a = _vector(point.accelerations,len(p),'point accelerations')
        t = _number(point.time_from_start_s,'trajectory duration')
        if not 0 <= t <= 3600:
            raise GateError('invalid trajectory duration')
        for index,limit in enumerate(config.joint_limits):
            if not limit.lower <= p[index] <= limit.upper or abs(v[index]) > limit.max_velocity*config.velocity_scale+1e-6 or abs(a[index]) > limit.max_acceleration*config.acceleration_scale+1e-6:
                raise GateError('trajectory bounds exceeded')
        if previous is not None:
            dt = t-previous.time_from_start_s
            if dt <= 0:
                raise GateError('nonmonotonic trajectory time')
            for index,limit in enumerate(config.joint_limits):
                if abs(p[index]-previous.positions[index])/dt > limit.max_velocity*config.velocity_scale+1e-6 or abs(v[index]-previous.velocities[index])/dt > limit.max_acceleration*config.acceleration_scale+1e-6:
                    raise GateError('trajectory finite-difference bounds exceeded')
            samples += max(1,math.ceil(max(abs(x-y) for x,y in zip(previous.positions,p))/config.sample_step_rad))
        previous = point
    if samples > config.max_samples or type(segment.checked_state_count) is not int or segment.checked_state_count != samples:
        raise GateError('collision validation sample count mismatch')
    if segment.points[0].time_from_start_s != 0 or max(abs(x-y) for x,y in zip(segment.start_joints,segment.requested_start_joints)) > config.joint_tolerance or max(abs(x-y) for x,y in zip(segment.end_joints,segment.ik_joints)) > config.joint_tolerance:
        raise GateError('segment start or goal mismatch')
    if any(abs(v)>config.start_velocity_tolerance_rad_s for v in segment.points[0].velocities) or any(abs(v)>1e-6 for v in segment.points[-1].velocities):
        raise GateError('photography trajectory start or end velocity exceeds tolerance')
    actual_p, actual_q = _vector(segment.fk_camera_xyz_mm,3,'FK position'), _quat(segment.fk_camera_quaternion)
    if math.dist(actual_p,xyz) > config.position_tolerance_mm or _orientation_error(actual_q,q) > config.orientation_tolerance_rad:
        raise GateError('segment FK target mismatch')
    # Serialize only after all public fields have bounded, immutable shapes.
    verify_segment_digest(segment)


def _message_document(value, budget):
    """Bounded ROS-message conversion; header stamps do not identify geometry."""
    budget[0] -= 1
    budget[1] -= 32  # conservative JSON/container overhead per scalar or node
    if budget[0] < 0 or budget[1] < 0:
        raise GateError('scene structure exceeds limit')
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            budget[1] -= len(value)*6  # worst-case JSON escaping, before copying
            if budget[1] < 0:
                raise GateError('scene string budget exceeded')
        return value
    if isinstance(value, Real):
        if not math.isfinite(value):
            raise GateError('nonfinite scene data')
        return int(value) if isinstance(value, int) else float(value)
    if isinstance(value, dict):
        return {str(k): _message_document(v, budget) for k, v in value.items() if k != 'stamp'}
    if hasattr(value, 'get_fields_and_field_types'):
        return {k: _message_document(getattr(value, k), budget) for k in value.get_fields_and_field_types() if k != 'stamp'}
    if isinstance(value, SimpleNamespace):
        return _message_document(vars(value), budget)
    if hasattr(value, '__iter__') and hasattr(value, '__len__'):
        if len(value) > MAX_SCENE_BYTES:
            raise GateError('scene array exceeds limit')
        return [_message_document(x, budget) for x in value]
    raise GateError('unsupported scene value')


def scene_digest(scene, group_joint_names):
    """Includes geometry, ACM, padding, scaling, TF and attached collision bodies.

    Current group joint positions are bound separately. Unplanned joint states
    and multi-DOF transforms remain in the digest. Timestamps are omitted.
    """
    if scene.is_diff is not False or not scene.robot_model_name:
        raise GateError('complete planning scene required')
    state = scene.robot_state
    js = state.joint_state
    if not 1 <= len(js.name) <= 256 or any(not isinstance(name,str) or not name or len(name)>256 for name in js.name) or len(js.name) != len(js.position) or len(set(js.name)) != len(js.name):
        raise GateError('invalid scene joint state')
    data = {'name': scene.name, 'robot_model_name': scene.robot_model_name,
            'world': scene.world, 'allowed_collision_matrix': scene.allowed_collision_matrix,
            'link_padding': scene.link_padding, 'link_scale': scene.link_scale,
            'fixed_frame_transforms': scene.fixed_frame_transforms,
            'attached_collision_objects': state.attached_collision_objects,
            'multi_dof_joint_state': state.multi_dof_joint_state,
            'other_joints': sorted((name, float(pos)) for name, pos in zip(js.name, js.position) if name not in group_joint_names)}
    document = _message_document(data, [2_000_000,MAX_SCENE_BYTES])
    serialized = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(serialized) > MAX_SCENE_BYTES:
        raise GateError('planning scene exceeds byte limit')
    return hashlib.sha256(serialized.encode()).hexdigest()


def _types():
    # Optional ROS imports are confined to the explicitly requested factory.
    from moveit_msgs.srv import GetPlanningScene, GetPositionIK, GetPositionFK, GetStateValidity, GetMotionPlan
    from moveit_msgs.msg import Constraints, JointConstraint
    return SimpleNamespace(scene=GetPlanningScene, ik=GetPositionIK, fk=GetPositionFK,
                           validity=GetStateValidity, plan=GetMotionPlan,
                           Constraints=Constraints, JointConstraint=JointConstraint)


class MoveItAdapter:
    """Five service clients, deliberately no publisher or execution action client.

    rpc(kind, request, timeout_s) must return the terminal service response or
    raise. Acknowledgements and futures are not responses. The adapter checks a
    monotonic total deadline between calls; rpc must honor its own timeout.
    """
    def __init__(self, config, rpc, message_types, *, clock=time.time, monotonic=time.monotonic, joint_state_source=None):
        if not isinstance(config, AdapterConfig) or not callable(rpc) or not callable(clock) or not callable(monotonic):
            raise GateError('invalid adapter construction')
        self.config, self._rpc, self._types = config, rpc, message_types
        self._clock, self._monotonic = clock, monotonic
        if (config.joint_state_topic is None) != (joint_state_source is None) or (joint_state_source is not None and not callable(joint_state_source)):
            raise GateError('explicit topic and joint-state source must be supplied together')
        self._joint_state_source=joint_state_source
        self._clients = ()
        self._subscription = None

    @classmethod
    def from_node(cls, node, config, wait_for_future, *, clock=time.time, monotonic=time.monotonic):
        """Use a caller-owned node/executor. wait_for_future(future, timeout)."""
        if not callable(wait_for_future):
            raise GateError('caller-owned future waiter required')
        message_types = _types()
        clients = {}
        try:
            for kind, name in config.service_names:
                clients[kind] = node.create_client(getattr(message_types, kind), name)
        except Exception:
            for client in clients.values():
                node.destroy_client(client)
            raise

        def rpc(kind, request, timeout):
            began = monotonic()
            client = clients[kind]
            if not client.wait_for_service(timeout_sec=timeout):
                raise GateError('MoveIt service unavailable: ' + kind)
            remaining = timeout - (monotonic() - began)
            if remaining <= 0:
                raise GateError('MoveIt service deadline: ' + kind)
            future = client.call_async(request)
            wait_for_future(future, remaining)
            if not future.done():
                future.cancel()
                raise GateError('MoveIt response timeout: ' + kind)
            if future.cancelled() or future.exception() is not None:
                raise GateError('MoveIt service failed: ' + kind)
            return future.result()

        latest={'message':None}
        subscription=None
        if config.joint_state_topic is not None:
            from sensor_msgs.msg import JointState
            from rclpy.qos import QoSProfile,ReliabilityPolicy,HistoryPolicy
            def receive(message):
                # Retain one bounded owned copy; never turn a receive time into
                # the source measurement time or invent missing velocities.
                if (not 1<=len(message.name)<=256 or any(not isinstance(name,str) or len(name)>256 for name in message.name)
                    or any(len(getattr(message,key))>256 for key in ('position','velocity','effort'))
                    or len(message.header.frame_id)>256):
                    latest['message']=None
                    return
                latest['message']=deepcopy(message)
            try:
                subscription=node.create_subscription(JointState,config.joint_state_topic,receive,
                    QoSProfile(depth=1,history=HistoryPolicy.KEEP_LAST,reliability=ReliabilityPolicy.BEST_EFFORT))
            except Exception:
                for client in clients.values(): node.destroy_client(client)
                raise
        adapter = cls(config, rpc, message_types, clock=clock, monotonic=monotonic,
                      joint_state_source=(lambda:latest['message']) if subscription is not None else None)
        adapter._clients = tuple(clients.values())
        adapter._node = node
        adapter._subscription=subscription
        return adapter

    def close(self):
        for client in self._clients:
            self._node.destroy_client(client)
        self._clients = ()
        if self._subscription is not None:
            self._node.destroy_subscription(self._subscription)
            self._subscription=None

    def _call(self, kind, request, deadline):
        began = self._monotonic()
        remaining = min(self.config.service_timeout_s, deadline - began)
        if remaining <= 0:
            raise GateError('MoveIt planning deadline exceeded')
        try:
            result = self._rpc(kind, request, remaining)
        except GateError:
            raise
        except Exception as exc:
            raise GateError('MoveIt service failed: ' + kind) from exc
        if result is None or self._monotonic() > began+remaining:
            raise GateError('MoveIt missing or late response: ' + kind)
        return result

    def _positions(self, values):
        result = _vector(tuple(values), len(self.config.joint_limits), 'joint positions')
        if any(not limit.lower <= value <= limit.upper for value, limit in zip(result, self.config.joint_limits)):
            raise GateError('joint position outside explicit bounds')
        return result

    def _joints(self, joint_state):
        if not 1<=len(joint_state.name)<=256 or any(not isinstance(name,str) or not name or len(name)>256 for name in joint_state.name):
            raise GateError('invalid or excessive joint names')
        names = tuple(joint_state.name)
        if not 1 <= len(names) <= 256 or len(names) != len(set(names)) or len(names) != len(joint_state.position) or not set(self.config.joint_names) <= set(names):
            raise GateError('incomplete or duplicated joint state')
        positions = dict(zip(names, joint_state.position))
        # Check unplanned joints too: their state is retained in every request.
        for value in positions.values():
            _number(value, 'joint position')
        return self._positions(tuple(positions[name] for name in self.config.joint_names))

    def _snapshot(self, deadline):
        request = self._types.scene.Request()
        request.components.components = 1023  # all defined PlanningSceneComponents
        source = self._call('scene', request, deadline).scene
        # Bound nested ROS scene content before making our own retained copy.
        scene_digest(source,self.config.joint_names)
        scene = deepcopy(source)
        js = scene.robot_state.joint_state
        positions = self._joints(js)
        if self._joint_state_source is not None:
            measured=self._joint_state_source()
            if measured is None:
                raise GateError('no measured joint state on explicit source topic')
            measured_positions=self._joints(measured)
            if max(abs(x-y) for x,y in zip(positions,measured_positions)) > self.config.joint_tolerance:
                raise GateError('PlanningScene and measured joint-state source disagree')
            js=measured
            positions=measured_positions
        velocities = ()
        if len(js.velocity):
            if len(js.velocity) != len(js.name):
                raise GateError('incomplete joint velocity state')
            all_v = dict(zip(js.name, js.velocity))
            velocities = tuple(_number(all_v[name], 'joint velocity') for name in self.config.joint_names)
        stamp = js.header.stamp
        if type(stamp.sec) is not int or type(stamp.nanosec) is not int or stamp.sec < 0 or not 0 <= stamp.nanosec < 1_000_000_000:
            raise GateError('invalid scene state timestamp')
        timestamp = stamp.sec + stamp.nanosec / 1e9
        now = _number(self._clock(), 'clock')
        if not 0 <= now - timestamp <= self.config.max_state_age_s:
            raise GateError('stale or future robot state')
        digest = scene_digest(scene, self.config.joint_names)
        snapshot = SceneSnapshot(digest, self.config.joint_names, positions, velocities, timestamp,
                                 scene.robot_model_name, 'moveit-scene:sha256:' + digest, now)
        validate_snapshot(snapshot,self.config)
        return snapshot, scene

    def snapshot(self):
        return self._snapshot(self._monotonic() + self.config.service_timeout_s)[0]

    def _state(self, scene, positions):
        state = deepcopy(scene.robot_state)
        values = dict(zip(self.config.joint_names, positions))
        state.joint_state.position = [float(values.get(name, pos)) for name, pos in zip(state.joint_state.name, state.joint_state.position)]
        state.joint_state.velocity = [0.0] * len(state.joint_state.name)
        state.joint_state.effort = []
        state.is_diff = False
        return state

    def _valid(self, scene, positions, deadline):
        request = self._types.validity.Request()
        request.robot_state = self._state(scene, self._positions(positions))
        request.group_name = self.config.group_name
        response = self._call('validity', request, deadline)
        if response.valid is not True or len(response.contacts):
            raise GateError('MoveIt state collision or constraint failure')
        if any(result.result is not True for result in response.constraint_result):
            raise GateError('MoveIt state constraint failure')

    def _fk(self, scene, positions, frame_id, deadline):
        request = self._types.fk.Request()
        request.header.frame_id = frame_id
        request.fk_link_names = [self.config.ik_link_name]
        request.robot_state = self._state(scene, positions)
        response = self._call('fk', request, deadline)
        if response.error_code.val != 1 or tuple(response.fk_link_names) != (self.config.ik_link_name,) or len(response.pose_stamped) != 1:
            raise GateError('MoveIt FK failed')
        stamped = response.pose_stamped[0]
        if stamped.header.frame_id != frame_id:
            raise GateError('MoveIt FK frame mismatch')
        p, q = stamped.pose.position, stamped.pose.orientation
        return link_to_camera((p.x*1000, p.y*1000, p.z*1000), (q.x, q.y, q.z, q.w),
                              self.config.link_camera_xyz_mm, self.config.link_camera_quaternion)

    def _check_pose(self, actual, expected):
        p, q = actual
        P, Q = expected
        if math.dist(p, P) > self.config.position_tolerance_mm or _orientation_error(q,Q) > self.config.orientation_tolerance_rad:
            raise GateError('FK camera pose misses target')

    def _trajectory(self, response, start, goal):
        if response.error_code.val != 1 or response.group_name != self.config.group_name:
            raise GateError('MoveIt planning failed or group mismatch')
        if max(abs(x-y) for x, y in zip(self._joints(response.trajectory_start.joint_state), start)) > self.config.joint_tolerance:
            raise GateError('MoveIt changed requested start state')
        trajectory = response.trajectory
        if len(trajectory.multi_dof_joint_trajectory.joint_names) or len(trajectory.multi_dof_joint_trajectory.points):
            raise GateError('multi-DOF trajectories are unsupported')
        joint = trajectory.joint_trajectory
        if tuple(joint.joint_names) != self.config.joint_names or not 1 <= len(joint.points) <= self.config.max_points:
            raise GateError('trajectory joint names or size mismatch')
        points = []
        for point in joint.points:
            duration = point.time_from_start
            if type(duration.sec) is not int or type(duration.nanosec) is not int or duration.sec < 0 or not 0 <= duration.nanosec < 1_000_000_000:
                raise GateError('invalid trajectory duration')
            stamp = duration.sec + duration.nanosec / 1e9
            if stamp > 3600 or (points and stamp <= points[-1].time_from_start_s):
                raise GateError('nonmonotonic or excessive trajectory duration')
            positions = self._positions(point.positions)
            # Timed trajectories must carry full derivatives, not just waypoints.
            velocity = _vector(tuple(point.velocities), len(positions), 'trajectory velocities')
            acceleration = _vector(tuple(point.accelerations), len(positions), 'trajectory accelerations')
            for i, limit in enumerate(self.config.joint_limits):
                if abs(velocity[i]) > limit.max_velocity * self.config.velocity_scale + 1e-6 or abs(acceleration[i]) > limit.max_acceleration * self.config.acceleration_scale + 1e-6:
                    raise GateError('trajectory derivative exceeds scaled bounds')
            if points:
                previous = points[-1]
                dt = stamp - previous.time_from_start_s
                for i, limit in enumerate(self.config.joint_limits):
                    if abs(positions[i] - previous.positions[i]) / dt > limit.max_velocity * self.config.velocity_scale + 1e-6:
                        raise GateError('trajectory timing exceeds velocity bound')
            points.append(TrajectoryPoint(stamp, positions, velocity, acceleration))
        if points[0].time_from_start_s != 0 or max(abs(x-y) for x,y in zip(points[0].positions, start)) > self.config.joint_tolerance or max(abs(x-y) for x,y in zip(points[-1].positions, goal)) > self.config.joint_tolerance:
            raise GateError('trajectory start or endpoint mismatch')
        return tuple(points)

    def _samples(self, points):
        """Bounded linear samples supplement MoveIt's own path validation."""
        counts = [max(1, math.ceil(max(abs(x-y) for x,y in zip(a.positions, b.positions)) / self.config.sample_step_rad)) for a,b in zip(points, points[1:])]
        if sum(counts) + 1 > self.config.max_samples:
            raise GateError('trajectory collision samples exceed limit')
        yield points[0].positions
        for a,b,count in zip(points, points[1:], counts):
            for index in range(1, count+1):
                t = index / count
                yield tuple(x + t*(y-x) for x,y in zip(a.positions, b.positions))

    def plan_segment(self, view_id, frame_id, camera_xyz_mm, camera_quaternion, start_joints, expected_scene_hash):
        _text(view_id, 'view id'); _text(frame_id, 'frame id')
        if not isinstance(expected_scene_hash, str) or not re.fullmatch('[0-9a-f]{64}', expected_scene_hash):
            raise GateError('expected scene digest required')
        xyz = _vector(camera_xyz_mm, 3, 'target position')
        if max(map(abs, xyz)) > 1_000_000:
            raise GateError('target coordinates exceed bound')
        quaternion, start = _quat(camera_quaternion), self._positions(start_joints)
        started = _number(self._clock(), 'clock')
        deadline = self._monotonic() + self.config.segment_timeout_s
        before, scene = self._snapshot(deadline)
        if before.scene_hash != expected_scene_hash:
            raise GateError('planning scene changed before planning')
        self._valid(scene, start, deadline)
        link_xyz, link_q = camera_to_link(xyz, quaternion, self.config.link_camera_xyz_mm, self.config.link_camera_quaternion)
        request = self._types.ik.Request()
        ik = request.ik_request
        ik.group_name, ik.ik_link_name = self.config.group_name, self.config.ik_link_name
        ik.avoid_collisions = True
        ik.robot_state = self._state(scene, start)
        ik.pose_stamped.header.frame_id = frame_id
        p, q = ik.pose_stamped.pose.position, ik.pose_stamped.pose.orientation
        p.x, p.y, p.z = (float(v / 1000) for v in link_xyz)
        q.x, q.y, q.z, q.w = map(float, link_q)
        ik.timeout.sec = int(self.config.planning_time_s)
        ik.timeout.nanosec = int((self.config.planning_time_s - int(self.config.planning_time_s)) * 1e9)
        response = self._call('ik', request, deadline)
        if response.error_code.val != 1:
            raise GateError('MoveIt IK failed')
        goal = self._joints(response.solution.joint_state)
        self._valid(scene, goal, deadline)
        self._check_pose(self._fk(scene, goal, frame_id, deadline), (xyz, quaternion))
        request = self._types.plan.Request()
        motion = request.motion_plan_request
        motion.group_name = self.config.group_name
        motion.start_state = self._state(scene, start)
        motion.allowed_planning_time = self.config.planning_time_s
        motion.num_planning_attempts = 1
        motion.max_velocity_scaling_factor = self.config.velocity_scale
        motion.max_acceleration_scaling_factor = self.config.acceleration_scale
        goal_constraints = self._types.Constraints()
        for name, value in zip(self.config.joint_names, goal):
            constraint = self._types.JointConstraint()
            constraint.joint_name, constraint.position = name, float(value)
            constraint.tolerance_above = constraint.tolerance_below = self.config.joint_tolerance
            constraint.weight = 1.0
            goal_constraints.joint_constraints.append(constraint)
        motion.goal_constraints = [goal_constraints]
        result = self._call('plan', request, deadline).motion_plan_response
        points = self._trajectory(result, start, goal)
        checked = 0
        for sample in self._samples(points):
            self._valid(scene, sample, deadline)
            checked += 1
        fk = self._fk(scene, points[-1].positions, frame_id, deadline)
        self._check_pose(fk, (xyz, quaternion))
        after, _ = self._snapshot(deadline)
        if after.scene_hash != expected_scene_hash:
            raise GateError('planning scene changed during planning')
        if max(abs(x-y) for x,y in zip(before.joint_positions, after.joint_positions)) > self.config.joint_tolerance:
            raise GateError('measured robot state drifted while planning')
        completed = _number(self._clock(), 'clock')
        if completed < started:
            raise GateError('clock moved backwards during planning')
        data = dict(view_id=view_id, frame_id=frame_id, camera_xyz_mm=xyz,
                    camera_quaternion=quaternion, requested_start_joints=start,
                    ik_joints=goal, points=points, scene_before=before, scene_after=after,
                    config_hash=self.config.digest, started_at=started, completed_at=completed,
                    fk_camera_xyz_mm=fk[0], fk_camera_quaternion=fk[1], checked_state_count=checked)
        digest = _hash({key: asdict(value) if hasattr(value, '__dataclass_fields__') else
                        [asdict(x) for x in value] if key == 'points' else value for key,value in data.items()})
        segment = SegmentResult(**data, digest=digest)
        validate_segment(segment,self.config)
        return segment
