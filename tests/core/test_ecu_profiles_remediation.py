import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from test_ecu_profiles import synthetic, measured
from vision_modules.ecu_profiles import *
from vision_core import Context
from vision_core.profiles import PROFILE_KINDS, Profile
from vision_core.repeatability import ObservedECU


def approve(r):
    r = replace(r, status='READY_FOR_REVIEW', approval=None)
    return replace(r, status='APPROVED', approval=ApprovalEvidence(r.profile_id, r.revision, record_sha256(r), 'reviewer', '2026-01-02T12:00:00Z', 'review'))


class RemediationTests(unittest.TestCase):
    def setUp(self):
        self.r = synthetic(); self.cal = {'cal':'v1'}
        self.cat = ECUCatalog(); self.cat.register(self.r)
        self.d = Declaration('ETC3','synthetic_variant','r1','operator')
        self.o = ECUObservation('sensor','ref','oak/rgb','session','scene','r1',100,(ObservedConnector('a','black',(1,1,1)),),True,True)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = ReleaseStore(self.tmp.name); self.addCleanup(self.store.close)
        self.store.publish(self.r,self.cal,catalog=self.cat)
        self.ctx = Context('session',{k:'r1' for k in PROFILE_KINDS},'scene',100,'oak/rgb')
        self.pose = ObservedECU('oak/rgb',(0,0,0),0,100,'scene','r1','ETC3','synthetic_variant','ref')
        self.ps = {k: Profile(k,k,'1','r1',True,{'basic'},{'basic'},self.cal) for k in PROFILE_KINDS}

    def verify(self, obs=None, catalog=None):
        return verify_declared_ecu(self.r,self.d,obs or self.o,session_id='session',frame_id='oak/rgb',scene_revision='scene',now=100,max_age=10,calibrations=self.cal,catalog=catalog or self.cat)
    def plan(self, **kwargs):
        args = dict(declaration=self.d,observation=self.o,context=self.ctx,observed_ecu=self.pose,profiles=self.ps,calibrations=self.cal,requirements={},now=100,max_age=10,catalog=self.cat,release_store=self.store,min_coverage=1,require_raw=False)
        args.update(kwargs); return select_and_plan_verified(**args)
    def test_frame_segments(self):
        for frame in ('/a','a/','a//b','a/../b','a/./b','a/space b','a/\n','x'*256):
            with self.subTest(frame=frame), self.assertRaises(ValueError): replace(self.o,frame_id=frame)
    def test_catalog_exact_selection(self):
        self.assertEqual(self.cat.select(self.d),self.r)
        with self.assertRaises(KeyError): self.cat.select(replace(self.d,variant='other'))
    def test_catalog_list(self): self.assertEqual(self.cat.list_records('ETC3'),(self.r,))
    def test_ambiguous_variant(self):
        other=approve(replace(self.r,profile_id='other',variant='other'))
        self.cat.register(other); self.assertEqual(self.verify().status,'AMBIGUOUS')
    def test_distinct_variant(self):
        c=replace(self.r.connectors[0],position=measured((5,5,5),'other_landmark'))
        other=approve(replace(self.r,profile_id='other',variant='other',connectors=(c,)))
        self.cat.register(other); self.assertEqual(self.verify().status,'ACCEPTED')
    def test_second_landmark_cross_category(self):
        c=replace(self.r.connectors[0],connector_id='b',position=measured((2,2,2),'pcb'))
        self.assertTrue(validate_draft(replace(self.r,connectors=self.r.connectors+(c,))))
    def test_orientation_missing(self):
        self.assertTrue(validate_draft(replace(self.r,views=(replace(self.r.views[0],orientation_provenance=None),))))
    def test_orientation_same_reference(self):
        v=self.r.views[0]; self.assertTrue(validate_draft(replace(self.r,views=(replace(v,orientation_provenance=v.position.provenance),))))
    def test_orientation_cross_category(self):
        v=self.r.views[0]; self.assertTrue(validate_draft(replace(self.r,views=(replace(v,orientation_provenance=self.r.envelope.provenance),))))
    def test_orientation_roundtrip(self): self.assertEqual(load_json(canonical_json(self.r)),self.r)
    def test_store_reopen_and_no_overwrite(self):
        other=approve(replace(self.r,declared_type='other')); cat=ECUCatalog(); cat.register(other)
        with ReleaseStore(self.tmp.name) as store:
            self.assertEqual(store.read('synthetic','r1'),self.r)
            with self.assertRaises(FileExistsError): store.publish(other,self.cal,catalog=cat)
    def test_store_other_revision(self):
        other=approve(replace(self.r,revision='r2')); self.cat.register(other)
        self.store.publish(other,self.cal,catalog=self.cat); self.assertEqual(self.store.read('synthetic','r2'),other)
    def test_store_tamper(self):
        path=Path(self.tmp.name)/self.store._name('synthetic','r1'); path.write_text(canonical_json(replace(self.r,declared_type='other')))
        with self.assertRaises(ValueError): self.store.read('synthetic','r1')
    def test_store_symlink(self):
        path=Path(self.tmp.name)/self.store._name('synthetic','r1'); path.unlink(); path.symlink_to('/dev/null')
        with self.assertRaises(OSError): self.store.read('synthetic','r1')
    def test_plan_receipt(self):
        plan,receipt=self.plan(); self.assertEqual(receipt.record_sha256,record_sha256(self.r)); self.assertEqual(receipt.plan_digest,plan.digest)
    def test_plan_wrong_reference(self):
        with self.assertRaises(ValueError): self.plan(observed_ecu=replace(self.pose,reference='different'))
    def test_plan_wrong_timestamp(self):
        with self.assertRaises(ValueError): self.plan(observed_ecu=replace(self.pose,timestamp=99))
    def test_plan_wrong_variant(self):
        with self.assertRaises(ValueError): self.plan(observed_ecu=replace(self.pose,variant='wrong'))
    def test_plan_unverified(self):
        with self.assertRaises(ValueError): self.plan(observation=replace(self.o,verified=False))
    def test_plan_stale(self):
        with self.assertRaises(ValueError): self.plan(now=111)
    def test_plan_release_mismatch(self):
        path=Path(self.tmp.name)/self.store._name('synthetic','r1'); path.unlink()
        with self.assertRaises(OSError): self.plan()
    def test_plan_ambiguous(self):
        self.cat.register(approve(replace(self.r,profile_id='other',variant='other')))
        with self.assertRaises(ValueError): self.plan()
