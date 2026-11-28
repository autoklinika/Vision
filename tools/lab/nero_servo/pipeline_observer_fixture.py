"""Software-only independent observation for the GenericSystem smoke fixture."""
from copy import deepcopy
import time

from vision_station.nero_manual_pipeline import Contract, Routes
from vision_station.ros_nero_manual_pipeline import (
    RosPipelineMonitor, joint_vector, scene_fingerprint,
)


class ObservationFixture:
    def __init__(self, node, params, station_candidate=None, profile=None):
        from sensor_msgs.msg import JointState
        from moveit_msgs.srv import GetPlanningScene
        from moveit_msgs.msg import PlanningScene
        self.node = node
        self.params = params
        self.station_candidate = station_candidate
        self.profile = profile
        self.routes = Routes.fixture()
        self.msg_type = JointState
        self.pub = node.create_publisher(JointState, self.routes.feedback_topic, 10)
        self.get = node.create_client(GetPlanningScene, self.routes.namespace + "/get_planning_scene")
        self.request = GetPlanningScene.Request()
        self.request.components.components = 1023
        self.scene_pub = node.create_publisher(PlanningScene,
                    params["moveit_servo"].get("monitored_planning_scene_topic","/planning_scene"),10)
        self.monitor = None
        self.observer_node = None
        self.observer_executor = None
        self.observer_thread = None
        self.observer_stop = None
        self.observer_error = None
        self.enabled = True
        self.override = None
        self.last = None
        self.next_publish = 0.
        self.last_published_stamp = None
        self.confirmed_twist = False
        self.scene = None
        self.contract = None

    def receive_mock_state(self, state):
        self.last = state

    def tick(self):
        if not self.enabled or self.last is None or time.monotonic() < self.next_publish:
            return
        self.next_publish = time.monotonic() + .02
        q = tuple(self.override) if self.override is not None else joint_vector(self.last)
        m = self.msg_type()
        m.name = ["joint"+str(i) for i in range(1,8)]
        m.position = q
        # The override is a deliberate synthetic measurement. Otherwise
        # preserve the actual mock-state timestamp and never restamp cached
        # controller positions as fresh observations.
        m.header.stamp = (self.node.get_clock().now().to_msg() if self.override is not None
                          else self.last.header.stamp)
        stamp = (m.header.stamp.sec,m.header.stamp.nanosec)
        if self.last_published_stamp is not None and stamp<=self.last_published_stamp:
            return
        self.last_published_stamp=stamp
        self.pub.publish(m)

    def read_scene(self, spin):
        deadline = time.monotonic()+5.
        while not self.get.service_is_ready() and time.monotonic() < deadline:
            spin(.05)
        if not self.get.service_is_ready():
            raise RuntimeError("fixture planning scene service missing")
        f = self.get.call_async(self.request)
        while not f.done() and time.monotonic() < deadline:
            spin(.02)
        if not f.done():
            raise RuntimeError("fixture planning scene readback timed out")
        return f.result().scene

    def prepare(self, spin, pose):
        from geometry_msgs.msg import Pose
        from moveit_msgs.msg import PlanningScene, CollisionObject
        from shape_msgs.msg import SolidPrimitive
        # Demonstrate independent state while the mock controller is stationary.
        q = list(pose)
        q[0] += .01
        self.override = q
        spin(.5)
        observed = joint_vector(self.read_scene(spin).robot_state.joint_state)
        assert max(abs(a-b) for a,b in zip(observed,q)) < 1e-6, observed
        assert max(abs(a-b) for a,b in zip(joint_vector(self.last),pose)) < 1e-6
        print("INDEPENDENT_OBSERVED_STATE_PASS", flush=True)
        self.override = None
        spin(.4)

        old = self.read_scene(spin)
        assert not old.world.collision_objects
        assert not old.robot_state.attached_collision_objects
        if self.station_candidate is None:
            # The original synthetic obstacle regression.
            obj = CollisionObject(id="observer_fixture_box")
            obj.header.frame_id = "world"
            obj.pose.position.x = 3.
            obj.pose.orientation.w = 1.
            obj.primitives = [SolidPrimitive(type=SolidPrimitive.BOX,dimensions=[.1,.1,.1])]
            obj.primitive_poses = [Pose()]
            obj.primitive_poses[0].orientation.w = 1.
            scene = PlanningScene(is_diff=True)
            scene.robot_state.is_diff = True
            scene.world.collision_objects = [obj]
        else:
            from rclpy.serialization import deserialize_message
            scene=deserialize_message(self.station_candidate.scene,PlanningScene)
            assert scene.is_diff and scene.robot_state.is_diff
            assert len(scene.world.collision_objects)==1
            assert len(scene.robot_state.attached_collision_objects)==1
            assert not scene.robot_state.joint_state.name
            assert not scene.allowed_collision_matrix.entry_names
            assert not scene.allowed_collision_matrix.default_entry_names
            assert not scene.world.octomap.octomap.data
        deadline = time.monotonic()+5.
        while self.scene_pub.get_subscription_count() != 1 and time.monotonic()<deadline:
            spin(.05)
        assert self.scene_pub.get_subscription_count() == 1
        self.scene_pub.publish(scene)
        spin(.45)
        actual = self.read_scene(spin)
        if self.station_candidate is None:
            assert len(actual.world.collision_objects)==1
            result = actual.world.collision_objects[0]
            assert result.id == obj.id and result.primitives == obj.primitives
            assert abs(result.pose.position.x+result.primitive_poses[0].position.x-3.) < 1e-8
            assert not actual.robot_state.attached_collision_objects
        else:
            self.verify_station_geometry(scene,actual)
            print("FULL_STATION_SCENE_READBACK_PASS",flush=True)
        assert actual.allowed_collision_matrix == old.allowed_collision_matrix
        assert max(abs(a-b) for a,b in zip(joint_vector(actual.robot_state.joint_state),pose)) < 1e-6
        self.scene = actual
        # Independently reread the entire static scene multiple times.
        from vision_station.ros_nero_manual_pipeline import normalized_scene
        for _ in range(3):
            spin(.15)
            later = self.read_scene(spin)
            assert normalized_scene(actual) == normalized_scene(later)
            assert scene_fingerprint(actual) == scene_fingerprint(later)
        print("SCENE_STABILITY_PASS",flush=True)

        params = dict(self.routes.required_servo_parameters())
        params.update({k:self.params[k] for k in ("robot_description","robot_description_semantic")})
        servo = self.params["moveit_servo"]
        for key in ("publish_period","incoming_command_timeout","collision_check_rate",
                    "self_collision_proximity_threshold","scene_collision_proximity_threshold",
                    "check_octomap_collisions","use_smoothing","apply_twist_commands_about_ee_frame"):
            params["moveit_servo."+key] = servo[key]
        for key in ("linear","rotational","joint"):
            params["moveit_servo.scale."+key] = servo["scale"][key]
        # Fixture-only receipt based on its deliberately constructed scene.
        if self.profile is None:
            self.contract = Contract(self.routes, scene_fingerprint(actual),
                                     tuple(sorted(params.items())), .005)
        else:
            from vision_station.nero_manual_composition import contract_for_loaded_model
            self.contract=contract_for_loaded_model(self.routes,self.profile,self.params,scene_fingerprint(actual))
        for topic in (self.routes.feedback_topic,self.routes.synthetic_feedback_topic):
            print("OBSERVED_SUBSCRIBERS",topic,[(e.node_namespace,e.node_name,e.topic_type)
                  for e in self.node.get_subscriptions_info_by_topic(topic)],flush=True)
        self.start_monitor()
        self.wait_ready(spin)

    @staticmethod
    def verify_station_geometry(expected,actual):
        # Compare composed primitive transforms instead of assuming MoveIt
        # preserves the decomposition between object pose and shape pose.
        import numpy as np
        def pos(p):
            return np.array([p.x,p.y,p.z])
        def rot(p):
            q=np.array([p.x,p.y,p.z,p.w])
            assert abs(np.linalg.norm(q)-1.)<1e-6
            x,y,z,w=q/np.linalg.norm(q)
            return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                             [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                             [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        def check(a,b):
            assert a.id==b.id and a.header.frame_id==b.header.frame_id
            assert a.primitives==b.primitives
            assert not a.meshes and not b.meshes and not a.planes and not b.planes
            assert not a.subframe_names and not b.subframe_names
            assert len(a.primitive_poses)==len(b.primitive_poses)==len(a.primitives)
            for x,y in zip(a.primitive_poses,b.primitive_poses):
                ap=pos(a.pose.position)+rot(a.pose.orientation)@pos(x.position)
                bp=pos(b.pose.position)+rot(b.pose.orientation)@pos(y.position)
                assert np.linalg.norm(ap-bp)<1e-8
                assert np.max(np.abs(rot(a.pose.orientation)@rot(x.orientation)
                    -rot(b.pose.orientation)@rot(y.orientation)))<1e-7
        assert len(actual.world.collision_objects)==len(expected.world.collision_objects)==1
        assert len(actual.robot_state.attached_collision_objects)==len(expected.robot_state.attached_collision_objects)==1
        table=expected.world.collision_objects[0]
        assert table.id=="vision_table_1500x780_candidate"
        check(table,actual.world.collision_objects[0])
        a=expected.robot_state.attached_collision_objects[0]
        b=actual.robot_state.attached_collision_objects[0]
        assert a.link_name==b.link_name=="link7"
        assert list(a.touch_links)==list(b.touch_links)==["flange_link"]
        assert len(a.object.primitives)==3
        check(a.object,b.object)
        acm=actual.allowed_collision_matrix
        if b.object.id in acm.default_entry_names:
            assert not acm.default_entry_values[acm.default_entry_names.index(b.object.id)]
        if b.object.id in acm.entry_names:
            i=acm.entry_names.index(b.object.id)
            for other in ("link5","link6",table.id):
                if other in acm.entry_names:
                    assert not acm.entry_values[i].enabled[acm.entry_names.index(other)]
        assert not actual.world.octomap.octomap.data

    def start_monitor(self):
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from threading import Event, Thread
        self.observer_node = rclpy.create_node("pipeline_observer",namespace=self.routes.namespace,
                                context=self.node.context,start_parameter_services=False)
        self.observer_executor = SingleThreadedExecutor(context=self.node.context)
        self.observer_executor.add_node(self.observer_node)
        self.monitor = RosPipelineMonitor(self.observer_node,self.contract,
                             twist_mode_confirmed=lambda:self.confirmed_twist)
        self.monitor.start()
        self.observer_stop=Event()
        self.observer_error=None
        def observe():
            try:
                while not self.observer_stop.is_set():
                    self.observer_executor.spin_once(timeout_sec=.02)
            except Exception as exc:
                self.observer_error=exc
                self.monitor.authority.invalidate("OBSERVER_EXECUTOR_FAILED")
        self.observer_thread = Thread(target=observe,daemon=True)
        self.observer_thread.start()

    def stop_monitor(self):
        if self.observer_executor is not None:
            # Join before destroying the ROS executor guard conditions.
            self.observer_stop.set()
            self.observer_thread.join(timeout=3.)
            if self.observer_thread.is_alive():
                raise RuntimeError("observer executor did not stop")
            self.observer_executor.remove_node(self.observer_node)
            self.observer_executor.shutdown(timeout_sec=2.)
        if self.monitor is not None:
            self.monitor.close()
        if self.observer_node is not None:
            self.observer_node.destroy_node()
        self.observer_executor = self.observer_thread = self.observer_node = self.monitor = None
        if self.observer_error is not None:
            raise RuntimeError("observer executor failed") from self.observer_error

    def wait_ready(self, spin):
        deadline = time.monotonic()+8.
        while time.monotonic()<deadline:
            spin(.05)
            if self.monitor():
                spin(.25)
                if self.monitor():
                    print("PIPELINE_MONITOR_VERIFIED",flush=True)
                    return
            if self.monitor.authority._latched:
                break
        print("STARTUP_READBACK_DIAGNOSTIC",self.monitor.last_state_readback,self.monitor.last_received_scene_update,flush=True)
        raise RuntimeError("pipeline monitor rejected fixture: "+self.monitor.authority.reason)

    def check(self):
        if self.monitor is not None:
            e=self.monitor.authority._evidence
            live=self.monitor.authority._live_feedback
            if not self.monitor():
                print("READBACK_DIAGNOSTIC",self.monitor.last_state_readback,self.monitor.last_received_scene_update,flush=True)
                if e is not None and live is not None:
                    print("CACHED_SCENE_VS_LIVE",max(abs(x-y) for x,y in zip(e.scene_q,live[1])),
                          "scene_batch_age",time.monotonic()-e.captured_mono,
                          "live_age",time.time()-live[0],flush=True)
                raise RuntimeError("pipeline authority lost: "+self.monitor.authority.reason)

    def test_loss(self, spin):
        self.check()
        self.enabled=False
        spin(.5)
        assert not self.monitor(), "lost observation admitted"
        reason=self.monitor.authority.reason
        assert reason in ("FEEDBACK_STALE","FEEDBACK_UNVERIFIED","READBACK_INVALID","FEEDBACK_STALE_OR_INVALID"), reason
        self.enabled=True
        spin(.5)
        assert not self.monitor(), "observer automatically rearmed"
        print("FEEDBACK_LOSS_LATCH_PASS",reason,flush=True)
        # Reconstruct only in this test fixture, to exercise another fault.
        self.stop_monitor()
        self.start_monitor()
        self.wait_ready(spin)

        from moveit_msgs.msg import PlanningScene
        altered=PlanningScene(is_diff=True)
        altered.robot_state.is_diff=True
        moved=deepcopy(self.scene.world.collision_objects[0])
        moved.pose.position.x+=.1
        altered.world.collision_objects=[moved]
        self.scene_pub.publish(altered)
        spin(.6)
        assert not self.monitor()
        assert self.monitor.authority.reason=="SCENE_CHANGED", self.monitor.authority.reason
        print("SCENE_CHANGE_LATCH_PASS",flush=True)

    def close(self):
        self.stop_monitor()
