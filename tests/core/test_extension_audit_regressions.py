"""Adversarial extension tests, deliberately separate from implementer fixture."""
import unittest
from vision_core.extensions import ModuleRegistry, ModuleSpec, ScenarioSpec, StageSpec
from vision_core.workflow import CHECKS, STAGES, Workflow


class RequiredStageReachability(unittest.TestCase):
    def test_declared_required_module_cannot_be_skipped_by_S11(self):
        module = ModuleSpec('thermal','1','thermal',{'thermal.frame'},True,('THERMAL_CAPTURE',))
        registry=ModuleRegistry()
        registry.register(module)
        stages=[]
        for i,s in enumerate(STAGES):
            if s=='S09':
                stages.append(StageSpec('THERMAL_CAPTURE',('S08',),{'verified'},'thermal'))
            stages.append(StageSpec(s,() if i==0 else (STAGES[i-1],),CHECKS[s]))
        # There is no dependency from S09/S10/S11 to THERMAL_CAPTURE.
        # This must be rejected at scenario registration time; otherwise
        # S11 can be marked successful without executing the REQUIRED thermal stage.
        scenario=ScenarioSpec('thermal-missing-join','1',tuple(stages),('thermal',))
        with self.assertRaises(ValueError):
            validate_required_modules_reachable(scenario,registry)


def validate_required_modules_reachable(scenario,registry):
    # This is an intentionally public API contract test:
    # validation should be in ScenarioSpec or Workflow constructor, not test logic.
    from test_workflow import NOW,profiles,context
    from vision_core import Profile, Journal
    from dataclasses import replace
    ps=profiles()
    m=registry.resolve('thermal')
    ps['thermal']=Profile('thermal','mock','1','r1',True,m.capabilities,frozenset(),{'cal':'v1'})
    ctx=replace(context(),profile_revisions={**context().profile_revisions,'thermal':'r1'})
    journal=Journal(':memory:')
    try:
        Workflow(journal,ctx,ps,{'cal':'v1'},{},10,lambda:NOW,scenario=scenario,registry=registry)
    finally:
        journal.close()

class CompletedSessionValidity(unittest.TestCase):
    def test_completed_session_with_changed_scenario_is_not_successful(self):
        from test_extensions import ExtensionsTests
        from vision_core import Evidence, State
        from vision_core.workflow import CHECKS
        from test_workflow import NOW
        from dataclasses import replace
        x=ExtensionsTests()
        x.setUp()
        try:
            for stage in x.w.stages:
                x.w.start(stage,stage)
                if stage in ('T1','V1','JOIN'):
                    x.w.verify_module_receipt(x.receipt(stage), b'data')
                checks=CHECKS[stage] if stage in CHECKS else {'verified'}
                x.w.complete(Evidence(x.ctx.session_id,stage,stage,x.ctx,NOW,True,True,frozenset(checks),'ref'))
            self.assertEqual(x.w.states['S11'],State.SUCCEEDED)
            changed=x.make(scenario=replace(x.scenario,version='new-scenario'))
            self.assertNotEqual(changed.states['S11'],State.SUCCEEDED)
            self.assertTrue(any(e.kind=='context_invalidated' for e in x.j.replay(x.ctx.session_id)))
        finally: x.tearDown()

class ModuleRequiredVsPermittedStages(unittest.TestCase):
    def test_required_stage_missing_is_rejected_but_permitted_optional_is_legal(self):
        from test_workflow import NOW, profiles, context
        from vision_core import Profile, Journal
        from dataclasses import replace
        from vision_core.extensions import ModuleRegistry, ModuleSpec, StageSpec, ScenarioSpec
        stages=[]
        for i,s in enumerate(STAGES):
            if s=='S04':
                stages.append(StageSpec('T1',('S03',),{'verified'},'thermal'))
            dependencies=() if i==0 else (STAGES[i-1],)
            if s=='S04':
                dependencies=('S03','T1')
            stages.append(StageSpec(s,dependencies,CHECKS[s]))
        scenario=ScenarioSpec('thermal-with-optional','1',tuple(stages),('thermal',))
        def run(required):
            m=ModuleSpec('thermal','1','thermal',{'thermal.frame'},True,('T1','T2'),required_stage_ids=required)
            reg=ModuleRegistry()
            reg.register(m)
            ps=profiles()
            ps['thermal']=Profile('thermal','mock','1','r1',True,m.capabilities,frozenset(),{'cal':'v1'})
            ctx=replace(context(),profile_revisions={**context().profile_revisions,'thermal':'r1'})
            j=Journal(':memory:')
            try:
                return Workflow(j,ctx,ps,{'cal':'v1'},{},10,lambda:NOW,scenario=scenario,registry=reg)
            finally:
                j.close()
        self.assertIsNotNone(run(('T1',)))
        with self.assertRaises(ValueError):
            run(('T1','T2'))
