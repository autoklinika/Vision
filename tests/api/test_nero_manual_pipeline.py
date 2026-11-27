from dataclasses import replace
import unittest
from types import SimpleNamespace as NS

from vision_station.nero_manual import Feedback, JOINTS
from vision_station.nero_manual_pipeline import (
    Contract, Endpoint, Evidence, PipelineAuthority, Routes, TRAJECTORY_TYPE, TWIST_TYPE,
)
from vision_station.ros_nero_manual_pipeline import controller_evidence


class Clock:
    now = 100.
    def time(self):
        return self.now


def params(routes):
    return tuple(sorted({
        **routes.required_servo_parameters(),
        "robot_description": "<robot name='fixture'/>",
        "robot_description_semantic": "<robot name='fixture'/>",
        **{"moveit_servo."+k:v for k,v in {
            "publish_period": .02, "incoming_command_timeout": .15,
            "collision_check_rate": 10.,
            "self_collision_proximity_threshold": .01,
            "scene_collision_proximity_threshold": .02,
            "scale.linear": .005, "scale.rotational": .05, "scale.joint": .2,
            "check_octomap_collisions": False, "use_smoothing": True,
            "apply_twist_commands_about_ee_frame": True,
        }.items()},
    }.items()))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.routes = Routes.physical()
        self.c = Clock()
        self.contract = Contract(self.routes, "a"*64, params(self.routes), .002)
        self.guard = PipelineAuthority(self.contract, wall=self.c.time, mono=self.c.time)
        publishers = tuple((topic, (Endpoint(node, kind, bytes([i+1])),))
                           for i,(topic,(node,kind)) in enumerate(self.routes.endpoints().items()))
        publishers += (
            (self.routes.twist,(Endpoint(self.routes.feedback_node,TWIST_TYPE,b"\x77"),)),
            (self.routes.controller_command,(Endpoint("/vision_servo_sample_relay",TRAJECTORY_TYPE,b"\x88"),)),
        )
        self.e = Evidence(self.c.now, self.c.now-.01, (0.,)*7, (0.,)*7,
                          self.contract.scene_digest, self.contract.parameters,
                          publishers,
                          ((self.routes.feedback_topic, ((self.routes.servo_node, "sensor_msgs/msg/JointState"),)),
                           (self.routes.synthetic_feedback_topic, ())),
                          True, True, True)

    def test_physical_feedback_not_mock(self):
        with self.assertRaises(ValueError):
            Routes(self.routes.namespace, self.routes.synthetic_feedback_topic, self.routes.feedback_node)
        wrong = dict(self.contract.parameters)
        wrong["moveit_servo.joint_topic"] = self.routes.synthetic_feedback_topic
        with self.assertRaises(ValueError):
            replace(self.contract, parameters=tuple(wrong.items()))
        wrong = dict(self.contract.parameters)
        wrong["moveit_servo.check_collisions"] = False
        with self.assertRaises(ValueError):
            replace(self.contract, parameters=tuple(wrong.items()))

    def test_not_ready_without_complete_evidence(self):
        self.assertFalse(self.guard())
        self.assertFalse(self.guard.observe(replace(self.e, twist_mode_confirmed=False)))
        self.assertTrue(self.guard.observe(self.e))
        self.assertTrue(self.guard())

    def test_scene_change_latches(self):
        self.assertTrue(self.guard.observe(self.e))
        self.assertFalse(self.guard.observe(replace(self.e, scene_digest="b"*64)))
        self.assertEqual(self.guard.reason, "SCENE_CHANGED")
        self.assertFalse(self.guard.observe(self.e))
        self.assertFalse(self.guard())

    def test_parameters_changed(self):
        self.assertTrue(self.guard.observe(self.e))
        p = dict(self.e.parameters)
        p["moveit_servo.check_collisions"] = False
        self.assertFalse(self.guard.observe(replace(self.e, parameters=tuple(p.items()))))
        self.assertEqual(self.guard.reason, "PARAMETERS_CHANGED")

    def test_controller_not_interpolator(self):
        self.assertFalse(self.guard.observe(replace(self.e, interpolator_only=False)))
        self.assertEqual(self.guard.reason, "CONTROLLER_INVALID")

    def test_feedback_source_replaced(self):
        self.assertTrue(self.guard.observe(self.e))
        p = dict(self.e.publishers)
        topic = self.routes.feedback_topic
        p[topic] = (replace(p[topic][0], gid=b"\x99"),)
        self.assertFalse(self.guard.observe(replace(self.e, publishers=tuple(p.items()))))
        self.assertEqual(self.guard.reason, "SOURCE_REPLACED")

    def test_duplicate_feedback_source(self):
        self.assertTrue(self.guard.observe(self.e))
        p = dict(self.e.publishers)
        topic = self.routes.feedback_topic
        p[topic] = p[topic] + (Endpoint("/unexpected", "sensor_msgs/msg/JointState", b"\x99"),)
        self.assertFalse(self.guard.observe(replace(self.e, publishers=tuple(p.items()))))
        self.assertEqual(self.guard.reason, "SOURCE_MISSING_OR_DUPLICATE")

    def test_servo_must_not_subscribe_to_mock_joint_states(self):
        s = dict(self.e.subscribers)
        s[self.routes.synthetic_feedback_topic] = ((self.routes.servo_node, "sensor_msgs/msg/JointState"),)
        self.assertFalse(self.guard.observe(replace(self.e, subscribers=tuple(s.items()))))
        self.assertEqual(self.guard.reason, "SERVO_FOLLOWS_INTERPOLATOR")

    def test_scene_state_must_match_source(self):
        self.assertFalse(self.guard.observe(replace(self.e, scene_q=(.01,)*7)))
        self.assertEqual(self.guard.reason, "SERVO_STATE_NOT_FEEDBACK")

    def test_stale_feedback_no_rearm(self):
        self.assertTrue(self.guard.observe(self.e))
        self.c.now += .16
        self.assertFalse(self.guard())
        self.assertEqual(self.guard.reason, "FEEDBACK_STALE")
        fresh = replace(self.e, captured_mono=self.c.now, feedback_stamp=self.c.now)
        self.assertFalse(self.guard.observe(fresh))

    def test_stale_batch_no_rearm(self):
        self.assertTrue(self.guard.observe(self.e))
        self.c.now += .51
        self.assertFalse(self.guard())
        self.assertEqual(self.guard.reason, "BATCH_STALE")

    def test_actual_sdk_disagreement_latches(self):
        self.assertTrue(self.guard.observe(self.e))
        t=self.c.now-.005
        f=Feedback((0.,)*7,(0.,)*7,t,t,0,0,1,(64,)*7,(t,)*7,(t,)*7)
        self.assertTrue(self.guard.agrees_with_feedback(f))
        self.assertFalse(self.guard.agrees_with_feedback(replace(f,q=(.003,)*7)))
        self.assertEqual(self.guard.reason, "SDK_STATE_MISMATCH")
        self.assertFalse(self.guard.observe(self.e))

    def test_command_endpoints_required_before_ready(self):
        p = dict(self.e.publishers)
        p[self.routes.twist] = ()
        self.assertFalse(self.guard.observe(replace(self.e, publishers=tuple(p.items()))))
        self.assertEqual(self.guard.reason, "COMMAND_SOURCE_UNVERIFIED")

    def test_command_source_pins(self):
        self.assertTrue(self.guard.observe(self.e))
        p=dict(self.e.publishers)
        p[self.routes.twist]=(Endpoint(self.routes.feedback_node,TWIST_TYPE,b"\x77"),)
        p[self.routes.controller_command]=(Endpoint("/vision_servo_sample_relay",TRAJECTORY_TYPE,b"\x88"),)
        self.assertTrue(self.guard.observe(replace(self.e,publishers=tuple(p.items()))))
        p[self.routes.controller_command]=()
        self.assertFalse(self.guard.observe(replace(self.e,publishers=tuple(p.items()))))
        self.assertEqual(self.guard.reason,"COMMAND_SOURCE_REPLACED")

    def test_fixture_cannot_name_physical_source(self):
        with self.assertRaises(ValueError):
            Routes("/vision_manual_fixture",self.routes.feedback_topic,self.routes.feedback_node)

    def test_controller_readback_rejects_real_hardware_and_extra_controller(self):
        names=[j+"/position" for j in JOINTS]
        jtc=NS(name="arm_controller", state="active", type="joint_trajectory_controller/JointTrajectoryController",
               is_chained=False, claimed_interfaces=names)
        mock=NS(plugin_name="mock_components/GenericSystem",state=NS(label="active"),
                command_interfaces=[NS(name=n,is_claimed=True) for n in names])
        self.assertEqual(controller_evidence(NS(controller=[jtc]),NS(component=[mock])),(True,True))
        self.assertEqual(controller_evidence(NS(controller=[jtc]),NS(component=[NS(**{**vars(mock),"plugin_name":"real"})])),(True,False))
        self.assertEqual(controller_evidence(NS(controller=[jtc,NS(name="extra")]),NS(component=[mock])),(False,True))


if __name__ == "__main__":
    unittest.main()
