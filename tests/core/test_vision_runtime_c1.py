"""Synthetic C1 safety regressions; permissive callbacks are test doubles only."""
import unittest
from dataclasses import replace
import test_vision_runtime_v1 as runtime
import test_vision_runtime_ros2 as ros
import test_ecu_reference_execution as reference
from vision_runtime import MeasuredConnector
from vision_runtime.ros2_observation import SensorObservationBuilder, VerifiedGeometry

H = runtime.H

class ReferenceSafetyTests(runtime.RuntimeTests):
    def changed(self, change):
        p, store = reference.ExecutionTests.modified(self, change)
        self.coordinator = self.make(reference_profile=p, reference_release_store=store, library=None)

    def failed(self, observation=None):
        self.s02()
        self.assertEqual(self.coordinator.accept_localization(observation or self.obs(), self.req('S03')).status, 'FAILED')

    def test_required_reference_position(self):
        self.changed(lambda d: d['connectors_landmarks']['connectors'][0].update(position_mm=[50,50,10]))
        self.failed()

    def test_missing_localization_feature_rule(self):
        self.failed(self.obs(connectors=(MeasuredConnector('other','black',(1,1,1),.1,H),)))

    def test_unsupported_method(self):
        self.changed(lambda d: d['recognition_rules']['features_to_check'][0].update(method='visual_marking'))
        self.failed()

    def test_connector_uncertainty(self):
        self.failed(self.obs(connectors=(MeasuredConnector('a','black',(1,1,1),1000,H),)))

    def test_envelope_uncertainty(self):
        self.failed(self.obs(envelope_mm=(10000,10000,10000), envelope_uncertainty_mm=1000000))

    def test_alternate_profile_color(self):
        self.changed(lambda d: d['connectors_landmarks']['connectors'][0].update(color='gray'))
        self.failed()

class BindingTests(unittest.TestCase):
    def build(self, verifier, proof=H):
        t=ros.AdapterTests('test_valid'); t.setUp()
        g=VerifiedGeometry((0,0,0),(0,0,0,1),(100,80,20),.2,(MeasuredConnector('a','black',(1,1,1),.1,H),),(H,),(H,),H,'scene')
        return SensorObservationBuilder(verifier).observation(t.packet(),g,session_id='session',request_id='S03',profile_revisions={'ecu':'r1'},calibration_ids={'relative':'r1'},relative_calibration_id='r1',scene_revision='scene',source='sensor',source_proof=proof)

    def test_binding_accepts_matching_evidence(self):
        result=self.build(lambda kind, b: kind == 'binding' and b.source_proof == H and bool(b.packet) and bool(b.geometry))
        self.assertEqual(result.status,'READY'); self.assertTrue(result.receipt.binding_reference.startswith('sha256:'))

    def test_binding_denied(self):
        self.assertEqual(self.build(lambda kind, b: False).status,'NOT_READY')

    def test_source_proof_mismatch(self):
        self.assertEqual(self.build(lambda kind, b: kind == 'binding' and b.source_proof == H, 'sha256:'+'b'*64).status,'NOT_READY')
