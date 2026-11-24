"""Synthetic neutral backend for orchestration tests, never a runtime adapter."""
from dataclasses import asdict

from vision_planner import (AdapterConfig, JointLimit, SceneSnapshot, SegmentResult,
                            TrajectoryPoint, MotionSetup, SceneLease)
from vision_planner.coordinator import digest


class SyntheticBackend:
    def __init__(self, fixture):
        self.fixture = fixture
        self.config = AdapterConfig('synthetic_arm', 'synthetic_tip',
            (JointLimit('joint1', -2, 2, 2, 3), JointLimit('joint2', -2, 2, 2, 3)),
            (0, 0, 0), (0, 0, 0, 1), 'v1', 'v1')
        self.calls = []
        self.transform_snapshot = lambda snapshot: snapshot
        self.transform_segment = lambda segment: segment
        self.scene_hash = 'c' * 64
        self.positions = (0., 0.)

    def snapshot(self):
        self.calls.append('snapshot')
        now = self.fixture.case.now
        return self.transform_snapshot(SceneSnapshot(self.scene_hash, self.config.joint_names,
            self.positions, (0., 0.), now - .02, 'synthetic_robot',
            'moveit-scene:sha256:' + self.scene_hash, now))

    def plan_segment(self, view_id, frame_id, xyz, quaternion, start, scene_hash):
        self.calls.append(view_id)
        started = self.fixture.case.now
        before = self.snapshot()
        goal = tuple(x + .02 for x in start)
        middle = tuple(x + .01 for x in start)
        points = (TrajectoryPoint(0., start, (0., 0.), (.02, .02)),
                  TrajectoryPoint(1., middle, (.02, .02), (0., 0.)),
                  TrajectoryPoint(2., goal, (0., 0.), (-.02, -.02)))
        self.fixture.case.now += .1
        after = self.snapshot()
        data = dict(view_id=view_id, frame_id=frame_id, camera_xyz_mm=xyz,
                    camera_quaternion=quaternion, requested_start_joints=start,
                    ik_joints=goal, points=points, scene_before=before, scene_after=after,
                    config_hash=self.config.digest, started_at=started,
                    completed_at=self.fixture.case.now, fk_camera_xyz_mm=xyz,
                    fk_camera_quaternion=quaternion, checked_state_count=3)
        # Uses the production segment canonicalization, with independently
        # constructed fixture geometry and time series.
        result = SegmentResult(**data, digest='')
        body = asdict(result); body.pop('digest')
        return self.transform_segment(SegmentResult(**data, digest=digest(body)))


def setup_for(fixture, backend):
    return MotionSetup('r1', 'r1', 'r1', 'cal', 'cal', 'v1', 'v1',
                       fixture.calibration.configuration_ref, backend.config.digest,
                       'synthetic_config_authority', 'sha256:' + 'd' * 64, True,
                       'simulation', .001, .001)


def lease_for(fixture):
    def factory(request, prepared, config, snapshot):
        return SceneLease(request, prepared.digest, snapshot.scene_hash, config.digest,
                          snapshot.robot_model_name, fixture.case.now,
                          fixture.case.now + 5, 'synthetic_scene_authority',
                          'sha256:' + 'e' * 64)
    return factory
