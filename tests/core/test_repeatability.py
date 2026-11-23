from vision_core.photography import CaptureBinding
import json
import math
import os
import tempfile
import unittest
from dataclasses import replace

import test_workflow as foundation
from vision_core import GateError, Journal, State
from vision_core.repeatability import (ObservedECU, SpatialFootprint, SpatialCoverageEvidence, RetryLedger,
    create_plan, verify_plan, photography_views, complete_s05, coverage_proof, make_manifest, verify_manifest)

NOW = foundation.NOW

class RepeatabilityTests(unittest.TestCase):
    def setUp(self):
        self.p = foundation.profiles()
        self.p['ecu'] = replace(self.p['ecu'], view_quaternions_xyzw=((0, 0, 0, 1),))
        self.c = foundation.context()
        self.obs = ObservedECU(self.c.frame_id, (10, 20, 30), 0, NOW, 'scene1', 'r1', 'example', 'a', 'synthetic-observation')
        self.args = (self.c, self.p, {'cal': 'v1'}, {}, NOW, 10)
        self.plan = self.make()

    def make(self, obs=None, ctx=None, profiles=None, threshold=.5):
        return create_plan(ctx or self.c, profiles or self.p, {'cal': 'v1'}, {}, obs or self.obs, NOW, 10, min_coverage=threshold, require_raw=True)

    def evidence(self, plan=None):
        plan = plan or self.plan
        return SpatialCoverageEvidence('session', plan.digest, 'scene1', self.c.profile_revisions, NOW,
            frozenset(t.view_id for t in plan.targets), tuple(SpatialFootprint(t.view_id, (0, 0, 10, 20), True) for t in plan.targets),
            'ecu_local', 'synthetic-measurement', True, tuple(CaptureBinding(t.view_id, 'a' * 64) for t in plan.targets))

    def proof(self, e, plan=None):
        return coverage_proof(plan or self.plan, e, 's08', *self.args)

    def test_pose_transform_and_hash(self):
        other = self.make(replace(self.obs, position_mm=(100, 200, 10), yaw_rad=math.pi/2))
        self.assertEqual(self.plan.targets[0].view_id, other.targets[0].view_id)
        self.assertEqual(self.plan.targets[0].local_xyz_mm, other.targets[0].local_xyz_mm)
        self.assertEqual(self.plan.targets[0].scene_xyz_mm, (11, 22, 33))
        for a, b in zip(other.targets[0].scene_xyz_mm, (98, 201, 13)): self.assertAlmostEqual(a, b)
        self.assertNotEqual(self.plan.digest, other.digest)
        self.assertEqual(self.plan.digest, self.make().digest)
        ps = dict(self.p); ps['tool'] = replace(ps['tool'], revision='r2')
        ctx = replace(self.c, profile_revisions={**self.c.profile_revisions, 'tool':'r2'})
        self.assertNotEqual(self.plan.digest, self.make(ctx=ctx, profiles=ps).digest)
        self.assertEqual(photography_views(self.plan, *self.args)[0].target, (1, 2, 3))

    def test_reject_bad_context(self):
        for obs in (replace(self.obs, frame_id='wrong'), replace(self.obs, scene_revision='other'),
                    replace(self.obs, timestamp=NOW-11), replace(self.obs, timestamp=NOW+1),
                    replace(self.obs, variant='other'), replace(self.obs, ecu_revision='r2'),
                    replace(self.obs, position_mm=(math.nan, 0, 0)), replace(self.obs, reference='')):
            with self.subTest(obs=obs), self.assertRaises(GateError): self.make(obs)
        with self.assertRaises(GateError): verify_plan(self.plan, replace(self.c, scene_revision='other'), *self.args[1:])
        with self.assertRaises(GateError): verify_plan(replace(self.plan, targets=self.plan.targets*2), *self.args)
        with self.assertRaises(GateError): self.make(threshold=0)

    def test_exact_union(self):
        ps = dict(self.p)
        ps['ecu'] = replace(ps['ecu'], pcb_regions=((0,0,10,10),(5,0,10,10)), view_targets=((1,2,3),(2,3,4)), view_quaternions_xyzw=((0,0,0,1),(0,0,0,1)))
        plan = self.make(profiles=ps, threshold=.6)
        e = replace(self.evidence(plan), footprints=(SpatialFootprint('view_001',(0,0,7,10),True), SpatialFootprint('view_002',(5,0,5,10),True)))
        _, ratio = coverage_proof(plan, e, 's08', self.c, ps, {'cal':'v1'}, {}, NOW, 10)
        self.assertAlmostEqual(ratio, 2/3)
        with self.assertRaises(GateError): coverage_proof(replace(plan, min_coverage=.9), e, 's08', self.c, ps, {'cal':'v1'}, {}, NOW, 10)
        outside = replace(e, footprints=tuple(replace(f, rectangle_mm=(50,50,1,1)) for f in e.footprints))
        with self.assertRaises(GateError): coverage_proof(plan, outside, 's08', self.c, ps, {'cal':'v1'}, {}, NOW, 10)

    def test_coverage_rejections_and_manifest(self):
        e = self.evidence(); proof, ratio = self.proof(e)
        self.assertTrue(proof.verified)
        for bad in (replace(e, verified=False), replace(e, provenance_reference=''), replace(e, scene_revision='other'),
                    replace(e, plan_hash='wrong'), replace(e, frame_id='world'), replace(e, timestamp=NOW-11),
                    replace(e, captured_view_ids=frozenset()), replace(e, footprints=()),
                    replace(e, footprints=(replace(e.footprints[0], verified=False),))):
            with self.subTest(bad=bad), self.assertRaises(GateError): self.proof(bad)
        manifest = make_manifest(self.plan, e, ratio, [])
        verify_manifest(manifest, self.plan, e, ratio, [])
        data = json.loads(manifest); data['document']['coverage_fraction'] = .1
        with self.assertRaises(GateError): verify_manifest(json.dumps(data), self.plan, e, ratio, [])

    def test_retry_replay_and_denials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'j.sqlite'); j = Journal(path); ledger = RetryLedger(j)
            kwargs = dict(view_id='view_001', attempt=1, request_id='new-1', failure='blur', approved=True,
                          approval_reference='operator', qa_reference='qa-result', qa_verified=True, coverage_evidence=self.evidence(), max_attempts=2)
            def decide(l, **changes): return l.decide(self.plan, *self.args, **{**kwargs, **changes})
            for change in ({'approved':False}, {'failure':'timeout'}, {'failure':'motion_failure'},
                           {'failure':'missing_transfer'}, {'qa_reference':''}, {'qa_verified':False}, {'coverage_evidence':replace(self.evidence(), verified=False)}):
                with self.subTest(change=change), self.assertRaises(GateError): decide(ledger, **change)
            first = decide(ledger); self.assertEqual(first, decide(ledger)); j.close()
            j = Journal(path); ledger = RetryLedger(j)
            self.assertEqual(first, decide(ledger))
            with self.assertRaises(GateError): decide(ledger, failure='crop')
            decide(ledger, attempt=2, request_id='new-2')
            with self.assertRaises(GateError): decide(ledger, attempt=3, request_id='new-3')
            self.assertEqual(len(ledger.decisions('session')), 2); j.close()

    def test_orientation_transform_and_adapter(self):
        other = self.make(replace(self.obs, position_mm=(100, 200, 10), yaw_rad=math.pi/2))
        self.assertEqual(self.plan.targets[0].local_quaternion, other.targets[0].local_quaternion)
        for actual, expected in zip(other.targets[0].scene_quaternion, (0, 0, math.sqrt(.5), math.sqrt(.5))):
            self.assertAlmostEqual(actual, expected)
        view = photography_views(other, *self.args)[0]
        self.assertEqual(view.orientation_xyzw, (0, 0, 0, 1))

    def test_orientation_validation(self):
        for quats in ((), ((0, 0, 0, 2),), ((0, 0, 0, 0),), ((0, 0, float('nan'), 1),),
                      ((0, 0, 0, True),), ((0, 0, 0, 1), (0, 0, 0, 1))):
            with self.subTest(quats=quats):
                ps = dict(self.p); ps['ecu'] = replace(ps['ecu'], view_quaternions_xyzw=quats)
                with self.assertRaises(GateError): self.make(profiles=ps)

    def test_geometry_same_revision_invalidates_plan(self):
        for field, value in (('nominal_dimensions', (99, 20)), ('max_height', 99),
                             ('tolerances', (99,)), ('view_quaternions_xyzw', ((0, 0, 1, 0),))):
            with self.subTest(field=field):
                ps = dict(self.p); ps['ecu'] = replace(ps['ecu'], **{field: value})
                self.assertNotEqual(self.plan.digest, self.make(profiles=ps).digest)
                with self.assertRaises(GateError):
                    verify_plan(self.plan, self.c, ps, {'cal': 'v1'}, {}, NOW, 10)

    def test_invalid_rectangles_and_age(self):
        for rect in (None, 3, (0, 0, float('nan'), 1), (0, 0, 0, 1), (0, 0, -1, 1), (0, 0, 10**1000, 1)):
            with self.subTest(rect=str(rect)[:40]):
                e = replace(self.evidence(), footprints=(SpatialFootprint('view_001', rect, True),))
                with self.assertRaises(GateError): self.proof(e)
        for age in (0, -1, float('nan'), True):
            with self.subTest(age=age), self.assertRaises(GateError):
                verify_plan(self.plan, self.c, self.p, {'cal':'v1'}, {}, NOW, age)

    def test_coverage_overlap_with_hole(self):
        ps = dict(self.p)
        ps['ecu'] = replace(ps['ecu'], pcb_regions=((0,0,10,10),), view_targets=((1,2,3),(2,3,4)),
                            view_quaternions_xyzw=((0,0,0,1),(0,0,0,1)))
        plan = self.make(profiles=ps, threshold=.8)
        e = replace(self.evidence(plan), footprints=(SpatialFootprint('view_001',(0,0,4,10),True),
                    SpatialFootprint('view_002',(3,0,4,10),True)))
        with self.assertRaises(GateError):
            coverage_proof(plan, e, 's08', self.c, ps, {'cal':'v1'}, {}, NOW, 10)
        plan = self.make(profiles=ps, threshold=.7)
        e = replace(e, plan_hash=plan.digest)
        self.assertAlmostEqual(coverage_proof(plan, e, 's08', self.c, ps, {'cal':'v1'}, {}, NOW, 10)[1], .7)

    def test_retry_stale_scene_and_request_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            j = Journal(os.path.join(tmp, 'j.sqlite')); ledger = RetryLedger(j)
            kw = dict(view_id='view_001', attempt=1, request_id='retry', failure='blur', approved=True,
                      approval_reference='operator', qa_reference='qa', qa_verified=True,
                      coverage_evidence=self.evidence(), max_attempts=2)
            ledger.decide(self.plan, *self.args, **kw)
            with self.assertRaises(GateError): ledger.decide(self.plan, *self.args, **{**kw, 'attempt': 2})
            with self.assertRaises(GateError): ledger.decide(self.plan, self.c, self.p, {'cal':'v1'}, {}, NOW+11, 10, **kw)
            with self.assertRaises(GateError): ledger.decide(self.plan, replace(self.c, scene_revision='other'), self.p, {'cal':'v1'}, {}, NOW, 10, **kw)
            j.close()

    def test_workflow_s05(self):
        f = foundation.WorkflowTests('runTest'); f.setUp()
        try:
            f.engine.profiles['ecu'] = self.p['ecu']
            f.advance(4); f.engine.start('S05', 'req-S05')
            with self.assertRaises(GateError): complete_s05(f.engine, replace(self.plan, digest='tampered'))
            self.assertEqual(f.engine.states['S05'], State.RUNNING)
            complete_s05(f.engine, self.plan)
            self.assertEqual(f.engine.states['S05'], State.SUCCEEDED)
        finally: f.tearDown()
