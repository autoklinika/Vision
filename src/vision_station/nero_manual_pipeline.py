"""Contracts for the isolated Servo/JTC reference pipeline.

JTC is an interpolator, not the NERO feedback authority. The physical
owner remains the sole CAN writer. No launch, hardware access, approval
or control-mode changes are performed by this module.
"""
from dataclasses import dataclass
import math
import re
from threading import RLock
import time

from .nero import NODE
from .nero_manual import JOINTS, AGE, finite, vector7

PHYSICAL_NS = "/vision_manual"
FIXTURE_NS = "/vision_manual_fixture"
PHYSICAL_FEEDBACK = "/nero_guarded/feedback/joint_states"
JOINT_STATE_TYPE = "sensor_msgs/msg/JointState"
SERVO_STATUS_TYPE = "moveit_msgs/msg/ServoStatus"
TRAJECTORY_TYPE = "trajectory_msgs/msg/JointTrajectory"
CONTROLLER_STATE_TYPE = "control_msgs/msg/JointTrajectoryControllerState"
TWIST_TYPE = "geometry_msgs/msg/TwistStamped"
JTC_TYPE = "joint_trajectory_controller/JointTrajectoryController"
JSB_TYPE = "joint_state_broadcaster/JointStateBroadcaster"
MOCK_PLUGIN = "mock_components/GenericSystem"


@dataclass(frozen=True)
class Routes:
    namespace: str
    feedback_topic: str
    feedback_node: str

    def __post_init__(self):
        if self.namespace == PHYSICAL_NS:
            if (self.feedback_topic, self.feedback_node) != (PHYSICAL_FEEDBACK, NODE):
                raise ValueError("physical Servo must follow the guarded NERO feedback")
        elif self.namespace == FIXTURE_NS:
            if (self.feedback_topic, self.feedback_node) != (
                    FIXTURE_NS + "/observed_joint_states", FIXTURE_NS + "/fixture"):
                raise ValueError("explicit synthetic feedback fixture required")
        else:
            raise ValueError("fixed manual namespaces required")

    @classmethod
    def physical(cls):
        return cls(PHYSICAL_NS, PHYSICAL_FEEDBACK, NODE)

    @classmethod
    def fixture(cls):
        return cls(FIXTURE_NS, FIXTURE_NS + "/observed_joint_states", FIXTURE_NS + "/fixture")

    @property
    def servo_node(self):
        return self.namespace + "/servo_node"

    @property
    def controller(self):
        return self.namespace + "/arm_controller"

    @property
    def controller_manager(self):
        return self.namespace + "/controller_manager"

    @property
    def synthetic_feedback_topic(self):
        return self.namespace + "/joint_states"

    @property
    def twist(self):
        return self.namespace + "/twist"

    @property
    def trajectory(self):
        return self.namespace + "/servo_trajectory"

    @property
    def status(self):
        return self.namespace + "/servo_status"

    @property
    def controller_state(self):
        return self.controller + "/controller_state"

    @property
    def controller_command(self):
        return self.controller + "/joint_trajectory"

    def required_servo_parameters(self):
        return {
            "moveit_servo.move_group_name": "arm",
            "moveit_servo.command_in_type": "speed_units",
            "moveit_servo.joint_topic": self.feedback_topic,
            "moveit_servo.cartesian_command_in_topic": self.twist,
            "moveit_servo.command_out_topic": self.trajectory,
            "moveit_servo.status_topic": self.status,
            "moveit_servo.command_out_type": "trajectory_msgs/JointTrajectory",
            "moveit_servo.check_collisions": True,
            "moveit_servo.is_primary_planning_scene_monitor": True,
            "moveit_servo.publish_joint_positions": True,
            "moveit_servo.publish_joint_velocities": True,
            "use_sim_time": False,
        }

    def endpoints(self):
        return {
            self.feedback_topic: (self.feedback_node, JOINT_STATE_TYPE),
            self.trajectory: (self.servo_node, TRAJECTORY_TYPE),
            self.status: (self.servo_node, SERVO_STATUS_TYPE),
            self.controller_state: (self.controller, CONTROLLER_STATE_TYPE),
        }


@dataclass(frozen=True)
class Endpoint:
    node: str
    message_type: str
    gid: bytes


@dataclass(frozen=True)
class Contract:
    """Expected immutable values from an independently checked scene/config.

    A digest of a scene received from an unverified running system is NOT
    an approval. Fixture receipts must never be treated as station receipts.
    """
    routes: Routes
    scene_digest: str
    parameters: tuple
    scene_tracking_max_rad: float

    def __post_init__(self):
        if not isinstance(self.routes, Routes) or not re.fullmatch(r"[a-f0-9]{64}", self.scene_digest):
            raise ValueError("explicit scene fingerprint required")
        if not isinstance(self.parameters, tuple) or len(dict(self.parameters)) != len(self.parameters):
            raise ValueError("immutable parameter inventory required")
        p = dict(self.parameters)
        for key, value in self.routes.required_servo_parameters().items():
            if key not in p or type(p[key]) is not type(value) or p[key] != value:
                raise ValueError("unexpected Servo route or configuration: " + key)
        for key in ("robot_description", "robot_description_semantic"):
            if not isinstance(p.get(key), str) or not p[key].strip():
                raise ValueError("explicit model description required: " + key)
        if not finite(self.scene_tracking_max_rad) or not 0 < self.scene_tracking_max_rad <= .01:
            raise ValueError("explicit bounded state agreement required")
        # These settings are relevant even when not changed from upstream.
        # Require explicit values; never replace the approved collision
        # margins, speed limits or timeout with convenient test defaults.
        for key in ("publish_period", "incoming_command_timeout",
                    "collision_check_rate", "self_collision_proximity_threshold",
                    "scene_collision_proximity_threshold", "scale.linear",
                    "scale.rotational", "scale.joint"):
            value = p.get("moveit_servo." + key)
            if not finite(value) or value <= 0:
                raise ValueError("explicit positive Servo setting required: " + key)
        for key in ("check_octomap_collisions", "use_smoothing",
                    "apply_twist_commands_about_ee_frame"):
            if type(p.get("moveit_servo." + key)) is not bool:
                raise ValueError("explicit Servo setting required: " + key)
        for key, value in self.parameters:
            if not isinstance(key, str) or type(value) not in (str, bool, int, float):
                raise ValueError("scalar parameter readback only")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("nonfinite parameter")


@dataclass(frozen=True)
class Evidence:
    # Each observation is a coherent, bounded service readback batch.
    captured_mono: float
    feedback_stamp: float
    feedback_q: tuple
    scene_q: tuple
    scene_digest: str
    parameters: tuple
    publishers: tuple
    subscribers: tuple
    controllers_ok: bool
    interpolator_only: bool
    twist_mode_confirmed: bool


class PipelineAuthority:
    """Read-only, source-pinned, fail-closed readiness lease.

    The caller obtains evidence outside the hardware TX lock. This callable
    never waits for a ROS service or performs actuator operations. An observed
    mismatch after readiness latches until explicit reconstruction. It is not
    a functional-safety certification or a physical commissioning authority.
    """
    def __init__(self, contract, *, wall=time.time, mono=time.monotonic, max_batch_age=.5):
        if not isinstance(contract, Contract) or not finite(max_batch_age) or not 0 < max_batch_age <= .5:
            raise ValueError("explicit pipeline contract required")
        self.contract = contract
        self.wall, self.mono = wall, mono
        self.max_batch_age = max_batch_age
        self.lock = RLock()
        self._pins = {}
        self._evidence = None
        self._latched = False
        self._ever_ready = False
        self.reason = "NO_EVIDENCE"

    def _reject(self, reason):
        self._evidence = None
        if self._ever_ready:
            self._latched = True
        self.reason = reason
        return False

    def _validate(self, e):
        if not isinstance(e, Evidence):
            return "EVIDENCE_MISSING"
        if not finite(e.captured_mono) or not 0 <= self.mono() - e.captured_mono <= self.max_batch_age:
            return "BATCH_STALE"
        if not finite(e.feedback_stamp) or not 0 <= self.wall() - e.feedback_stamp <= AGE:
            return "FEEDBACK_STALE"
        if not vector7(e.feedback_q) or not vector7(e.scene_q):
            return "JOINT_STATE_INVALID"
        if max(abs(x-y) for x, y in zip(e.feedback_q, e.scene_q)) > self.contract.scene_tracking_max_rad:
            return "SERVO_STATE_NOT_FEEDBACK"
        if e.scene_digest != self.contract.scene_digest:
            return "SCENE_CHANGED"
        actual = dict(e.parameters)
        if any(k not in actual or type(actual[k]) is not type(v) or actual[k] != v
               for k, v in self.contract.parameters):
            return "PARAMETERS_CHANGED"
        if e.controllers_ok is not True or e.interpolator_only is not True:
            return "CONTROLLER_INVALID"
        if e.twist_mode_confirmed is not True:
            return "TWIST_MODE_NOT_CONFIRMED"
        pubs = dict(e.publishers)
        subs = dict(e.subscribers)
        routes = self.contract.routes
        pins = {}
        for topic, (node, kind) in routes.endpoints().items():
            endpoints = pubs.get(topic, ())
            if len(endpoints) != 1:
                return "SOURCE_MISSING_OR_DUPLICATE"
            ep = endpoints[0]
            if (not isinstance(ep, Endpoint) or ep.node != node or ep.message_type != kind
                    or type(ep.gid) is not bytes or not ep.gid or not any(ep.gid)):
                return "SOURCE_UNVERIFIED"
            if topic in self._pins and self._pins[topic] != ep.gid:
                return "SOURCE_REPLACED"
            pins[topic] = ep.gid
        if (routes.servo_node, JOINT_STATE_TYPE) not in subs.get(routes.feedback_topic, ()):
            return "SERVO_FEEDBACK_SUBSCRIPTION_MISSING"
        if (routes.servo_node, JOINT_STATE_TYPE) in subs.get(routes.synthetic_feedback_topic, ()):
            return "SERVO_FOLLOWS_INTERPOLATOR"
        # Only the single owner (fixture node in the lab) may issue Twist.
        # Both endpoints must exist before a pipeline can become ready.
        for topic, node, kind in (
            (routes.twist, routes.feedback_node, TWIST_TYPE),
            (routes.controller_command, "/vision_servo_sample_relay", TRAJECTORY_TYPE),
        ):
            endpoints = pubs.get(topic, ())
            if topic in self._pins and (len(endpoints) != 1 or endpoints[0].gid != self._pins[topic]):
                return "COMMAND_SOURCE_REPLACED"
            if (len(endpoints) != 1 or endpoints[0].node != node or endpoints[0].message_type != kind
                    or type(endpoints[0].gid) is not bytes or not endpoints[0].gid or not any(endpoints[0].gid)):
                return "COMMAND_SOURCE_UNVERIFIED"
            pins[topic] = endpoints[0].gid
        self._pins.update(pins)
        return None

    def observe(self, evidence):
        with self.lock:
            if self._latched:
                return False
            try:
                reason = self._validate(evidence)
            except Exception:
                reason = "EVIDENCE_INVALID"
            if reason:
                return self._reject(reason)
            self._evidence = evidence
            self._ever_ready = True
            self.reason = "VERIFIED"
            return True

    def invalidate(self, reason):
        with self.lock:
            if not self._latched:
                self._reject(reason)

    def agrees_with_feedback(self, feedback):
        """Compare cached PSM input against the sole owner's actual SDK cache."""
        from .nero_manual import Feedback
        with self.lock:
            if not self():
                return False
            if (not isinstance(feedback, Feedback) or not feedback.valid(self.wall())
                    or max(abs(a-b) for a,b in zip(feedback.q, self._evidence.feedback_q))
                        > self.contract.scene_tracking_max_rad):
                return self._reject("SDK_STATE_MISMATCH")
            return True

    def __call__(self):
        with self.lock:
            if self._latched or self._evidence is None:
                return False
            # Scene/config may only be revalidated by an independent batch.
            # Do not keep refreshing the same evidence or its timestamps.
            if not 0 <= self.mono() - self._evidence.captured_mono <= self.max_batch_age:
                return self._reject("BATCH_STALE")
            if not 0 <= self.wall() - self._evidence.feedback_stamp <= AGE:
                return self._reject("FEEDBACK_STALE")
            return True
