"""Real S01–S06 Core/Runtime orchestration with explicitly synthetic motion."""
from dataclasses import asdict, replace
import unittest
from unittest.mock import patch

from vision_core import GateError, State
from vision_core.ports import Request
from vision_planner import InspectionPlanner
from vision_planner.coordinator import digest
from test_preparation import SyntheticPlannerFixture
from planner_support import SyntheticBackend, setup_for, lease_for


class PlannerCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = SyntheticPlannerFixture(strict_planning=True, views=2)
        self.addCleanup(self.fixture.close)
        self.allowed = True
        self.trust_calls = []
        self.planner = InspectionPlanner(self.fixture.runtime, trust_verifier=self.trust)
        self.backend = SyntheticBackend(self.fixture)
        self.setup = setup_for(self.fixture, self.backend)

    def trust(self, kind, value):
        self.trust_calls.append(kind)
        return self.allowed

    def prepare(self, **changes):
        return self.planner.prepare(self.fixture.case.req('S05'),
            camera_calibration=changes.get('camera_calibration', self.fixture.calibration),
            policy=changes.get('policy', self.fixture.policy))

    def plan(self, **changes):
        return self.planner.plan_motion(self.fixture.case.req('S06'), backend=self.backend,
            setup=changes.get('setup', self.setup),
            scene_lease_factory=changes.get('scene_lease_factory', lease_for(self.fixture)))

    def assert_motion_blocked(self):
        self.assertNotEqual(self.fixture.runtime.engine.states['S06'], State.SUCCEEDED)
        self.assertEqual(self.fixture.runtime.engine.states['S07'], State.BLOCKED)
        self.assertIsNone(self.planner.motion)

    def test_complete_real_runtime_and_core_pipeline_to_s06(self):
        prepared = self.prepare()
        motion = self.plan()
        w = self.fixture.runtime.engine
        self.assertTrue(all(w.states[f'S{i:02d}'] == State.SUCCEEDED for i in range(1, 7)))
        self.assertEqual(w.states['S07'], State.PENDING)
        self.assertEqual(w.accepted_plan_hash, prepared.core_plan.digest)
        self.assertEqual(w.accepted_preparation_hash, prepared.digest)
        self.assertEqual(w.accepted_motion_hash, motion.digest)
        self.assertEqual([s.view_id for s in motion.segments], ['view_001', 'view_002'])
        self.assertEqual(motion.segments[0].end_joints, motion.segments[1].requested_start_joints)
        self.assertEqual(motion.digest, digest({k:v for k,v in motion.__dict__.items() if k != 'digest'}))
        self.assertIn('preparation', self.trust_calls)
        self.assertIn('motion_setup', self.trust_calls)
        self.assertIn('scene_lease', self.trust_calls)
        self.assertIn('motion_binding', self.trust_calls)
        self.assertFalse(hasattr(self.backend, 'execute'))

    def test_requires_strict_mode_at_session_creation(self):
        with SyntheticPlannerFixture() as fixture:
            with self.assertRaisesRegex(GateError, 'before S01'):
                InspectionPlanner(fixture.runtime, trust_verifier=self.trust)

    def test_untrusted_preparation_fails_s05(self):
        self.allowed = False
        with self.assertRaisesRegex(GateError, 'verification'): self.prepare()
        self.assertEqual(self.fixture.runtime.engine.states['S05'], State.FAILED)
        self.assertEqual(self.fixture.runtime.engine.states['S06'], State.BLOCKED)
        self.assertIsNone(self.planner.prepared)

    def test_optical_gap_fails_before_s06(self):
        calibration = replace(self.fixture.calibration, usable_image_xywh_px=(99,99,2,2))
        with self.assertRaises(GateError): self.prepare(camera_calibration=calibration)
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.fixture.runtime.engine.states['S06'], State.BLOCKED)

    def test_stage_request_cannot_be_substituted(self):
        wrong = replace(self.fixture.case.req('S05'), request_id='wrong', step_id='S06')
        with self.assertRaises(GateError):
            self.planner.prepare(wrong, camera_calibration=self.fixture.calibration,
                                 policy=self.fixture.policy)
        self.assertEqual(self.fixture.runtime.engine.states['S05'], State.PENDING)

    def test_s06_before_s05_is_denied(self):
        with self.assertRaises(GateError): self.plan()
        self.assertEqual(self.backend.calls, [])

    def test_missing_preparation_object_cannot_be_reconstructed_from_hash_only(self):
        self.prepare(); self.planner.prepared = None
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_untrusted_setup_cannot_contact_backend(self):
        self.prepare(); self.allowed = False
        with self.assertRaises(GateError): self.plan()
        self.assertEqual(self.backend.calls, [])
        self.assert_motion_blocked()

    def test_tool_calibration_and_model_binding(self):
        self.prepare()
        with self.assertRaises(GateError): self.plan(setup=replace(self.setup, calibration_revision='other'))
        self.assertEqual(self.backend.calls, [])
        self.assert_motion_blocked()

    def test_capture_configuration_cannot_be_changed_for_same_plan(self):
        self.prepare()
        with self.assertRaises(GateError): self.plan(setup=replace(self.setup, camera_configuration_ref='sha256:'+'f'*64))
        self.assert_motion_blocked()

    def test_missing_joint_velocities_not_assumed_stationary(self):
        self.prepare()
        self.backend.transform_snapshot = lambda s: replace(s, joint_velocities=())
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_fresh_service_response_does_not_refresh_stale_robot_state(self):
        self.prepare()
        self.backend.transform_snapshot = lambda s: replace(s, timestamp=s.timestamp-3)
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_live_robot_must_be_stationary(self):
        self.prepare()
        self.backend.transform_snapshot = lambda s: replace(s, joint_velocities=(.02,0.))
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_lease_cannot_belong_to_other_request(self):
        self.prepare()
        factory = lease_for(self.fixture)
        def wrong(*args):
            lease = factory(*args)
            return replace(lease, request=replace(lease.request, request_id='previous'))
        with self.assertRaises(GateError): self.plan(scene_lease_factory=wrong)
        self.assert_motion_blocked()

    def test_lease_cannot_expire_during_planning(self):
        self.prepare()
        factory = lease_for(self.fixture)
        def expired(*args):
            lease = factory(*args)
            return replace(lease, expires_at=lease.issued_at+.05)
        with self.assertRaises(GateError): self.plan(scene_lease_factory=expired)
        self.assert_motion_blocked()

    def test_tampered_segment_digest_is_rejected(self):
        self.prepare()
        self.backend.transform_segment = lambda s: replace(s, digest='f'*64)
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_rehashed_segment_cannot_change_target_or_view(self):
        self.prepare()
        def tamper(segment):
            changed = replace(segment, view_id='another')
            body = asdict(changed); body.pop('digest')
            return replace(changed, digest=digest(body))
        self.backend.transform_segment = tamper
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_backend_failure_is_terminal_and_never_retried(self):
        self.prepare()
        def fail(*args): raise GateError('synthetic collision rejection')
        self.backend.plan_segment = fail
        with self.assertRaisesRegex(GateError, 'collision'): self.plan()
        calls = len(self.backend.calls)
        with self.assertRaises(GateError): self.plan()
        self.assertEqual(len(self.backend.calls), calls)
        self.assert_motion_blocked()

    def test_final_motion_verification_cannot_be_skipped(self):
        self.prepare()
        self.planner.trust_verifier = lambda kind, payload: kind != 'motion_binding'
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_changed_scene_after_successful_segments_is_rejected(self):
        self.prepare()
        original = self.backend.transform_segment
        def change(segment):
            self.backend.scene_hash = 'f'*64
            return original(segment)
        self.backend.transform_segment = change
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_slow_verifier_cannot_accept_expired_observation(self):
        self.prepare()
        def verifier(kind, payload):
            if kind == 'motion_binding': self.fixture.case.now += 11
            return True
        self.planner.trust_verifier = verifier
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_modified_preparation_is_not_a_second_approved_s05(self):
        prepared = self.prepare()
        self.planner.prepared = replace(prepared, coverage_fraction=.1)
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_blocked()

    def test_success_cannot_be_replayed_as_a_new_motion_request(self):
        self.prepare(); self.plan()
        prior = len(self.backend.calls)
        with self.assertRaises(GateError): self.plan()
        self.assertEqual(len(self.backend.calls), prior)

    def test_aggregate_limit_applies_across_individually_valid_segments(self):
        self.prepare()
        with patch('vision_planner.coordinator.MAX_MOTION_POINTS', 5):
            with self.assertRaisesRegex(GateError, 'aggregate'): self.plan()
        self.assert_motion_blocked()


if __name__ == '__main__':
    unittest.main()
