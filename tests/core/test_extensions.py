import hashlib
import unittest
from dataclasses import dataclass, replace

from test_workflow import NOW, profiles
from vision_core import Context, Evidence, GateError, Journal, Profile, State, Workflow
from vision_core.extensions import ModuleRegistry, ModuleSpec, ModuleReceipt, ScenarioSpec, StageSpec
from vision_core.workflow import STAGES, CHECKS


def fixture():
    modules = [ModuleSpec('thermal', '1', 'thermal', {'heat'}, True, ('T1',)),
               ModuleSpec('vibration', '1', 'vibration', {'vibe'}, True, ('V1', 'JOIN'))]
    registry = ModuleRegistry()
    for m in modules: registry.register(m)
    stages = []
    for i, name in enumerate(STAGES):
        deps = [] if not i else [STAGES[i-1]]
        if name == 'S04':
            stages.extend([StageSpec('T1', ('S03',), {'verified'}, 'thermal'),
                           StageSpec('V1', ('S03',), {'verified'}, 'vibration'),
                           StageSpec('JOIN', ('T1', 'V1'), {'verified'}, 'vibration')])
            deps.append('JOIN')
        stages.append(StageSpec(name, tuple(deps), CHECKS[name]))
    return modules, registry, ScenarioSpec('synthetic', '1', tuple(stages), ('thermal', 'vibration'))

class ExtensionsTests(unittest.TestCase):
    def setUp(self):
        self.modules, self.registry, self.scenario = fixture()
        self.ps = profiles()
        for m in self.modules:
            self.ps[m.profile_kind] = Profile(m.profile_kind, m.module_id, '1', 'r1', True, m.capabilities, frozenset(), {'cal': 'v1'})
        self.ctx = Context('extension', {k: 'r1' for k in self.ps}, 'scene', NOW, 'frame')
        self.j = Journal(':memory:')
        self.w = self.make()
    def tearDown(self): self.j.close()
    def make(self, scenario=None, registry=None, **kw):
        return Workflow(self.j, self.ctx, kw.get('profiles', self.ps), kw.get('calibrations', {'cal': 'v1'}), {}, kw.get('max_age', 10), lambda: NOW, scenario=scenario or self.scenario, registry=registry or self.registry)
    def advance(self):
        for stage in STAGES[:3]:
            self.w.start(stage, stage)
            self.w.complete(Evidence(self.ctx.session_id, stage, stage, self.ctx, NOW, True, True, frozenset(CHECKS[stage]), 'ref'))
    def receipt(self, stage='T1', **changes):
        module = self.modules[0 if stage == 'T1' else 1]
        return replace(ModuleReceipt('extension', stage, stage, module.module_id, module.version, 'r1', self.ctx, NOW, hashlib.sha256(b'data').hexdigest(), 'ref', True), **changes)
    def evidence(self, stage):
        return Evidence('extension', stage, stage, self.ctx, NOW, True, True, frozenset({'verified'}), 'ref')
    def test_two_modules_and_join(self):
        self.advance()
        with self.assertRaises(GateError): self.w.start('JOIN', 'JOIN')
        for stage in ('T1', 'V1', 'JOIN'):
            self.w.start(stage, stage)
            self.w.verify_module_receipt(self.receipt(stage), b'data')
            self.w.complete(self.evidence(stage))
        self.w.start('S04', 'S04')
        self.assertEqual(self.w.states['JOIN'], State.SUCCEEDED)
    def test_branch_failure_only_blocks_descendants(self):
        self.advance(); self.w.start('T1', 'T1'); self.w.stop('T1', State.FAILED, 'failure')
        self.assertEqual(self.w.states['JOIN'], State.BLOCKED)
        self.assertEqual(self.w.states['S04'], State.BLOCKED)
        self.w.start('V1', 'V1')
    def test_generic_evidence_cannot_complete(self):
        self.advance(); self.w.start('T1', 'T1')
        with self.assertRaises(GateError): self.w.complete(self.evidence('T1'))
    def test_duplicate_receipt(self):
        self.advance(); self.w.start('T1', 'T1'); self.w.verify_module_receipt(self.receipt(), b'data')
        with self.assertRaises(GateError): self.w.verify_module_receipt(self.receipt(), b'data')
    def test_receipt_mismatch(self):
        self.advance(); self.w.start('T1', 'T1')
        for change in ({'module_id':'vibration'}, {'profile_revision':'bad'}, {'timestamp':NOW-11}, {'context':replace(self.ctx, scene_revision='bad')}, {'payload_sha256':'0'*64}, {'request_id':'bad'}):
            with self.subTest(change=change), self.assertRaises(GateError): self.w.verify_module_receipt(self.receipt(**change), b'data')
    def test_restart_running_blocks(self):
        self.advance(); self.w.start('T1', 'T1'); self.w.verify_module_receipt(self.receipt(), b'data')
        w = self.make()
        self.assertEqual(w.states['T1'], State.BLOCKED)
        with self.assertRaises(GateError): w.complete(self.evidence('T1'))
    def test_changed_scenario_invalidates_restart(self):
        self.advance()
        w = self.make(scenario=replace(self.scenario, version='2'))
        self.assertEqual(w.states['S04'], State.BLOCKED)
    def test_changed_descriptor_invalidates_restart(self):
        self.advance()
        registry = ModuleRegistry()
        registry.register(replace(self.modules[0], capabilities=frozenset({'heat', 'extra'})))
        registry.register(self.modules[1])
        w = self.make(registry=registry)
        self.assertEqual(w.states['S04'], State.BLOCKED)
    def test_graph_mutation_invalidates_all_branches(self):
        self.advance()
        self.w.dependencies['T1'] = ()
        with self.assertRaises(GateError): self.w.start('T1', 'T1')
        self.assertEqual(self.w.states['V1'], State.BLOCKED)
    def test_changed_max_age_invalidates_restart(self):
        self.advance(); w = self.make(max_age=11)
        self.assertEqual(w.states['S04'], State.BLOCKED)
    def test_profile_mutation_invalidates(self):
        self.advance(); self.w.profiles['thermal'] = replace(self.ps['thermal'], revision='r2')
        with self.assertRaises(GateError): self.w.start('T1', 'T1')
    def test_missing_capability(self):
        self.w.profiles['thermal'] = replace(self.ps['thermal'], capabilities=frozenset())
        with self.assertRaises(GateError): self.w.start('S01', 'S01')
    def test_missing_calibration(self):
        self.w.calibrations.clear()
        with self.assertRaises(GateError): self.w.start('S01', 'S01')
    def test_unknown_module(self):
        with self.assertRaises(ValueError): self.make(scenario=replace(self.scenario, required_module_ids=('missing',)))
    def test_duplicates_and_cycles(self):
        with self.assertRaises(ValueError): self.registry.register(self.modules[0])
        with self.assertRaises(ValueError): ScenarioSpec('x', '1', (StageSpec('a', (), {'x'}), StageSpec('a', (), {'x'})), ())
        with self.assertRaises(ValueError): ScenarioSpec('x', '1', (StageSpec('a', ('b',), {'x'}), StageSpec('b', ('a',), {'x'})), ())
    def test_builtin_checks_required(self):
        stages = list(self.scenario.stages); stages[0] = replace(stages[0], checks=frozenset({'readiness'}))
        with self.assertRaises(ValueError): self.make(scenario=replace(self.scenario, stages=tuple(stages)))
    def test_unregistered_profile_rejected(self):
        self.w.profiles['stray'] = self.ps['thermal']
        with self.assertRaises(GateError): self.w.start('S01', 'S01')

@dataclass(frozen=True)
class SyntheticThermalProfile(Profile):
    geometry: tuple = (1, 2, 3)


class ThermalIntegrationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from vision_core.repeatability import ObservedECU, create_plan
        self.tmp = tempfile.TemporaryDirectory()
        self.j = Journal(self.tmp.name + '/journal.sqlite')
        self.registry = ModuleRegistry()
        self.registry.register(ModuleSpec('thermal', '1', 'thermal', {'heat'}, True, ('T_CAPTURE', 'T_QA')))
        stages = []
        for i, name in enumerate(STAGES):
            deps = [] if not i else [STAGES[i-1]]
            if name == 'S09':
                stages.extend((StageSpec('T_CAPTURE', ('S08',), {'verified'}, 'thermal'),
                               StageSpec('T_QA', ('T_CAPTURE',), {'verified'}, 'thermal')))
                deps.append('T_QA')
            stages.append(StageSpec(name, tuple(deps), CHECKS[name]))
        self.scenario = ScenarioSpec('thermal-synthetic', '1', tuple(stages), ('thermal',))
        self.ps = profiles()
        self.ps['ecu'] = replace(self.ps['ecu'], view_targets=((1, 2, 3), (2, 3, 4)), view_quaternions_xyzw=((0, 0, 0, 1), (0, 0, 0, 1)))
        self.ps['thermal'] = SyntheticThermalProfile('thermal', 'mock', '1', 'r1', True, {'heat'}, set(), {'cal': 'v1'})
        self.ctx = Context('thermal-session', {k: 'r1' for k in self.ps}, 'scene', NOW, 'frame')
        self.obs = ObservedECU('frame', (0, 0, 0), 0, NOW, 'scene', 'r1', 'example', 'a', 'rgb-depth-observation')
        self.w = self.make()
        self.plan = create_plan(self.ctx, self.ps, {'cal': 'v1'}, {}, self.obs, NOW, 10, min_coverage=.9, require_raw=True, extra_kinds=self.w.extra_kinds)

    def tearDown(self):
        self.j.close(); self.tmp.cleanup()

    def make(self, scenario=None, ps=None):
        return Workflow(self.j, self.ctx, ps if ps is not None else self.ps, {'cal': 'v1'}, {}, 10, lambda: NOW, scenario=scenario or self.scenario, registry=self.registry)

    def ev(self, stage, reference='ref', plan_hash=None):
        checks = CHECKS.get(stage, {'verified'})
        return Evidence(self.ctx.session_id, stage, stage, self.ctx, NOW, True, True, frozenset(checks), reference, plan_hash)

    def through_s08(self):
        import cv2
        import numpy as np
        from vision_core.archive import Archive, digest
        from vision_core.photography import PhotographySession, ResultIdentity, MotionResult, CaptureResult, Original
        from vision_core.quality import QualityPolicy
        from vision_core.repeatability import complete_s05, photography_views, coverage_proof, SpatialCoverageEvidence, SpatialFootprint
        for stage in STAGES[:4]:
            self.w.start(stage, stage); self.w.complete(self.ev(stage))
        self.w.start('S05', 'S05'); complete_s05(self.w, self.plan)
        self.w.start('S06', 'S06'); self.w.complete(self.ev('S06', plan_hash=self.plan.digest))
        self.w.start('S07', 'S07')
        self.archive = Archive(self.tmp.name, self.ctx.session_id)
        self.addCleanup(self.archive.close)
        args = (self.ctx, self.ps, {'cal': 'v1'}, {}, NOW, 10)
        photo = PhotographySession(self.w, self.archive, photography_views(self.plan, *args, extra_kinds=self.w.extra_kinds), self.plan)
        for i, view in enumerate(photo.views):
            identity = ResultIdentity(self.ctx, 'S07', view.view_id, NOW)
            photo.accept_motion(MotionResult(identity, True, (0.1, 0.2), True, NOW, 'motion'))
            image = (np.indices((32, 32)).sum(axis=0) % 2 * 180 + 30 + i * 10).astype(np.uint8)
            png = cv2.imencode('.png', image)[1].tobytes(); raw = ('raw-' + view.view_id).encode()
            photo.accept_capture(CaptureResult(identity, True, True, (Original('png', png, digest(png), view.view_id+'-png'), Original('raw', raw, digest(raw), view.view_id+'-raw')), 'capture'))
        photo.complete_capture(); self.w.start('S08', 'S08')
        ids = frozenset(v.view_id for v in photo.views)
        spatial = SpatialCoverageEvidence(self.ctx.session_id, self.plan.digest, 'scene', self.ctx.profile_revisions, NOW, ids, tuple(SpatialFootprint(v, (0, 0, 10, 20), True) for v in sorted(ids)), 'ecu_local', 'measured', True, photo.capture_bindings())
        proof, fraction = coverage_proof(self.plan, spatial, 'S08', *args, extra_kinds=self.w.extra_kinds)
        self.assertEqual(fraction, 1)
        photo.assess(QualityPolicy(10, .2, .2, 5, 250, 16, 16, (0, 0, 16, 16)), proof)
        return photo

    def receipt(self, stage):
        return ModuleReceipt(self.ctx.session_id, stage, stage, 'thermal', '1', 'r1', self.ctx, NOW, hashlib.sha256(b'thermal').hexdigest(), stage+'-ref', True)

    def test_full_synthetic_session_and_replay(self):
        photo = self.through_s08()
        with self.assertRaises(GateError): self.w.start('S09', 'S09')
        for stage in ('T_CAPTURE', 'T_QA'):
            self.w.start(stage, stage)
            self.w.verify_module_receipt(self.receipt(stage), b'thermal')
            self.w.complete(self.ev(stage, stage+'-ref'))
        self.w.start('S09', 'S09'); self.w.complete(self.ev('S09'))
        self.w.start('S10', 'S10'); photo.archive_session()
        self.w.start('S11', 'S11'); self.w.complete(self.ev('S11'))
        self.assertTrue(all(state == State.SUCCEEDED for state in self.make().states.values()))
        self.assertEqual(sum(e.kind == 'module_verified' for e in self.j.replay(self.ctx.session_id)), 2)

    def test_profile_contract_and_plan_binding(self):
        from vision_core.repeatability import create_plan, verify_plan
        args = (self.ctx, self.ps, {'cal': 'v1'}, {}, self.obs, NOW, 10)
        with self.assertRaises(GateError): create_plan(*args, min_coverage=.9, require_raw=True)
        missing = dict(self.ps); del missing['thermal']
        with self.assertRaises(GateError): create_plan(self.ctx, missing, {'cal': 'v1'}, {}, self.obs, NOW, 10, min_coverage=.9, require_raw=True, extra_kinds={'thermal'})
        for changed in (replace(self.ps['thermal'], geometry=(4, 5, 6)), replace(self.ps['thermal'], capabilities={'heat', 'other'}), replace(self.ps['thermal'], calibration_dependencies={'cal': 'v1', 'other': 'v2'})):
            ps = {**self.ps, 'thermal': changed}
            with self.assertRaises(GateError): verify_plan(self.plan, self.ctx, ps, {'cal': 'v1', 'other': 'v2'}, {}, NOW, 10, extra_kinds={'thermal'})

    def test_receipt_mismatch_blocks_park(self):
        self.through_s08(); self.w.start('T_CAPTURE', 'T_CAPTURE')
        with self.assertRaises(GateError): self.w.verify_module_receipt(self.receipt('T_CAPTURE'), b'wrong')
        with self.assertRaises(GateError): self.w.complete(self.ev('T_CAPTURE', 'T_CAPTURE-ref'))
        with self.assertRaises(GateError): self.w.start('S09', 'S09')

    def test_receipt_reference_must_match(self):
        self.through_s08(); self.w.start('T_CAPTURE', 'T_CAPTURE')
        self.w.verify_module_receipt(self.receipt('T_CAPTURE'), b'thermal')
        with self.assertRaises(GateError): self.w.complete(self.ev('T_CAPTURE', 'unrelated'))

    def test_graph_change_on_restart(self):
        self.w.start('S01', 'S01'); self.w.complete(self.ev('S01'))
        stages = list(self.scenario.stages)
        index = next(i for i, s in enumerate(stages) if s.stage_id == 'T_QA')
        stages[index] = replace(stages[index], dependencies=('T_CAPTURE', 'S08'))
        restarted = self.make(scenario=replace(self.scenario, stages=tuple(stages)))
        self.assertEqual(restarted.states['S02'], State.BLOCKED)
