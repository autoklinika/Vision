"""Final premerge Runtime authentication and source-time regressions.

All receipts and sources are synthetic. Faulty verifier callbacks intentionally
mutate their inputs or advance the clock; none of these tests accesses ROS.
"""
from dataclasses import replace
import unittest

import test_vision_runtime_v1 as runtime_fixture
import test_vision_runtime_ros2 as ros_fixture
from vision_core import State
from vision_runtime import MeasuredConnector, ReadinessReceipt, SensorStamp
from vision_runtime.ros2_observation import SensorObservationBuilder, VerifiedGeometry


H = 'sha256:' + 'a' * 64
OTHER = 'sha256:' + 'b' * 64


class FinalRuntimeAuditTests(unittest.TestCase):
    def runtime(self, verifier=None):
        fixture = runtime_fixture.RuntimeTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if verifier is not None:
            fixture.coordinator = fixture.make(trust_verifier=verifier)
        return fixture

    def packet(self):
        fixture = ros_fixture.AdapterTests('test_valid')
        fixture.setUp()
        return fixture.packet()

    def geometry(self, position=(0, 0, 0)):
        return VerifiedGeometry(position, (0, 0, 0, 1), (100, 80, 20), .1,
            (MeasuredConnector('a', 'black', (1, 1, 1), .1, H),),
            (H,), (H,), H, 'scene')

    def build(self, verifier, *, geometry=None, profiles=None, calibrations=None):
        return SensorObservationBuilder(verifier).observation(
            self.packet(), geometry or self.geometry(), session_id='session',
            request_id='S03', profile_revisions=profiles or {'ecu': 'r1'},
            calibration_ids=calibrations or {'relative': 'r1'},
            relative_calibration_id='r1', scene_revision='scene', source='sensor',
            source_proof=H)

    def test_readiness_mutated_after_authentication_cannot_succeed(self):
        def verifier(kind, receipt):
            if kind == 'readiness':
                object.__setattr__(receipt, 'quality', False)
            return True
        f = self.runtime(verifier)
        result = f.coordinator.prepare_station(f.ready(), f.req('S01'))
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(f.coordinator.engine.states['S02'], State.BLOCKED)

    def test_pose_mutated_after_authentication_cannot_succeed(self):
        def verifier(kind, receipt):
            if kind == 'observation':
                object.__setattr__(receipt, 'position_mm', (999, 0, 0))
            return True
        f = self.runtime(verifier)
        f.s02()
        result = f.coordinator.accept_localization(f.obs(), f.req('S03'))
        self.assertEqual(result.status, 'FAILED')
        self.assertIsNone(f.coordinator._observation)
        self.assertEqual(f.coordinator.engine.states['S04'], State.BLOCKED)

    def skewed_observation(self, f):
        return f.obs(rgb=SensorStamp('camera', 100.05, H),
                     camera_info=SensorStamp('camera', 100.05, H),
                     tf=SensorStamp('station', 100.05, H))

    def test_s03_oldest_stream_is_rechecked_after_slow_verifier(self):
        f = self.runtime()
        f.s02()
        request = f.req('S03')
        f.coordinator.begin('S03', request)
        observation = self.skewed_observation(f)
        f.now = 109.99
        def verifier(kind, receipt):
            if kind == 'observation': f.now = 110.02
            return True
        f.coordinator.trust_verifier = verifier
        result = f.coordinator.accept_localization(observation, request)
        self.assertLess(f.now-observation.rgb.timestamp, f.coordinator.max_age)
        self.assertGreater(f.now-observation.depth.timestamp, f.coordinator.max_age)
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(f.coordinator.engine.states['S04'], State.BLOCKED)

    def test_s04_oldest_stream_is_rechecked_after_slow_verifier(self):
        f = self.runtime()
        f.s02()
        request = f.req('S03')
        f.coordinator.begin('S03', request)
        f.now = 100.05
        observation = self.skewed_observation(f)
        self.assertEqual(f.coordinator.accept_localization(observation, request).status, 'SUCCEEDED')
        f.now = 109.99
        def verifier(kind, receipt):
            if kind == 'observation': f.now = 110.02
            return True
        f.coordinator.trust_verifier = verifier
        result = f.coordinator.verify_selected_ecu(f.req('S04'))
        self.assertLess(f.now-observation.rgb.timestamp, f.coordinator.max_age)
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(f.coordinator.engine.states['S05'], State.BLOCKED)

    def test_s04_requires_exact_receipt_previously_accepted_by_s03(self):
        f = self.runtime()
        f.s03()
        f.coordinator._observation = replace(f.coordinator._observation,
            position_mm=(50, 60, 0), reference=OTHER, geometry_reference=OTHER,
            binding_reference=OTHER)
        result = f.coordinator.verify_selected_ecu(f.req('S04'))
        self.assertEqual(result.status, 'FAILED')
        self.assertEqual(f.coordinator.engine.states['S05'], State.BLOCKED)

    def test_geometry_alias_changed_during_builder_auth_is_rejected(self):
        position = [0, 0, 0]
        geometry = self.geometry(position)
        def verifier(kind, binding):
            self.assertEqual(binding.geometry.position_mm[0], 0)
            position[0] = 999
            return True
        result = self.build(verifier, geometry=geometry)
        self.assertEqual(result.status, 'NOT_READY')
        self.assertIsNone(result.receipt)

    def test_binding_field_cannot_be_changed_inside_verifier(self):
        def verifier(kind, binding):
            object.__setattr__(binding, 'scene_revision', 'different')
            return True
        self.assertEqual(self.build(verifier).status, 'NOT_READY')

    def test_caller_mapping_changes_cannot_escape_authenticated_builder_binding(self):
        profiles, calibrations = {'ecu': 'r1'}, {'relative': 'r1'}
        def verifier(kind, binding):
            self.assertEqual(binding.profile_revisions, (('ecu', 'r1'),))
            self.assertEqual(binding.calibration_ids, (('relative', 'r1'),))
            profiles['ecu'] = 'r2'
            calibrations['relative'] = 'r2'
            return True
        result = self.build(verifier, profiles=profiles, calibrations=calibrations)
        self.assertEqual(result.status, 'READY')
        self.assertEqual(dict(result.receipt.profile_revisions), {'ecu': 'r1'})
        self.assertEqual(dict(result.receipt.calibration_ids), {'relative': 'r1'})

    def readiness(self, verifier, **changes):
        arguments = dict(session_id='session', request_id='S01',
            profile_revisions={'capture': 'r1'}, calibration_ids={'cal': 'r1'},
            timestamp=100, source='sensor', source_proof=H, device_state_reference=OTHER,
            capabilities={'rgb', 'depth', 'camera_info', 'tf'})
        arguments.update(changes)
        return SensorObservationBuilder(verifier).readiness(**arguments)

    def test_readiness_verifier_receives_the_complete_typed_receipt(self):
        seen = []
        def verifier(kind, receipt):
            seen.append(receipt)
            return (kind == 'readiness' and isinstance(receipt, ReadinessReceipt)
                    and receipt.session_id == 'session' and receipt.request_id == 'S01'
                    and dict(receipt.profile_revisions) == {'capture': 'r1'}
                    and dict(receipt.calibration_ids) == {'cal': 'r1'}
                    and receipt.timestamp == 100 and receipt.reference == H
                    and receipt.device_state_reference == OTHER)
        result = self.readiness(verifier)
        self.assertEqual(result.status, 'READY')
        self.assertIs(result.receipt, seen[0])

    def test_readiness_builder_rejects_mutated_authenticated_timestamp(self):
        def verifier(kind, receipt):
            if isinstance(receipt, ReadinessReceipt):
                object.__setattr__(receipt, 'timestamp', 200)
            return True
        self.assertEqual(self.readiness(verifier).status, 'NOT_READY')

    def test_readiness_verifier_can_reject_another_request(self):
        verifier = lambda kind, receipt: isinstance(receipt, ReadinessReceipt) and receipt.request_id == 'S01'
        self.assertEqual(self.readiness(verifier, request_id='other').status, 'NOT_READY')


if __name__ == '__main__':
    unittest.main()
