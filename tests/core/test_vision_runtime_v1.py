"""Synthetic offline coordinator integration tests; no physical measurements."""
import unittest
import copy
from dataclasses import replace
from pathlib import Path
import test_ecu_reference_execution as fixture
from vision_core import Context, Journal, Profile, State, GateError
from vision_core.profiles import PROFILE_KINDS
from vision_core.ports import Request
from vision_modules.ecu_profiles import Declaration, ApprovalEvidence, record_sha256
from vision_runtime import VisionRuntimeCoordinator, ReadinessReceipt, ObservationReceipt, SensorStamp, MeasuredConnector
from vision_runtime.mock import MockSensorPort

H = 'sha256:' + 'a'*64

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        fixture.ExecutionTests.setUp(self)
        # Synthetic verifier and reference data only; these are not camera evidence.
        self.d = copy.deepcopy(self.d)
        feature = self.d['connectors_landmarks']['connectors'][0]
        feature.update(feature_id='a', color='black', position_mm=[1, 1, 1])
        rule = self.d['recognition_rules']['features_to_check'][0]
        rule.update(feature_id='a', method='rgbd_landmark')
        self.d['localization_rules']['required_features'] = ['a']
        self.p = fixture.seal(self.d)
        from vision_modules.ecu_reference import ReferenceReleaseStore, ReferenceLibrary
        folder = Path(self.tmp.name) / 'runtime_ref'; folder.mkdir()
        self.ref = ReferenceReleaseStore(folder); self.addCleanup(self.ref.close); self.ref.publish(self.p)
        self.lib = ReferenceLibrary(); self.lib.register(self.p)
        self.bundle = fixture.ExecutionTests.compile(self)
        self.caps = self.caps | {'depth','camera_info','tf'}
        self.profiles = {k: Profile(k,k,'1','r1',True,{'basic'},{'basic'},self.cal) for k in PROFILE_KINDS}
        self.profiles['ecu'] = self.bundle.core_profile
        self.ctx = Context('session',{k:'r1' for k in PROFILE_KINDS})
        self.journal = Journal(str(Path(self.tmp.name)/'journal.sqlite')); self.addCleanup(self.journal.close)
        self.now = 100
        self.coordinator = self.make()

    def make(self, **changes):
        kw = dict(declaration=Declaration('ETC3','synthetic_variant','r1','operator'), record=self.record, catalog=self.catalog, release_store=self.ecu, reference_profile=self.p, physical_state='pcb_exposed_top', recipe='photo', capabilities=self.caps, asset_store=self.assets, reference_release_store=self.ref, trust_verifier=lambda kind, receipt: True, sensor_frame='camera', scene_frame='station', known_transforms={('camera','station')}, max_skew=.1, clock=lambda:self.now, library=self.lib)
        kw.update(changes)
        return VisionRuntimeCoordinator(self.journal,self.ctx,self.profiles,self.cal,{},10,**kw)
    def req(self, stage, rid=None): return Request(stage, rid or stage, self.coordinator.engine.context)
    def ready(self, **changes):
        return replace(ReadinessReceipt('session','S01',self.ctx.profile_revisions,self.cal,100,'sensor',H,True,frozenset(self.caps),H), **changes)
    def obs(self, **changes):
        s=SensorStamp('camera',100,H); tf=SensorStamp('station',100,H)
        return replace(ObservationReceipt('session','S03',self.ctx.profile_revisions,self.cal,'scene','station',s,s,s,tf,'camera','16UC1',(0,0,0),(0,0,0,1),(100,80,20),.1,(MeasuredConnector('a','black',(1,1,1),.1,H),),(H,),(H,),'sensor',H,True, geometry_reference=H, source_proof=H, binding_reference=H), **changes)
    def s01(self): self.assertEqual(self.coordinator.prepare_station(self.ready(),self.req('S01')).status,'SUCCEEDED')
    def s02(self): self.s01(); self.assertEqual(self.coordinator.confirm_selection(self.req('S02')).status,'SUCCEEDED')
    def s03(self, obs=None): self.s02(); self.assertEqual(self.coordinator.accept_localization(obs or self.obs(),self.req('S03')).status,'SUCCEEDED')
    def test_full(self):
        self.s03(); result=self.coordinator.verify_selected_ecu(self.req('S04'))
        self.assertEqual(result.status,'SUCCEEDED'); self.assertEqual(result.operator_id,'operator')
        self.assertTrue(all(self.coordinator.engine.states[f'S{i:02}']==State.SUCCEEDED for i in range(1,5)))
        self.assertEqual(self.coordinator.engine.states['S05'],State.PENDING)
        event=[e for e in self.journal.replay('session') if e.kind=='localization_accepted'][0]
        self.assertEqual(event.data['context']['scene_revision'],'scene')
        self.assertTrue(event.data['evidence']['reference'].startswith('sha256:'))
    def test_dispatch_before_receipt(self):
        request=self.req("S01"); self.coordinator.begin("S01",request)
        self.now=101
        self.assertEqual(self.coordinator.prepare_station(self.ready(timestamp=101),request).status,"SUCCEEDED")
    def test_invalid_quaternion(self):
        with self.assertRaises(ValueError): self.obs(quaternion_xyzw=(0,0,0,2))
    def test_second_pose(self):
        self.s03(self.obs(position_mm=(20,3,9),quaternion_xyzw=(0,0,1,0)))
        self.assertEqual(self.coordinator.verify_selected_ecu(self.req('S04')).status,'SUCCEEDED')
    def test_mock_inert(self):
        port=MockSensorPort(); self.assertIsNone(port.observe(self.req('S03'))); self.assertEqual(len(port.requests),1)
    def test_selection_wrong_variant(self):
        with self.assertRaises(ValueError): self.make(declaration=Declaration('ETC3','wrong','r1','operator'))
    def test_selection_draft(self):
        with self.assertRaises(ValueError): self.make(record=replace(self.record,status='DRAFT'))
    def test_replay(self):
        self.s01()
        with self.assertRaises(GateError): self.coordinator.prepare_station(self.ready(),self.req('S01'))
    def test_request_reuse(self):
        self.s01()
        with self.assertRaises(GateError): self.coordinator.confirm_selection(self.req('S02','S01'))
    def test_restart_blocks_running(self):
        self.coordinator.engine.start('S01','running')
        again=self.make(); self.assertEqual(again.engine.states['S01'],State.BLOCKED)
    def test_changed_profiles(self):
        self.s01(); self.coordinator.engine.profiles['station']=replace(self.profiles['station'],revision='r2')
        with self.assertRaises(GateError): self.coordinator.confirm_selection(self.req('S02'))
    def test_context_mismatch_request(self):
        with self.assertRaises(ValueError): self.coordinator.prepare_station(self.ready(),Request('S01','a',Context('other',self.ctx.profile_revisions)))
    def test_stale_s04(self):
        self.s03(); self.now=111
        with self.assertRaises(GateError): self.coordinator.verify_selected_ecu(self.req('S04'))
    def test_no_trust(self):
        self.coordinator=self.make(trust_verifier=lambda kind, receipt: False)
        self.assertEqual(self.coordinator.prepare_station(self.ready(),self.req('S01')).status,'FAILED')
    def test_ambiguous_variant(self):
        other=replace(self.record,variant='other',profile_id='other',approval=None)
        other=replace(other,approval=ApprovalEvidence(other.profile_id,other.revision,record_sha256(other),'reviewer','2026-01-02T12:00:00Z','review-record'))
        self.catalog.register(other); self.s03()
        result=self.coordinator.verify_selected_ecu(self.req('S04'))
        self.assertEqual(result.status,'FAILED'); self.assertIn('AMBIGUOUS',result.reasons[0])


def readiness_case(name, changes):
    def test(self):
        result=self.coordinator.prepare_station(self.ready(**changes),self.req('S01'))
        self.assertEqual(result.status,'FAILED'); self.assertEqual(self.coordinator.engine.states['S02'],State.BLOCKED)
    setattr(RuntimeTests, 'test_readiness_'+name, test)
for name, changes in {
    'request':{'request_id':'wrong'}, 'session':{'session_id':'other'}, 'operator':{'source':'operator'},
    'quality':{'quality':False}, 'stale':{'timestamp':89}, 'calibration':{'calibration_ids':{'cal':'wrong'}},
    'profiles':{'profile_revisions':{'ecu':'wrong'}}, 'capabilities':{'capabilities':frozenset({'rgb'})},
    'reference':{'reference':'unverified'}, 'device':{'device_state_reference':'unverified'},
}.items(): readiness_case(name, changes)

def observation_case(name, changes):
    def test(self):
        self.s02(); result=self.coordinator.accept_localization(self.obs(**changes),self.req('S03'))
        self.assertEqual(result.status,'FAILED'); self.assertEqual(self.coordinator.engine.states['S04'],State.BLOCKED)
    setattr(RuntimeTests, 'test_observation_'+name, test)
for name, changes in {
    'request':{'request_id':'wrong'}, 'scene_frame':{'frame_id':'wrong'}, 'sensor_frame':{'rgb':SensorStamp('other',100,H)},
    'tf_frame':{'tf':SensorStamp('other',100,H)}, 'tf_source':{'tf_source_frame':'wrong'},
    'skew':{'depth':SensorStamp('camera',99,H)}, 'stale':{'depth':SensorStamp('camera',89,H)},
    'depth_reference':{'depth':SensorStamp('camera',100,'unverified')}, 'tf_reference':{'tf':SensorStamp('station',100,'unverified')},
    'envelope':{'envelope_mm':(101,80,20)}, 'operator':{'source':'operator'}, 'quality':{'quality':False},
    'connector_color':{'connectors':(MeasuredConnector('a','gray',(1,1,1),.1,H),)},
    'connector_position':{'connectors':(MeasuredConnector('a','black',(10,1,1),.1,H),)},
    'connector_reference':{'connectors':(MeasuredConnector('a','black',(1,1,1),.1,'unverified'),)},
    'profile':{'profile_revisions':{'ecu':'r2'}}, 'calibration':{'calibration_ids':{'cal':'wrong'}},
}.items(): observation_case(name, changes)

if __name__ == '__main__': unittest.main()
