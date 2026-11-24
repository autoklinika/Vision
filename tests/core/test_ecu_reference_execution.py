"""Synthetic, test-only reference assets and ECU data; no real ECU measurements."""
import hashlib
import json
import math
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from test_ecu_reference_profile import synthetic_profile
from test_ecu_profiles import synthetic
from vision_modules.ecu_reference import *
from vision_modules.ecu_profiles import ECUCatalog, ReleaseStore
from vision_core import Context
from vision_core.profiles import PROFILE_KINDS, Profile, validate_profiles
from vision_core.repeatability import ObservedECU, create_plan

def seal(d):
    digest = content_sha256(load_json(json.dumps(d)))
    d['metadata']['content_sha256'] = digest
    d['provenance_release']['released_snapshot_sha256'] = digest
    d['provenance_release']['release_approval']['content_sha256'] = digest
    return load_json(json.dumps(d))

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); (root/'private').mkdir(); (root/'ecu').mkdir(); (root/'ref').mkdir()
        self.data = b'synthetic private image bytes'; (root/'private/image.png').write_bytes(self.data)
        d = synthetic_profile(); self.d = d
        d['metadata'].update(family_id='ETC3', variant_id='synthetic_variant')
        d['inspection_workflows']['recipes'][0]['required_modules'] = []
        v = d['photography_recipes']['recipes'][0]['views'][0]; v['view_id'] = 'v1'; v['camera_goal']['translation_mm'] = [10,20,50]
        d['inspection_workflows']['recipes'][0]['required_view_ids'] = ['v1']
        d['pcb_definition']['regions_of_interest'][0]['rectangle_xywh_mm'] = [5,5,20,30]
        h = hashlib.sha256(self.data).hexdigest(); d['reference_assets']['assets'][0].update(sha256=h, bytes=len(self.data)); d['provenance_release']['asset_hashes'][0]['sha256'] = h
        self.p = seal(d); self.record = synthetic(); self.cal = {'cal':'v1','camera_cal':'r1'}; self.caps = {'basic','rgb','camera'}
        self.catalog = ECUCatalog(); self.catalog.register(self.record)
        self.ecu = ReleaseStore(root/'ecu'); self.addCleanup(self.ecu.close); self.ecu.publish(self.record, self.cal, catalog=self.catalog)
        self.ref = ReferenceReleaseStore(root/'ref'); self.addCleanup(self.ref.close); self.ref.publish(self.p)
        self.assets = AssetStore(root); self.addCleanup(self.assets.close)
        self.lib = ReferenceLibrary(); self.lib.register(self.p)
    def compile(self, profile=None, **kwargs):
        args = dict(capabilities=self.caps, asset_store=self.assets, reference_release_store=self.ref, library=self.lib)
        args.update(kwargs)
        return compile_profile(profile or self.p, 'pcb_exposed_top', 'photo', self.record, self.catalog, self.ecu, self.cal, **args)
    def test_end_to_end(self):
        bundle = self.compile(); self.assertEqual(bundle.asset_hashes[0].bytes, len(self.data))
        ps = {k: Profile(k,k,'1','r1',True,{'basic'},{'basic'},self.cal) for k in PROFILE_KINDS}; ps['ecu'] = bundle.core_profile
        self.assertEqual(validate_profiles(ps,self.cal,{}), [])
        ctx = Context('session',{k:'r1' for k in PROFILE_KINDS},'scene',100,'frame')
        obs = ObservedECU('frame',(0,0,0),0,100,'scene','r1','ETC3','synthetic_variant','ref')
        a = create_plan(ctx,ps,self.cal,{},obs,100,10,min_coverage=1,require_raw=False)
        b = create_plan(ctx,ps,self.cal,{},replace(obs,position_mm=(5,3,0),yaw_rad=math.pi/2),100,10,min_coverage=1,require_raw=False)
        self.assertEqual(a.targets[0].local_xyz_mm,b.targets[0].local_xyz_mm); self.assertNotEqual(a.targets[0].scene_xyz_mm,b.targets[0].scene_xyz_mm)
    def test_missing_release(self):
        (Path(self.tmp.name)/'ref'/self.ref._name('synthetic','r1')).unlink()
        with self.assertRaises(ValueError): self.compile()
    def test_asset_altered(self):
        (Path(self.tmp.name)/'private/image.png').write_bytes(b'x'*len(self.data))
        with self.assertRaises(ValueError): self.compile()
    def test_asset_symlink_final(self):
        p=Path(self.tmp.name)/'private/image.png'; p.unlink(); p.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.compile()
    def test_asset_symlink_directory(self):
        p=Path(self.tmp.name)/'private'; (p/'image.png').unlink(); p.rmdir(); p.symlink_to('/tmp')
        with self.assertRaises(ValueError): self.compile()
    def test_asset_traversal(self):
        a=dict(self.p.data['reference_assets']['assets'][0]); a['relative_path']='../x'
        with self.assertRaises(ValueError): self.assets.verify_asset(a)
    def test_asset_large(self):
        a=dict(self.p.data['reference_assets']['assets'][0]); a['bytes']=128*1024*1024+1
        with self.assertRaises(ValueError): self.assets.verify_asset(a)
    def test_asset_mime(self):
        a=dict(self.p.data['reference_assets']['assets'][0]); a['mime']='text/plain'
        with self.assertRaises(ValueError): self.assets.verify_asset(a)
    def test_library_exact(self):
        with self.assertRaises(ValueError): self.lib.select('ETC3','other','r1')
    def test_library_mutation(self):
        object.__setattr__(self.p,'data',load_json(json.dumps(synthetic_profile())).data)
        with self.assertRaises(ValueError): self.lib.select('ETC3','synthetic_variant','r1')
    def test_duplicate_release(self):
        with self.assertRaises(FileExistsError): self.ref.publish(self.p)
    def test_changed_release(self):
        (Path(self.tmp.name)/'ref'/self.ref._name('synthetic','r1')).write_text('{}')
        with self.assertRaises(ValueError): self.compile()
    def test_missing_capabilities(self):
        with self.assertRaises(ValueError): self.compile(capabilities=set())
    def test_missing_asset_store(self):
        with self.assertRaises(ValueError): self.compile(asset_store=None)
    def test_wrong_state(self):
        with self.assertRaises(ValueError): compile_profile(self.p,'closed','photo',self.record,self.catalog,self.ecu,self.cal,capabilities=self.caps,asset_store=self.assets,reference_release_store=self.ref)
    def test_wrong_recipe(self):
        with self.assertRaises(ValueError): compile_profile(self.p,'pcb_exposed_top','bad',self.record,self.catalog,self.ecu,self.cal,capabilities=self.caps,asset_store=self.assets,reference_release_store=self.ref)
    def test_missing_calibration(self):
        with self.assertRaises(ValueError): compile_profile(self.p,'pcb_exposed_top','photo',self.record,self.catalog,self.ecu,{},capabilities=self.caps,asset_store=self.assets,reference_release_store=self.ref)
    def modified(self, fn):
        fn(self.d); p=seal(self.d)
        # Publish each modified test snapshot into a fresh release namespace.
        folder=Path(self.tmp.name)/'modified'; folder.mkdir(); store=ReferenceReleaseStore(folder); self.addCleanup(store.close); store.publish(p)
        return p, store
    def test_wrong_variant(self):
        p,s=self.modified(lambda d:d['metadata'].update(variant_id='other'))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_wrong_revision(self):
        p,s=self.modified(lambda d:d['metadata'].update(profile_revision='r2'))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_goal_mismatch(self):
        p,s=self.modified(lambda d:d['photography_recipes']['recipes'][0]['views'][0]['camera_goal'].update(translation_mm=[11,20,50]))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_quaternion_mismatch(self):
        p,s=self.modified(lambda d:d['photography_recipes']['recipes'][0]['views'][0]['camera_goal'].update(quaternion_xyzw=[0,0,1,0]))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_roi_mismatch(self):
        p,s=self.modified(lambda d:d['pcb_definition']['regions_of_interest'][0].update(rectangle_xywh_mm=[0,0,2,2]))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_envelope_mismatch(self):
        p,s=self.modified(lambda d:d['geometry']['per_physical_state'][1].update(envelope_xyz_mm=[101,80,20]))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_module_registry_required(self):
        p,s=self.modified(lambda d:d['inspection_workflows']['recipes'][0].update(required_modules=['vision']))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_draft(self):
        self.d['metadata']['status']='DRAFT'; p=seal(self.d)
        with self.assertRaises(ValueError): self.compile(p)
    def test_scope_not_approved(self):
        p,s=self.modified(lambda d:d['metadata'].update(approval_scopes=[]))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None)
    def test_unknown_module(self):
        from vision_core.extensions import ModuleRegistry, ScenarioSpec, StageSpec
        p,s=self.modified(lambda d:d['inspection_workflows']['recipes'][0].update(required_modules=['vision']))
        scenario=ScenarioSpec('inspection','1',(StageSpec('S01',(),frozenset({'check'})),),('vision',))
        with self.assertRaises(ValueError): self.compile(p,reference_release_store=s,library=None,module_registry=ModuleRegistry(),scenario_spec=scenario)
    def test_release_symlink(self):
        path=Path(self.tmp.name)/'ref'/self.ref._name('synthetic','r1'); path.unlink(); path.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): self.compile()
