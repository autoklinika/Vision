"""Collision-scene fingerprint regression, no ROS node or hardware."""
from copy import deepcopy
import unittest

from geometry_msgs.msg import Pose
from moveit_msgs.msg import PlanningScene, CollisionObject, AllowedCollisionEntry
from shape_msgs.msg import SolidPrimitive
from vision_station.ros_nero_manual_pipeline import scene_fingerprint


class SceneFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.scene = PlanningScene()
        self.scene.robot_model_name = "agx_arm"
        obj = CollisionObject()
        obj.id = "fixture_box"
        obj.header.frame_id = "base_link"
        obj.pose.orientation.w = 1.
        obj.primitives = [SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[.1,.2,.3])]
        pose = Pose()
        pose.orientation.w = 1.
        obj.primitive_poses = [pose]
        self.scene.world.collision_objects = [obj]
        self.baseline = scene_fingerprint(self.scene)

    def test_dynamic_state_and_timestamps_are_not_configuration(self):
        s = deepcopy(self.scene)
        s.robot_state.joint_state.name = ["joint1"]
        s.robot_state.joint_state.position = [.3]
        s.robot_state.joint_state.header.stamp.sec = 123
        s.world.collision_objects[0].header.stamp.sec = 124
        s.name = "another display name"
        self.assertEqual(self.baseline, scene_fingerprint(s))

    def test_geometry_and_pose_changes_are_detected(self):
        s = deepcopy(self.scene)
        s.world.collision_objects[0].pose.position.z = .001
        self.assertNotEqual(self.baseline, scene_fingerprint(s))
        s = deepcopy(self.scene)
        s.world.collision_objects[0].primitives[0].dimensions = [.1,.2,.4]
        self.assertNotEqual(self.baseline, scene_fingerprint(s))

    def test_collision_permissions_are_detected(self):
        s = deepcopy(self.scene)
        acm = s.allowed_collision_matrix
        acm.entry_names = ["fixture_box", "link7"]
        acm.entry_values = [AllowedCollisionEntry(enabled=[False, True]),
                            AllowedCollisionEntry(enabled=[True, False])]
        self.assertNotEqual(self.baseline, scene_fingerprint(s))
        before = scene_fingerprint(s)
        acm.entry_values[0].enabled = [False,False]
        acm.entry_values[1].enabled = [False,False]
        self.assertNotEqual(before, scene_fingerprint(s))

    def test_world_removal_is_detected(self):
        s = deepcopy(self.scene)
        s.world.collision_objects = []
        self.assertNotEqual(self.baseline, scene_fingerprint(s))

if __name__ == "__main__":
    unittest.main()
