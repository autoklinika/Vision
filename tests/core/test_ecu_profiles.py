"""Synthetic data only; no physical ECU geometry or calibration is asserted."""
import json
import math
import unittest
from dataclasses import replace
from pathlib import Path

from vision_modules.ecu_profiles import *
from vision_core.profiles import PROFILE_KINDS, Profile, validate_profiles
from vision_core import Context
from vision_core.repeatability import ObservedECU, create_plan


def measured(values, ref, **changes):
    p = Provenance('VERIFIED', '2026-01-01', 'synthetic_instrument', 'ecu_local', 0.2, ref)
    return Measurement(values, replace(p, **changes))


def synthetic():
    r = ECURecord(1, 'synthetic', 'ETC3', 'synthetic_variant', False, 'r1', 'READY_FOR_REVIEW', 'ETC3',
        (Connector('a', 'black', measured((1, 1, 1), 'landmark'), True),), (),
        measured((100, 80, 20), 'body'), (measured((5, 5, 80, 60), 'pcb'),),
        (ViewTarget('v1', measured((10, 20, 50), 'view'), (0, 0, 0, 1), 1, True, measured((0,), 'orientation').provenance),),
        ('basic',), ('basic',), (('cal', 'v1'),), None)
    a = ApprovalEvidence(r.profile_id, r.revision, record_sha256(r), 'reviewer', '2026-01-02T12:00:00Z', 'review-record')
    return replace(r, status='APPROVED', approval=a)


def promote(record, calibrations):
    catalog = ECUCatalog()
    catalog.register(record)
    return to_core_ecu_profile(record, calibrations, catalog=catalog)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.draft = load_json(Path('config/ecu_profiles/etc3_poc_v1.json').read_bytes())
        self.good = synthetic()
        self.cal = {'cal': 'v1'}

    def test_draft_roundtrip(self):
        self.assertEqual(load_json(canonical_json(self.draft)), self.draft)
        self.assertEqual(record_sha256(load_json(canonical_json(self.draft))), record_sha256(self.draft))
    def test_draft_facts(self):
        self.assertEqual([c.color for c in self.draft.connectors].count('black'), 2)
        self.assertEqual([c.color for c in self.draft.connectors].count('gray'), 1)
        self.assertEqual({n.reported_height_mm for n in self.draft.field_notes}, {65, 69})
        self.assertTrue(all(n.provenance.datum is None for n in self.draft.field_notes))
        self.assertIsNone(self.draft.envelope); self.assertFalse(self.draft.views); self.assertFalse(self.draft.pcb_regions)
        self.assertFalse(self.draft.variant_is_manufacturer)
    def test_draft_blocked(self):
        self.assertTrue(validate_draft(self.draft))
        with self.assertRaises(ValueError): promote(self.draft, self.cal)
    def test_oversized(self):
        with self.assertRaises(ValueError): load_json(b' ' * (512 * 1024 + 1))
    def test_non_utf8(self):
        with self.assertRaises(ValueError): load_json(b'\xff')
    def test_malformed(self):
        with self.assertRaises(ValueError): load_json('{')
    def test_duplicate_key(self):
        with self.assertRaises(ValueError): load_json('{"schema_version":1,"schema_version":1}')
    def test_unknown(self):
        d = json.loads(canonical_json(self.draft)); d['unknown'] = 1
        with self.assertRaises(ValueError): load_json(json.dumps(d))
    def test_missing(self):
        d = json.loads(canonical_json(self.draft)); del d['variant']
        with self.assertRaises(ValueError): load_json(json.dumps(d))
    def test_schema(self):
        with self.assertRaises(ValueError): replace(self.draft, schema_version=2)
    def test_nan(self):
        with self.assertRaises(ValueError): load_json(canonical_json(self.draft).replace('69', 'NaN'))
    def test_float_bound(self):
        with self.assertRaises(ValueError): measured((1e12, 2, 3), 'body')
    def test_identifier(self):
        with self.assertRaises(ValueError): replace(self.draft, profile_id='../etc')
    def test_duplicate_connector(self):
        with self.assertRaises(ValueError): replace(self.draft, connectors=(self.draft.connectors[0],)*2)
    def test_invalid_color(self):
        with self.assertRaises(ValueError): Connector('a', 'orange', None, False)
    def test_catalog_revision_immutable(self):
        cat = ECUCatalog(); cat.register(self.good); self.assertEqual(cat.get('ETC3', 'synthetic_variant', 'r1'), self.good)
        with self.assertRaises(ValueError): cat.register(replace(self.good, declared_type='other'))
    def test_catalog_tamper(self):
        cat = ECUCatalog(); cat.register(self.good)
        object.__setattr__(self.good, 'declared_type', 'changed')
        with self.assertRaises(ValueError): cat.get('ETC3', 'synthetic_variant', 'r1')
    def test_positive_release(self):
        self.assertFalse(validate_draft(self.good)); self.assertTrue(promote(self.good, self.cal).approved)
    def test_tampered_sha(self):
        with self.assertRaises(ValueError): promote(replace(self.good, declared_type='other'), self.cal)
    def test_false_review(self):
        with self.assertRaises(ValueError): promote(replace(self.good, status='READY_FOR_REVIEW'), self.cal)
    def test_missing_approval(self):
        with self.assertRaises(ValueError): promote(replace(self.good, approval=None), self.cal)
    def test_fake_approval(self):
        with self.assertRaises(ValueError): replace(self.good, approval=True)
    def test_incomplete_body(self):
        self.assertTrue(validate_draft(replace(self.good, envelope=None)))
    def test_unknown_datum(self):
        self.assertTrue(validate_draft(replace(self.good, envelope=measured((100, 80, 20), 'body', datum=None))))
    def test_missing_source(self):
        with self.assertRaises(ValueError): Provenance('VERIFIED', '2026-01-01', 'i', 'ecu_local', 1, '')
    def test_missing_uncertainty(self):
        self.assertTrue(validate_draft(replace(self.good, envelope=measured((100,80,20),'body', uncertainty_mm=None))))
    def test_calibration(self):
        with self.assertRaises(ValueError): promote(self.good, {'cal': 'v2'})
    def test_outside_pcb(self):
        self.assertTrue(validate_draft(replace(self.good, pcb_regions=(measured((90, 0, 20, 10), 'pcb'),))))
    def test_zero_tolerance(self):
        with self.assertRaises(ValueError): replace(self.good.views[0], tolerance_mm=0)
    def test_missing_quaternion(self):
        self.assertTrue(validate_draft(replace(self.good, views=(replace(self.good.views[0], quaternion_xyzw=None),))))
    def test_wrong_quaternion(self):
        with self.assertRaises(ValueError): replace(self.good.views[0], quaternion_xyzw=(0,0,0,2))
    def test_negative_dimensions(self):
        self.assertTrue(validate_draft(replace(self.good, envelope=measured((100, 80, -1), 'body'))))
    def test_unverified_landmarks(self):
        self.assertTrue(validate_draft(replace(self.good, connectors=(replace(self.good.connectors[0], position=None),))))
    def test_same_reference(self):
        self.assertTrue(validate_draft(replace(self.good, pcb_regions=(measured((5,5,10,10), 'body'),))))

    def observation(self, **changes):
        o = ECUObservation('sensor', 'observation', 'frame', 'session', 'scene', 'r1', 100, (ObservedConnector('a', 'black', (1,1,1)),), True, True)
        return replace(o, **changes)
    def verify(self, observation=None, declaration=None, **context):
        catalog = ECUCatalog(); catalog.register(self.good)
        return verify_declared_ecu(self.good, declaration or Declaration('ETC3','synthetic_variant','r1','operator'), observation or self.observation(), session_id=context.get('session_id','session'), frame_id=context.get('frame_id','frame'), scene_revision=context.get('scene_revision','scene'), now=100, max_age=10, calibrations=self.cal, catalog=catalog)
    def test_verified_observation(self): self.assertEqual(self.verify().status, 'ACCEPTED')
    def test_wrong_variant(self): self.assertEqual(self.verify(declaration=Declaration('ETC3','wrong','r1','operator')).status, 'REJECTED')
    def test_wrong_family(self): self.assertEqual(self.verify(declaration=Declaration('wrong','synthetic_variant','r1','operator')).status, 'REJECTED')
    def test_stale(self): self.assertEqual(self.verify(self.observation(timestamp=89)).status, 'REJECTED')
    def test_wrong_frame(self): self.assertEqual(self.verify(frame_id='wrong').status, 'REJECTED')
    def test_wrong_scene(self): self.assertEqual(self.verify(scene_revision='wrong').status, 'REJECTED')
    def test_wrong_session(self): self.assertEqual(self.verify(session_id='wrong').status, 'REJECTED')
    def test_wrong_revision(self): self.assertEqual(self.verify(self.observation(profile_revision='r2')).status, 'REJECTED')
    def test_unverified_observation(self): self.assertEqual(self.verify(self.observation(verified=False)).status, 'REJECTED')
    def test_self_attested_observation(self): self.assertEqual(self.verify(self.observation(source='operator')).status, 'REJECTED')
    def test_wrong_landmark(self): self.assertEqual(self.verify(self.observation(connectors=(ObservedConnector('a','black',(10,10,10)),))).status, 'REJECTED')
    def test_connector_hint_insufficient(self): self.assertEqual(self.verify(self.observation(connectors=(ObservedConnector('a','black',None),))).status, 'REJECTED')
    def test_preliminary_draft(self):
        obs = ECUObservation('sensor','ref','frame','session','scene','v1',100,tuple(ObservedConnector(c.connector_id,c.color,None) for c in self.draft.connectors),True,True)
        result = verify_declared_ecu(self.draft, Declaration('ETC3','provisional_3connector','v1','operator'), obs, session_id='session',frame_id='frame',scene_revision='scene',now=100,max_age=10,calibrations={})
        self.assertEqual(result.status, 'PRELIMINARY')
    def test_core_plan_pose(self):
        ps = {k: Profile(k,k,'1','r1',True,{'basic'},{'basic'},self.cal) for k in PROFILE_KINDS}
        ps['ecu'] = promote(self.good, self.cal)
        self.assertEqual(validate_profiles(ps,self.cal,{}), [])
        ctx = Context('session', {k:'r1' for k in PROFILE_KINDS}, 'scene',100,'frame')
        obs = ObservedECU('frame',(0,0,0),0,100,'scene','r1','ETC3','synthetic_variant','ref')
        a = create_plan(ctx,ps,self.cal,{},obs,100,10,min_coverage=1,require_raw=False)
        b = create_plan(ctx,ps,self.cal,{},replace(obs,position_mm=(5,3,0),yaw_rad=math.pi/2),100,10,min_coverage=1,require_raw=False)
        self.assertEqual(a.targets[0].local_xyz_mm,b.targets[0].local_xyz_mm)
        self.assertNotEqual(a.targets[0].scene_xyz_mm,b.targets[0].scene_xyz_mm)
        self.assertNotEqual(a.targets[0].scene_quaternion,b.targets[0].scene_quaternion)
