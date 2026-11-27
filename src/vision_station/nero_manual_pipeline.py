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
from .nero_feedback_sync import FeedbackHistory

PHYSICAL_NS = "/vision_manual"
FIXTURE_NS = "/vision_manual_fixture"
PHYSICAL_FEEDBACK = "/nero_guarded/feedback/joint_states"
JOINT_STATE_TYPE = "sensor_msgs/msg/JointState"
SERVO_STATUS_TYPE = "moveit_msgs/msg/ServoStatus"
TRAJECTORY_TYPE = "trajectory_msgs/msg/JointTrajectory"
CONTROLLER_STATE_TYPE = "control_msgs/msg/JointTrajectoryControllerState"
PLANNING_SCENE_TYPE = "moveit_msgs/msg/PlanningScene"
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
    def scene_topic(self):
        return self.servo_node + "/publish_planning_scene"

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
        self._live_feedback = None
        self._history = FeedbackHistory(horizon=max_batch_age+AGE,wall=wall)
        self._scene_service_stamp = None
        self._last_scene_update = None
        self._unwitnessed_change_since = None
        self.matched_scene_updates = 0
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
        # Upstream Servo 2.12 creates its state monitor on a generated
        # servo_node_private_<decimal> node. Pin the actual DDS endpoint,
        # not just the predictable part of its node name.
        def servo_state_reader(ep):
            return (isinstance(ep, Endpoint) and ep.message_type == JOINT_STATE_TYPE
                    and (ep.node == routes.servo_node
                         or re.fullmatch(re.escape(routes.servo_node) + r"_private_[0-9]+", ep.node)))
        if any(servo_state_reader(ep) for ep in subs.get(routes.synthetic_feedback_topic, ())):
            return "SERVO_FOLLOWS_INTERPOLATOR"
        readers = tuple(ep for ep in subs.get(routes.feedback_topic, ()) if servo_state_reader(ep))
        if len(readers) != 1 or type(readers[0].gid) is not bytes or not any(readers[0].gid):
            return "SERVO_FEEDBACK_SUBSCRIPTION_MISSING"
        reader_key = ("subscriber", routes.feedback_topic)
        if reader_key in self._pins and self._pins[reader_key] != readers[0].gid:
            return "SERVO_FEEDBACK_SUBSCRIPTION_REPLACED"
        pins[reader_key] = readers[0].gid
        # The maintained-scene publication comes from the same internal
        # PSM node as its joint-state subscription. Pin the publisher GID.
        scene_sources = pubs.get(routes.scene_topic, ())
        if (len(scene_sources)!=1 or scene_sources[0].node!=readers[0].node
                or scene_sources[0].message_type!=PLANNING_SCENE_TYPE
                or type(scene_sources[0].gid) is not bytes or not any(scene_sources[0].gid)):
            return "SCENE_SOURCE_UNVERIFIED"
        scene_gid=scene_sources[0].gid
        if routes.scene_topic in self._pins and self._pins[routes.scene_topic]!=scene_gid:
            return "SCENE_SOURCE_REPLACED"
        pins[routes.scene_topic]=scene_gid
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
        # GetPlanningScene does not timestamp its robot_state. Its q must
        # be an actual recently observed q from this bounded request window.
        # The live SDK comparison remains independent and uses fresh q.
        gid=pins[routes.feedback_topic]
        now=self.wall()
        earliest=now-(self.mono()-e.captured_mono)-AGE
        match=self._history.service_match(e.scene_q,gid,earliest=earliest,latest=now,
                        max_error=self.contract.scene_tracking_max_rad,
                        extra=(e.feedback_stamp,tuple(e.feedback_q),gid))
        if match is None:
            return "SERVO_STATE_NOT_OBSERVED"
        self._scene_service_stamp=match[0]
        self._pins.update(pins)
        return None

    def record_feedback(self, stamp, q, gid):
        """Refresh only measured-state evidence, never the scene/config lease."""
        with self.lock:
            if self._latched:
                return False
            if not finite(stamp) or not 0 <= self.wall() - stamp <= AGE or not vector7(q):
                return self._reject("FEEDBACK_STALE_OR_INVALID")
            if type(gid) is not bytes or not any(gid):
                return self._reject("SOURCE_UNVERIFIED")
            pin = self._pins.get(self.contract.routes.feedback_topic)
            if pin is not None and gid != pin:
                return self._reject("SOURCE_REPLACED")
            last = self._live_feedback
            if last is not None and gid == last[2]:
                if self._ever_ready and self.wall() - last[0] > AGE:
                    return self._reject("FEEDBACK_STALE")
                if stamp < last[0]:
                    return self._reject("FEEDBACK_REPLAY")
                if stamp == last[0] and tuple(q) != last[1]:
                    return self._reject("FEEDBACK_STAMP_CONFLICT")
            try:
                self._history.add(stamp,q,gid)
            except ValueError:
                return self._reject("FEEDBACK_HISTORY_INVALID")
            if (self._ever_ready and last is not None
                    and max(abs(x-y) for x,y in zip(last[1],q))>1e-7
                    and self._unwitnessed_change_since is None):
                self._unwitnessed_change_since=stamp
            self._live_feedback = (stamp, tuple(q), gid)
            return True

    def record_scene_update(self, stamp, q, gid):
        """Check the actual PSM publication against its exact input stamp.

        Return PENDING for DDS callback reordering. The adapter retries
        only while this original stamp is inside the bounded batch age.
        A published sample is evidence of an update, not a control command.
        """
        with self.lock:
            if self._latched:
                return "REJECTED"
            source=self._pins.get(self.contract.routes.scene_topic)
            feedback_source=self._pins.get(self.contract.routes.feedback_topic)
            if source is None or feedback_source is None:
                return "PENDING"
            if gid!=source:
                self._reject("SCENE_SOURCE_REPLACED")
                return "REJECTED"
            pending=self._unwitnessed_change_since
            if pending is not None and self.wall()-pending>self.max_batch_age:
                self._reject("SCENE_UPDATE_MISSING_DURING_CHANGE")
                return "REJECTED"
            if (not finite(stamp) or not 0<=self.wall()-stamp<=self.max_batch_age
                    or not vector7(q)):
                self._reject("SCENE_UPDATE_STALE_OR_INVALID")
                return "REJECTED"
            matched=self._history.at(stamp,feedback_source)
            if matched is None:
                return "PENDING"
            if max(abs(x-y) for x,y in zip(q,matched[1]))>self.contract.scene_tracking_max_rad:
                self._reject("SCENE_TIMESTAMP_STATE_MISMATCH")
                return "REJECTED"
            previous=self._last_scene_update
            if previous is not None and stamp<previous:
                self._reject("SCENE_UPDATE_REPLAY")
                return "REJECTED"
            if previous is None or stamp>previous:
                self.matched_scene_updates+=1
                self._last_scene_update=stamp
                if self._unwitnessed_change_since is not None and stamp>=self._unwitnessed_change_since:
                    # Preserve the first as-yet-unwitnessed change after
                    # this update, if motion continued in the meantime.
                    rows=[r for r in self._history.samples if r[2]==feedback_source and r[0]>=stamp]
                    self._unwitnessed_change_since=next(
                        (b[0] for a,b in zip(rows,rows[1:])
                         if max(abs(x-y) for x,y in zip(a[1],b[1]))>1e-7),None)
            return "MATCH"

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
            gid = self._pins[self.contract.routes.feedback_topic]
            if not self.record_feedback(evidence.feedback_stamp, evidence.feedback_q, gid):
                return False
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
                    or max(abs(a-b) for a,b in zip(feedback.q, self._live_feedback[1]))
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
            live = self._live_feedback
            if live is None or not 0 <= self.wall() - live[0] <= AGE:
                return self._reject("FEEDBACK_STALE")
            # A full scene readback is asynchronous evidence, not a
            # current joint command. Its state was matched within the
            # bounded request window in _validate(). Never compare
            # that old q to a newer q as if they were simultaneous.
            if (self._scene_service_stamp is None
                    or not 0<=self.wall()-self._scene_service_stamp<=self.max_batch_age+AGE):
                return self._reject("SCENE_WITNESS_EXPIRED")
            pending=self._unwitnessed_change_since
            if pending is not None and self.wall()-pending>self.max_batch_age:
                return self._reject("SCENE_UPDATE_MISSING_DURING_CHANGE")
            return True
