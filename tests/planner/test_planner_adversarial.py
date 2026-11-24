"""Independent callback and time-of-check regressions for S05/S06."""
from dataclasses import fields, replace
import unittest

from vision_core import GateError, State
from vision_planner.coordinator import InspectionPlanner, digest
from vision_planner.preparation import prepare_plan
from test_preparation import SyntheticPlannerFixture
from planner_support import SyntheticBackend, setup_for, lease_for


class PlannerAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.fixture = SyntheticPlannerFixture(strict_planning=True)
        self.addCleanup(self.fixture.close)
        self.planner = InspectionPlanner(self.fixture.runtime, trust_verifier=lambda *_: True)
        self.backend = SyntheticBackend(self.fixture)

    def prepare(self):
        return self.planner.prepare(self.fixture.case.req('S05'),
            camera_calibration=self.fixture.calibration, policy=self.fixture.policy)

    def plan(self, lease_factory=None):
        return self.planner.plan_motion(self.fixture.case.req('S06'), backend=self.backend,
            setup=setup_for(self.fixture, self.backend),
            scene_lease_factory=lease_factory or lease_for(self.fixture))

    def assert_motion_denied(self):
        self.assertNotEqual(self.fixture.runtime.engine.states['S06'], State.SUCCEEDED)
        self.assertEqual(self.fixture.runtime.engine.states['S07'], State.BLOCKED)
        self.assertIsNone(self.planner.motion)

    def test_authenticated_preparation_cannot_be_replaced_with_rehashed_other_optics(self):
        def verifier(kind, binding):
            if kind == 'preparation':
                # Authentication applied to the original payload. A faulty
                # extension then replaces it with another self-consistent plan.
                other = prepare_plan(self.fixture.runtime,
                    camera_calibration=replace(self.fixture.calibration, fx=150),
                    policy=self.fixture.policy)
                for field in fields(other):
                    object.__setattr__(binding.preparation, field.name, getattr(other, field.name))
            return True
        self.planner.trust_verifier = verifier
        with self.assertRaises(GateError): self.prepare()
        self.assertEqual(self.fixture.runtime.engine.states['S06'], State.BLOCKED)
        self.assertIsNone(self.planner.prepared)

    def test_authenticated_motion_cannot_be_rehashed_after_removing_segments(self):
        self.prepare()
        def verifier(kind, plan):
            if kind == 'motion_binding':
                object.__setattr__(plan, 'segments', ())
                body = {key:value for key,value in plan.__dict__.items() if key != 'digest'}
                object.__setattr__(plan, 'digest', digest(body))
            return True
        self.planner.trust_verifier = verifier
        with self.assertRaises(GateError): self.plan()
        self.assert_motion_denied()

    def test_lease_expiring_inside_final_verifier_is_rejected(self):
        self.prepare()
        motion_seen = False
        def verifier(kind, binding):
            nonlocal motion_seen
            if kind == 'motion_binding': motion_seen = True
            if kind == 'scene_lease' and motion_seen:
                # State age remains under the adapter's two-second limit.
                # Only rechecking the lease after verification catches this.
                self.fixture.case.now = binding.lease.expires_at + .1
            return True
        self.planner.trust_verifier = verifier
        factory = lease_for(self.fixture)
        def short_lease(*args):
            lease = factory(*args)
            return replace(lease, expires_at=lease.issued_at+.2)
        with self.assertRaises(GateError): self.plan(short_lease)
        self.assert_motion_denied()

    def test_fresh_observation_does_not_hide_state_aging_during_authentication(self):
        self.prepare()
        def verifier(kind, payload):
            if kind == 'motion_binding': self.fixture.case.now += 3
            return True
        self.planner.trust_verifier = verifier
        with self.assertRaises(GateError): self.plan()
        self.assertLess(self.fixture.case.now-self.fixture.runtime.engine.context.observation_timestamp,
                        self.fixture.runtime.engine.max_age)
        self.assert_motion_denied()


if __name__ == '__main__':
    unittest.main()
