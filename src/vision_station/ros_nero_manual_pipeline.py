"""Read-only ROS adapter for the explicit manual-pipeline contract.

Only queries parameter, scene and controller readback services. It never
switches modes, sends Twist, modifies the scene or launches hardware.
The caller supplies an independently verified scene fingerprint and a
trusted bootstrap confirmation that TWIST was selected.
"""
from copy import deepcopy
from collections import deque
import re
import hashlib
import time

from .nero_manual import JOINTS, AGE, vector7
from .nero_manual_start import ControllerStart
from .nero_manual_pipeline import (
    Contract, Endpoint, Evidence, PipelineAuthority, JOINT_STATE_TYPE,
    JTC_TYPE, JSB_TYPE, MOCK_PLUGIN, PLANNING_SCENE_TYPE, CONTROLLER_STATE_TYPE,
)


def normalized_scene(scene):
    """Fingerprint full collision-relevant readback, not dynamic joint state.

    Header timestamps and cosmetic colors/names are not configuration.
    Keep all world geometry including octomap, attached objects, touch
    links, ACM, padding, scale and fixed transforms. Exact comparison may
    reject equivalent reordered representations; it cannot silently ignore
    new geometry or an allowed-collision change.
    """
    from sensor_msgs.msg import JointState, MultiDOFJointState
    from builtin_interfaces.msg import Time
    s = deepcopy(scene)
    s.name = ""
    s.is_diff = False
    s.robot_state.is_diff = False
    s.robot_state.joint_state = JointState()
    s.robot_state.multi_dof_joint_state = MultiDOFJointState()
    s.object_colors = []
    for obj in s.world.collision_objects:
        obj.header.stamp = Time()
    for obj in s.robot_state.attached_collision_objects:
        obj.object.header.stamp = Time()
        # A detach posture is part of the attached object's static record.
        obj.detach_posture.header.stamp = Time()
    for transform in s.fixed_frame_transforms:
        transform.header.stamp = Time()
    s.world.octomap.header.stamp = Time()
    s.world.octomap.octomap.header.stamp = Time()
    return s


def scene_fingerprint(scene):
    # CDR includes padding which is not guaranteed to have stable bytes.
    # The identity is over every normalized message field, not wire padding.
    import json
    from rosidl_runtime_py.convert import message_to_ordereddict
    fields = message_to_ordereddict(normalized_scene(scene))
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def joint_vector(state):
    # ROS generated float64[] fields are array.array, not Python lists.
    # Convert the sequence once; keep the strict finite/names validation.
    position = tuple(state.position)
    if len(state.name) != 7 or set(state.name) != set(JOINTS) or not vector7(position):
        raise ValueError("invalid seven-joint state")
    return tuple(float(position[state.name.index(name)]) for name in JOINTS)


def endpoint_node(ep):
    return ep.node_namespace.rstrip("/") + "/" + ep.node_name


def graph_evidence(node, routes):
    topics = (*routes.endpoints(), routes.twist, routes.controller_command,
              routes.synthetic_feedback_topic, routes.scene_topic)
    publishers = tuple((topic, tuple(Endpoint(endpoint_node(ep), ep.topic_type, bytes(ep.endpoint_gid))
                         for ep in node.get_publishers_info_by_topic(topic))) for topic in topics)
    subscribers = tuple((topic, tuple(Endpoint(endpoint_node(ep), ep.topic_type, bytes(ep.endpoint_gid))
                         for ep in node.get_subscriptions_info_by_topic(topic))) for topic in
                        (routes.feedback_topic, routes.synthetic_feedback_topic))
    return publishers, subscribers


def controller_evidence(controllers, hardware):
    """Only the official active JTC on a virtual interpolation system.

    No real ros2_control hardware plugin may coexist in this controller
    manager. The final physical port belongs to the guarded SDK owner.
    """
    rows = list(controllers.controller)
    names = {c.name for c in rows}
    expected = {name + "/position" for name in JOINTS}
    jtc = [c for c in rows if c.name == "arm_controller"]
    controllers_ok = (
        len(names) == len(rows) and names in ({"arm_controller"}, {"arm_controller", "joint_state_broadcaster"})
        and len(jtc) == 1 and jtc[0].state == "active" and jtc[0].type == JTC_TYPE
        and not jtc[0].is_chained and set(jtc[0].claimed_interfaces) == expected
        and all(c.name == "arm_controller" or (
            c.state == "active" and c.type == JSB_TYPE and not c.claimed_interfaces) for c in rows)
    )
    components = list(hardware.component)
    interpolator_only = (
        len(components) == 1 and components[0].plugin_name == MOCK_PLUGIN
        and components[0].state.label == "active"
        and {i.name for i in components[0].command_interfaces if i.is_claimed} == expected
        and {i.name for i in components[0].command_interfaces} == expected
    )
    return controllers_ok, interpolator_only


class RosPipelineMonitor:
    """Nonblocking observation, intended for a dedicated executor/callback.

    Call poll periodically from the observation executor, not the hardware
    TX critical section. Supply the immutable contract before construction.
    The separate native relay retains per-sample output GID enforcement.
    """
    def __init__(self, node, contract, *, twist_mode_confirmed,
                 wall=time.time, mono=time.monotonic):
        from rcl_interfaces.srv import GetParameters
        from moveit_msgs.srv import GetPlanningScene
        from moveit_msgs.msg import PlanningScene
        from controller_manager_msgs.srv import ListControllers, ListHardwareComponents
        from sensor_msgs.msg import JointState
        from control_msgs.msg import JointTrajectoryControllerState
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
        if not isinstance(contract, Contract) or not callable(twist_mode_confirmed):
            raise ValueError("explicit contract and trusted TWIST bootstrap required")
        self.node, self.contract = node, contract
        self.wall, self.mono = wall, mono
        self.observation_epoch = wall()
        self.mode = twist_mode_confirmed
        self.authority = PipelineAuthority(contract, wall=wall, mono=mono)
        self.latest = None
        self.controller_start = None
        self.last_state_readback = None
        self.pending_scene_updates = deque()
        self.last_timestamped_update = None
        self.last_received_scene_update = None
        self.futures = None
        self.started = 0.
        self.closed = False
        self.timer = None
        self.group = MutuallyExclusiveCallbackGroup()
        self.param_keys = [k for k, _ in contract.parameters]
        routes = contract.routes
        self.requests = [
            (node.create_client(GetParameters, routes.servo_node + "/get_parameters", callback_group=self.group),
             GetParameters.Request(names=self.param_keys)),
            (node.create_client(GetPlanningScene, routes.namespace + "/get_planning_scene", callback_group=self.group),
             GetPlanningScene.Request()),
            (node.create_client(ListControllers, routes.controller_manager + "/list_controllers", callback_group=self.group),
             ListControllers.Request()),
            (node.create_client(ListHardwareComponents, routes.controller_manager + "/list_hardware_components", callback_group=self.group),
             ListHardwareComponents.Request()),
        ]
        # All collision-relevant planning scene components.
        self.requests[1][1].components.components = 1023
        self.sub = node.create_subscription(JointState, routes.feedback_topic, self._feedback,
                                            qos_profile_sensor_data, callback_group=self.group)
        self.scene_sub = node.create_subscription(PlanningScene,routes.scene_topic,
                                        self._scene_update,10,callback_group=self.group)
        self.controller_sub = node.create_subscription(JointTrajectoryControllerState,
                    routes.controller_state,self._controller_state,1,callback_group=self.group)

    def _controller_state(self,msg,info):
        if self.closed:
            return
        try:
            routes=self.contract.routes
            rows=self.node.get_publishers_info_by_topic(routes.controller_state)
            if (len(rows)!=1 or endpoint_node(rows[0])!=routes.controller
                    or rows[0].topic_type!=CONTROLLER_STATE_TYPE):
                raise ValueError("unverified controller source")
            gid=bytes(rows[0].endpoint_gid)
            sample_gid=info.get("publisher_gid")
            if sample_gid is not None and bytes(sample_gid)!=gid:
                raise ValueError("unverified controller sample")
            if len(msg.joint_names)!=7 or set(msg.joint_names)!=set(JOINTS) or msg.multi_dof_joint_names:
                raise ValueError("invalid controller joint inventory")
            def ordered(values):
                values=tuple(values)
                if not vector7(values):
                    raise ValueError("invalid controller state")
                return tuple(values[msg.joint_names.index(n)] for n in JOINTS)
            stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9
            evidence=ControllerStart(stamp,gid,ordered(msg.feedback.positions),
                ordered(msg.reference.positions),ordered(msg.feedback.velocities),
                ordered(msg.reference.velocities))
            with self.authority.lock:
                last=self.controller_start
                if stamp<self.observation_epoch or (last is not None and stamp<=last.stamp):
                    return
                self.controller_start=evidence
        except Exception:
            with self.authority.lock:
                self.controller_start=None

    def start_aligned(self,feedback):
        # Read-only cached witness. Do not query or reset JTC inside the
        # hardware TX lock. A stale/unaligned idle controller is unavailable,
        # not a reason to send a physical correction to its reference.
        with self.authority.lock:
            sample=self.controller_start
            pin=self.authority._pins.get(self.contract.routes.controller_state)
            return (not self.closed and self.authority.agrees_with_feedback(feedback)
                    and sample is not None and sample.matches(feedback,now=self.wall(),expected_gid=pin))


    def start(self):
        if self.closed or self.timer is not None:
            raise RuntimeError("monitor already started or closed")
        self.timer = self.node.create_timer(.05, self.poll, callback_group=self.group)

    def _scene_update(self,msg,info):
        if self.closed:
            return
        try:
            routes=self.contract.routes
            rows=self.node.get_publishers_info_by_topic(routes.scene_topic)
            if (len(rows)!=1 or rows[0].topic_type!=PLANNING_SCENE_TYPE
                    or not (endpoint_node(rows[0])==routes.servo_node
                            or re.fullmatch(re.escape(routes.servo_node)+r"_private_[0-9]+",endpoint_node(rows[0])))):
                raise ValueError("unverified scene publisher")
            gid=bytes(rows[0].endpoint_gid)
            sample_gid=info.get("publisher_gid")
            if sample_gid is not None and bytes(sample_gid)!=gid:
                raise ValueError("unverified scene sample")
            # A full scene snapshot may be sent to a late subscriber
            # with the last motion stamp, even if the robot is stationary.
            # It is not a new joint-state update and never renews evidence.
            # Complete static scene identity is checked via the service.
            if not msg.is_diff:
                return
            state=msg.robot_state.joint_state
            # Geometry-only updates are still covered by complete scene
            # readback. They do not prove a joint-state update.
            if not state.name and not state.position:
                return
            stamp=state.header.stamp.sec+state.header.stamp.nanosec/1e9
            # The upstream PSM also emits un-stamped state snapshots.
            # They are not timing evidence, and must never renew a
            # verified motion update. The service readback is checked
            # independently against recent observed positions.
            if stamp==0.:
                return
            # A newly created subscriber can receive the previous PSM
            # state even after its first successful service readback.
            # Pre-subscription states cannot attest this new epoch. Do
            # not accept them, restamp them, or renew any deadline.
            if stamp < self.observation_epoch:
                if self.last_timestamped_update is not None:
                    self.authority.invalidate("SCENE_UPDATE_PREVIOUS_EPOCH")
                return
            if len(self.pending_scene_updates)>=16:
                raise ValueError("scene update backlog")
            self.last_received_scene_update={"sourceStamp":stamp,"receivedAgeS":self.wall()-stamp,
                                             "diff":msg.is_diff,"stateDiff":msg.robot_state.is_diff}
            self.pending_scene_updates.append((stamp,joint_vector(state),gid))
            self._match_scene_updates()
        except Exception:
            self.authority.invalidate("SCENE_UPDATE_UNVERIFIED")

    def _match_scene_updates(self):
        # Before the first complete graph/scene readback, the publisher
        # identity is not yet pinned. Discard old startup publications,
        # not evidence acquired during an active verified session.
        while self.pending_scene_updates:
            stamp,q,gid=self.pending_scene_updates[0]
            if not self.authority._ever_ready:
                self.pending_scene_updates.popleft()
                continue
            result=self.authority.record_scene_update(stamp,q,gid)
            if result=="PENDING":
                if self.wall()-stamp>self.authority.max_batch_age:
                    self.pending_scene_updates.popleft()
                    self.authority.invalidate("SCENE_INPUT_TIMESTAMP_NOT_OBSERVED")
                    continue
                break
            self.pending_scene_updates.popleft()
            if result=="MATCH":
                self.last_timestamped_update={"sourceStamp":stamp,"receivedAgeS":self.wall()-stamp}

    def _feedback(self, msg, info):
        if self.closed:
            return
        try:
            expected = self.contract.routes
            rows = self.node.get_publishers_info_by_topic(expected.feedback_topic)
            if (len(rows) != 1 or endpoint_node(rows[0]) != expected.feedback_node
                    or rows[0].topic_type != JOINT_STATE_TYPE):
                raise ValueError("feedback source")
            gid = info.get("publisher_gid")
            # Some Jazzy RMW bindings omit sample GID; in that case this is
            # graph evidence only. The physical ManualEngine independently
            # checks fresh SDK feedback; never claim cryptographic attribution.
            if gid is not None and bytes(gid) != bytes(rows[0].endpoint_gid):
                raise ValueError("feedback sample source")
            stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
            if not 0 <= self.wall() - stamp <= AGE:
                raise ValueError("feedback age")
            self.latest = (stamp, joint_vector(msg), bytes(rows[0].endpoint_gid))
            self.authority.record_feedback(*self.latest)
            self._match_scene_updates()
        except Exception:
            self.latest = None
            self.authority.invalidate("FEEDBACK_UNVERIFIED")

    def poll(self):
        from rclpy.parameter import parameter_value_to_python
        if self.closed:
            return
        self._match_scene_updates()
        now = self.mono()
        if self.futures is not None:
            if now - self.started > .4:
                for (client, _), future in zip(self.requests, self.futures):
                    if not future.done():
                        client.remove_pending_request(future)
                        future.cancel()
                self.futures = None
                self.authority.invalidate("READBACK_TIMEOUT")
            elif all(f.done() for f in self.futures):
                pending, self.futures = self.futures, None
                try:
                    par, scene, ctrl, hw = [f.result() for f in pending]
                    if len(par.values) != len(self.param_keys) or self.latest is None:
                        raise ValueError("incomplete readback")
                    values = tuple(zip(self.param_keys, map(parameter_value_to_python, par.values)))
                    stamp, q, gid = self.latest
                    pubs, subs = graph_evidence(self.node, self.contract.routes)
                    eps = dict(pubs).get(self.contract.routes.feedback_topic, ())
                    if len(eps) != 1 or eps[0].gid != gid:
                        raise ValueError("feedback source replaced")
                    controllers_ok, interpolator_only = controller_evidence(ctrl, hw)
                    js = scene.scene.robot_state.joint_state
                    sq = joint_vector(js)
                    self.last_state_readback = {
                        "sceneStamp":js.header.stamp.sec+js.header.stamp.nanosec/1e9,
                        "feedbackStamp":stamp,
                        "feedbackAgeS":self.wall()-stamp,
                        "batchAgeS":self.mono()-self.started,
                        "sceneVsLatestRad":max(abs(x-y) for x,y in zip(sq,q)),
                    }
                    self.authority.observe(Evidence(
                        captured_mono=self.started, feedback_stamp=stamp, feedback_q=q,
                        scene_q=sq,
                        scene_digest=scene_fingerprint(scene.scene), parameters=values,
                        publishers=pubs, subscribers=subs, controllers_ok=controllers_ok,
                        interpolator_only=interpolator_only, twist_mode_confirmed=self.mode() is True))
                except Exception:
                    self.authority.invalidate("READBACK_INVALID")
        # No overlapping service batch, no service call from the TX lock.
        if self.futures is None:
            if all(client.service_is_ready() for client, _ in self.requests):
                self.started = self.mono()
                self.futures = [client.call_async(req) for client, req in self.requests]
            else:
                self.authority.invalidate("READBACK_SERVICE_UNAVAILABLE")

    def __call__(self):
        return not self.closed and self.authority()

    def agrees_with_feedback(self, feedback):
        return not self.closed and self.authority.agrees_with_feedback(feedback)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.authority.invalidate("MONITOR_CLOSED")
        if self.timer is not None:
            self.timer.cancel()
            self.node.destroy_timer(self.timer)
            self.timer = None
        if self.futures is not None:
            for (client, _), future in zip(self.requests, self.futures):
                if not future.done():
                    client.remove_pending_request(future)
                    future.cancel()
            self.futures = None
        self.node.destroy_subscription(self.sub)
        self.node.destroy_subscription(self.scene_sub)
        self.node.destroy_subscription(self.controller_sub)
        for client, _ in self.requests:
            self.node.destroy_client(client)
