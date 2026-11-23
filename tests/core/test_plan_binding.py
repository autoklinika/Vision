import os
import tempfile
import unittest
from dataclasses import replace

import test_workflow as foundation
from vision_core import Evidence, GateError, Journal, Workflow, State
from vision_core.archive import Archive
from vision_core.photography import PhotographySession, CoverageProof, CaptureBinding, ResultIdentity, MotionResult, CaptureResult, Original
from vision_core.archive import digest
from vision_core.repeatability import ObservedECU, create_plan, complete_s05, photography_views, SpatialCoverageEvidence, SpatialFootprint, coverage_proof
from vision_core.workflow import CHECKS

NOW = foundation.NOW


class PlanBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'journal.sqlite')
        self.j = Journal(self.path)
        self.ctx = foundation.context()
        self.p = foundation.profiles()
        self.p['ecu'] = replace(self.p['ecu'], view_quaternions_xyzw=((0, 0, 0, 1),))
        self.w = Workflow(self.j, self.ctx, self.p, {'cal': 'v1'}, {}, 10, lambda: NOW)
        obs = ObservedECU(self.ctx.frame_id, (0, 0, 0), 0, NOW, 'scene1', 'r1', 'example', 'a', 'obs')
        self.plan = create_plan(self.ctx, self.p, {'cal': 'v1'}, {}, obs, NOW, 10, min_coverage=.8, require_raw=True)
        self.archive = Archive(self.tmp.name, 'session')

    def tearDown(self):
        self.archive.close()
        self.j.close()
        self.tmp.cleanup()

    def evidence(self, step, plan_hash=None):
        return Evidence('session', step, 'req-'+step, self.ctx, NOW, True, True, frozenset(CHECKS[step]), 'proof', plan_hash)

    def advance(self, n=6):
        for i in range(1, n+1):
            step = f'S{i:02}'
            self.w.start(step, 'req-'+step)
            if step == 'S05': complete_s05(self.w, self.plan)
            else: self.w.complete(self.evidence(step, self.plan.digest if step == 'S06' else None))

    def views(self):
        return photography_views(self.plan, self.ctx, self.p, {'cal': 'v1'}, {}, NOW, 10)

    def test_generic_plan_and_motion_binding_rejected(self):
        self.advance(4)
        self.w.start('S05', 'req-S05')
        with self.assertRaises(GateError): self.w.complete(self.evidence('S05', self.plan.digest))
        self.assertEqual(self.w.states['S06'], State.BLOCKED)

    def test_wrong_motion_hash_rejected(self):
        self.advance(5)
        self.w.start('S06', 'req-S06')
        with self.assertRaises(GateError): self.w.complete(self.evidence('S06', 'wrong'))

    def test_restart_retains_plan_and_blocks_changed_profile(self):
        self.advance()
        self.j.close()
        self.j = Journal(self.path)
        self.w = Workflow(self.j, self.ctx, self.p, {'cal': 'v1'}, {}, 10, lambda: NOW)
        self.assertEqual(self.w.accepted_plan_hash, self.plan.digest)
        self.w.start('S07', 'req-S07')
        PhotographySession(self.w, self.archive, self.views(), self.plan)
        self.w.profiles['ecu'] = replace(self.p['ecu'], view_targets=((9, 2, 3),))
        ident = ResultIdentity(self.ctx, 'req-S07', 'view_001', NOW)
        with self.assertRaises(GateError):
            PhotographySession(self.w, self.archive, self.views(), self.plan).accept_motion(MotionResult(ident, True, (1,), True, NOW, 'motion'))
        self.assertEqual(list(self.archive.path.iterdir()), [])

    def test_altered_views_and_alternate_plan(self):
        for variant in ('plan', 'target', 'orientation', 'raw', 'missing'):
            with self.subTest(variant=variant):
                f = PlanBindingTests('runTest')
                f.setUp()
                try:
                    f.advance()
                    f.w.start('S07', 'req-S07')
                    views = f.views()
                    plan = f.plan
                    if variant == 'plan':
                        plan = create_plan(f.ctx, f.p, {'cal': 'v1'}, {}, f.plan.observation, NOW, 10, min_coverage=.9, require_raw=True)
                        self.assertEqual(plan.targets[0].view_id, f.plan.targets[0].view_id)
                    elif variant == 'target': views = (replace(views[0], target=(9, 2, 3)),)
                    elif variant == 'orientation': views = (replace(views[0], orientation_xyzw=(0, 0, 1, 0)),)
                    elif variant == 'raw': views = (replace(views[0], require_raw=False),)
                    else: plan = None
                    with self.assertRaises(GateError): PhotographySession(f.w, f.archive, views, plan)
                    self.assertEqual(list(f.archive.path.iterdir()), [])
                finally:
                    f.tearDown()

    def test_stale_scene_rejected(self):
        self.advance()
        self.w.start('S07', 'req-S07')
        self.w.context = replace(self.ctx, scene_revision='other')
        with self.assertRaises(GateError): PhotographySession(self.w, self.archive, self.views(), self.plan)

    def test_wrong_coverage_plan_and_generic_completion(self):
        self.advance()
        self.w.start('S07', 'req-S07')
        photo = PhotographySession(self.w, self.archive, self.views(), self.plan)
        ident = ResultIdentity(self.ctx, 'req-S07', 'view_001', NOW)
        photo.accept_motion(MotionResult(ident, True, (1,), True, NOW, 'motion'))
        png = b'\x89PNG\r\n\x1a\nsynthetic'
        raw = b'raw'
        photo.accept_capture(CaptureResult(ident, True, True, (Original('png', png, digest(png), 'p'), Original('raw', raw, digest(raw), 'r')), 'capture'))
        photo.complete_capture()
        self.w.start('S08', 'req-S08')
        spatial = SpatialCoverageEvidence('session', self.plan.digest, 'scene1', self.ctx.profile_revisions, NOW, frozenset({'view_001'}), (SpatialFootprint('view_001', (0, 0, 10, 20), True),), 'ecu_local', 'measurement', True, photo.capture_bindings())
        proof, _ = coverage_proof(self.plan, spatial, 'req-S08', self.ctx, self.p, {'cal': 'v1'}, {}, NOW, 10)
        self.assertEqual(proof.plan_hash, self.plan.digest)
        with self.assertRaises(GateError): photo.assess(None, replace(proof, plan_hash='wrong'))

    def test_forged_capture_binding_rejected_and_replay_stays_blocked(self):
        self.advance()
        self.w.start('S07', 'req-S07')
        photo = PhotographySession(self.w, self.archive, self.views(), self.plan)
        ident = ResultIdentity(self.ctx, 'req-S07', 'view_001', NOW)
        photo.accept_motion(MotionResult(ident, True, (1,), True, NOW, 'motion'))
        png, raw = b'\x89PNG\r\n\x1a\nsynthetic', b'raw'
        photo.accept_capture(CaptureResult(ident, True, True, (Original('png', png, digest(png), 'p'), Original('raw', raw, digest(raw), 'r')), 'capture'))
        photo.complete_capture()
        bindings = photo.capture_bindings()
        spatial = SpatialCoverageEvidence('session', self.plan.digest, 'scene1', self.ctx.profile_revisions, NOW,
            frozenset({'view_001'}), (SpatialFootprint('view_001', (0, 0, 10, 20), True),),
            'ecu_local', 'measurement', True, bindings)
        for invalid in ((), (CaptureBinding('view_001', ''),), (CaptureBinding('view_001', 'z' * 64),), (CaptureBinding('other', 'a' * 64),)):
            with self.assertRaises(GateError):
                coverage_proof(self.plan, replace(spatial, capture_bindings=invalid), 'req-S08', self.ctx, self.p, {'cal': 'v1'}, {}, NOW, 10)
        self.w.start('S08', 'req-S08')
        forged = replace(spatial, capture_bindings=(CaptureBinding('view_001', 'a' * 64),))
        proof, _ = coverage_proof(self.plan, forged, 'req-S08', self.ctx, self.p, {'cal': 'v1'}, {}, NOW, 10)
        with self.assertRaises(GateError): photo.assess(None, proof)
        self.assertEqual(self.w.states['S08'], State.FAILED)
        self.j.close()
        self.j = Journal(self.path)
        self.w = Workflow(self.j, self.ctx, self.p, {'cal': 'v1'}, {}, 10, lambda: NOW)
        self.assertEqual(self.w.states['S09'], State.BLOCKED)

    def test_generic_s07_cannot_bypass_capture(self):
        self.advance()
        self.w.start('S07', 'req-S07')
        with self.assertRaises(GateError): self.w.complete(self.evidence('S07', self.plan.digest))
