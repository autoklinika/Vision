"""Independent final audit of numerical pose validation and rigid transforms."""
from dataclasses import asdict, replace
import math
import unittest

import test_moveit_adapter as fixture
from vision_core import GateError
from vision_planner.moveit_adapter import (
    MoveItAdapter, camera_to_link, link_to_camera, validate_segment, _hash,
)


def rotation_z(angle, scale=1.):
    return (0., 0., math.sin(angle/2)*scale, math.cos(angle/2)*scale)


class FinalMotionAuditTests(unittest.TestCase):
    def setUp(self):
        self.rpc = fixture.FakeMoveIt()
        self.config = fixture.config(orientation_tolerance_rad=.0001)
        self.adapter = MoveItAdapter(self.config, self.rpc, fixture.types(),
                                     clock=lambda: 10., monotonic=lambda: 1.)

    def plan(self):
        return self.adapter.plan_segment('view_001', 'world', (100., 0., 1000.),
            (0., 0., 0., 1.), (0., 0.), self.adapter.snapshot().scene_hash)

    def fk_orientation(self, quaternion):
        def mutate(kind, response):
            if kind == 'fk':
                q = response.pose_stamped[0].pose.orientation
                q.x, q.y, q.z, q.w = quaternion
            return response
        self.rpc.mutate = mutate

    def test_nonexact_unit_fk_cannot_hide_fifty_times_allowed_orientation_error(self):
        # Norm error is accepted by the public quaternion contract. Raw dot
        # exceeds one and formerly hid a .005 rad error under a .0001 limit.
        self.fk_orientation(rotation_z(.005, 1.000009))
        with self.assertRaisesRegex(GateError, 'FK camera pose'): self.plan()

    def test_receipt_validation_normalizes_copies_before_angle_comparison(self):
        segment = replace(self.plan(), fk_camera_quaternion=rotation_z(.005, 1.000009))
        body = asdict(segment); body.pop('digest')
        segment = replace(segment, digest=_hash(body))
        with self.assertRaisesRegex(GateError, 'FK target'): validate_segment(segment, self.config)
        # The input receipt itself remains byte-for-byte unchanged.
        self.assertEqual(segment.fk_camera_quaternion, rotation_z(.005, 1.000009))

    def test_tiny_resolvable_rotation_does_not_disappear_in_dot_roundoff(self):
        cfg = replace(self.config, orientation_tolerance_rad=1e-9)
        adapter = MoveItAdapter(cfg, self.rpc, fixture.types(), clock=lambda:10., monotonic=lambda:1.)
        with self.assertRaisesRegex(GateError, 'FK camera pose'):
            adapter._check_pose(((0.,0.,0.),rotation_z(1e-8)),
                                ((0.,0.,0.),rotation_z(0.)))

    def test_antipodal_quaternions_remain_equivalent(self):
        self.fk_orientation((0., 0., 0., -1.000009))
        result = self.plan()
        validate_segment(result, self.config)

    def test_tool_transform_normalizes_both_quaternions_without_scaling_translation(self):
        camera_q = rotation_z(.6)
        tool_q = (math.sin(.2), 0., 0., math.cos(.2))
        camera_p, offset = (300., -400., 800.), (20., 30., 40.)
        expected = camera_to_link(camera_p, camera_q, offset, tool_q)
        scaled_camera = tuple(v*1.000009 for v in camera_q)
        scaled_tool = tuple(v*1.000009 for v in tool_q)
        actual = camera_to_link(camera_p, scaled_camera, offset, scaled_tool)
        for a, b in zip(actual[0]+actual[1], expected[0]+expected[1]):
            self.assertAlmostEqual(a, b, places=10)
        self.assertAlmostEqual(math.hypot(*actual[1]), 1., places=14)
        restored = link_to_camera(*actual, offset, scaled_tool)
        for a, b in zip(restored[0]+restored[1], camera_p+camera_q):
            self.assertAlmostEqual(a, b, places=10)

    def test_link_to_camera_uses_rotation_not_quaternion_scale(self):
        q = rotation_z(.6)
        offset = (9000., 3000., 4000.)
        expected = link_to_camera((10.,20.,30.), q, offset, (0.,0.,0.,1.))
        actual = link_to_camera((10.,20.,30.), tuple(v*.999991 for v in q),
                                offset, (0.,0.,0.,1.000009))
        for a, b in zip(actual[0]+actual[1], expected[0]+expected[1]):
            self.assertAlmostEqual(a, b, places=9)


if __name__ == '__main__':
    unittest.main()
