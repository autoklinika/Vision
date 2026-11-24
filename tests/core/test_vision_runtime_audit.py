"""Independent synthetic V1 runtime regressions, initially RED before fixes."""
import copy
import unittest
from dataclasses import replace

import test_vision_runtime_v1 as runtime_fixture
import test_vision_runtime_ros2 as rosfixture
import test_ecu_reference_execution as ref_fixture
from test_vision_runtime_ros2 import header, img, info, tf, H
from vision_runtime.ros2_messages import normalize_rgbd, MAX_IMAGE_BYTES
from vision_runtime.ros2_bridge import SnapshotCollector, TopicBindings
from vision_runtime.ros2_observation import SensorObservationBuilder, VerifiedGeometry
from vision_runtime import MeasuredConnector


class RuntimeAuditTests(unittest.TestCase):
    def fixture(self):
        t=runtime_fixture.RuntimeTests('test_full')
        t.setUp()
        self.addCleanup(t.doCleanups)
        return t

    def test_reference_connector_contradiction_blocks_s04(self):
        t=self.fixture()
        # The already approved test reference says a different position
        # than the approved ECURecord. It cannot be ignored by Vision.
        def corrupt(d):
            d['connectors_landmarks']['connectors'][0]['position_mm']=[50,50,10]
        p,s=ref_fixture.ExecutionTests.modified(t,corrupt)
        t.coordinator=t.make(reference_profile=p,reference_release_store=s,library=None)
        # Safe rejection may occur at S03 (preferable) or at S04.
        t.s02()
        localized=t.coordinator.accept_localization(t.obs(), t.req('S03'))
        if localized.status == 'SUCCEEDED':
            result=t.coordinator.verify_selected_ecu(t.req('S04'))
            self.assertEqual(result.status,'FAILED')
        else:
            self.assertEqual(localized.status,'FAILED')
            self.assertEqual(t.coordinator.engine.states['S04'].value,'BLOCKED')

    def test_large_declared_uncertainty_cannot_hide_wrong_geometry(self):
        t=self.fixture()
        observation=t.obs(
            envelope_mm=(10000,10000,10000),
            envelope_uncertainty_mm=1000000,
            connectors=(MeasuredConnector('a','black',(1,1,1),1000000,H),)
        )
        t.s02()
        result=t.coordinator.accept_localization(observation,t.req('S03'))
        self.assertEqual(result.status,'FAILED')

    def test_builder_verifier_must_receive_geometry_and_packet_together(self):
        fixture=rosfixture.AdapterTests('test_valid')
        fixture.setUp()
        packet=fixture.packet()
        geometry=VerifiedGeometry(
            (0,0,0),(0,0,0,1),(100,80,20),.2,
            (MeasuredConnector('a','black',(1,1,1),.1,H),),(H,),(H,),H,'scene')
        def binding_verifier(kind, subject):
            return (kind=='binding'
                    and getattr(subject,'packet',None) is packet
                    and getattr(subject,'geometry',None) is geometry
                    and getattr(subject,'scene_revision',None)=='scene')
        result=SensorObservationBuilder(binding_verifier).observation(
            packet,geometry,session_id='session',request_id='S03',
            profile_revisions={'ecu':'r1'},
            calibration_ids={'relative':'r1'},relative_calibration_id='r1',
            scene_revision='scene',source='sensor',source_proof=H)
        self.assertEqual(result.status,'READY')

    def test_all_zero_metric_depth_not_accepted(self):
        t=rosfixture.AdapterTests('test_valid')
        t.setUp()
        t.args[1].data = bytes(len(t.args[1].data))
        with self.assertRaises(ValueError):
            t.packet()

    def test_collector_prefers_latest_synchronized_quadruple(self):
        t=rosfixture.AdapterTests('test_valid')
        t.setUp()
        collector=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0),capacity=3)
        for key,msg in zip(('rgb','depth','rgb_info','depth_info'),t.args):
            collector.inject(key,msg)
        newer=copy.deepcopy(t.args[0])
        newer.header=header('rgb',101)
        collector.inject('rgb',newer)
        packet=collector.snapshot(
            scene_frame='scene',depth_unit='mm',now=101,max_age=2,max_skew=.1,
            tf_lookup=lambda target,source,stamp: tf(target,source))
        self.assertEqual(packet.rgb.stamp.timestamp,100)

    def test_collector_rejects_oversize_at_ingress(self):
        t=rosfixture.AdapterTests('test_valid')
        t.setUp()
        collector=SnapshotCollector(TopicBindings('/r','/d','/ri','/di',0),capacity=1)
        oversized=copy.deepcopy(t.args[0])
        oversized.step=MAX_IMAGE_BYTES
        oversized.height=2
        with self.assertRaises(ValueError):
            collector.inject('rgb',oversized)


if __name__=='__main__':
    unittest.main()
