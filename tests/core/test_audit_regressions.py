import os
import tempfile
import unittest
from dataclasses import replace
import test_workflow as foundation
from vision_core import Context, Evidence, GateError, Journal, Workflow, State
from vision_core.workflow import CHECKS
NOW=foundation.NOW

class AdversarialGates(unittest.TestCase):
    def test_double_instance_cannot_dispatch_same_stage(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'journal.sqlite')
            a,b=Journal(path),Journal(path)
            ctx=foundation.context()
            opts=dict(context=ctx,profiles=foundation.profiles(),calibrations={'cal':'v1'},requirements={},max_age=10,clock=lambda:NOW)
            first=Workflow(a,**opts); second=Workflow(b,**opts)
            try:
                first.start('S01','req-first')
                with self.assertRaises(GateError):
                    second.start('S01','req-second')
                self.assertEqual(len([e for e in a.replay('session') if e.kind=='dispatch' and e.step_id=='S01']),1)
            finally:
                a.close();b.close()

    def test_same_revision_changed_geometry_is_rejected_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'journal.sqlite')
            a=Journal(path);ctx=foundation.context();profiles=foundation.profiles()
            first=Workflow(a,ctx,profiles,{'cal':'v1'},{},10,lambda:NOW)
            for i in range(1,7):
                step=f'S{i:02}'
                first.start(step,'request-'+step)
                first.complete(Evidence(ctx.session_id,step,'request-'+step,ctx,NOW,True,True,
                                  frozenset(CHECKS[step]),'synthetic-evidence'))
            a.close()
            b=Journal(path)
            changed=dict(profiles)
            changed['ecu']=replace(changed['ecu'],view_targets=((99,2,3),))
            after=Workflow(b,ctx,changed,{'cal':'v1'},{},10,lambda:NOW)
            try:
                with self.assertRaises(GateError):
                    after.start('S07','motion-new')
                self.assertNotEqual(after.states['S07'],State.RUNNING)
            finally:b.close()

    def test_result_before_dispatch_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            j=Journal(os.path.join(root,'journal.sqlite'));ctx=replace(foundation.context(),observation_timestamp=NOW-5)
            engine=Workflow(j,ctx,foundation.profiles(),{'cal':'v1'},{},10,lambda:NOW)
            try:
                engine.start('S01','req-fresh')
                with self.assertRaises(GateError):
                    engine.complete(Evidence(ctx.session_id,'S01','req-fresh',ctx,NOW-1,True,True,
                          frozenset(CHECKS['S01']),'synthetic-evidence'))
            finally:j.close()

    def test_partial_invalidation_cannot_resume_after_crash(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'j.sqlite');ctx=foundation.context()
            j=Journal(path)
            w=Workflow(j,ctx,foundation.profiles(),{'cal':'v1'},{},10,lambda:NOW)
            for i in range(1,7):
                s=f'S{i:02}'
                w.start(s,'req-'+s)
                w.complete(Evidence(ctx.session_id,s,'req-'+s,ctx,NOW,True,True,
                         frozenset(CHECKS[s]),'synthetic-evidence'))
            # Simulate crash just after invalidation event, before blocked transitions.
            j.append(ctx.session_id,'','','context_invalidated',{'reason':'changed scene'})
            j.close()
            reopened=Journal(path)
            other=Workflow(reopened,ctx,foundation.profiles(),{'cal':'v1'},{},10,lambda:NOW)
            try:
                with self.assertRaises(GateError):
                    other.start('S07','unsafe-after-restart')
            finally: reopened.close()

if __name__=='__main__': unittest.main()


class AuditPhotoPlanTest(unittest.TestCase):
    def test_photo_requires_accepted_s05_plan(self):
        from vision_core.repeatability import ObservedECU, create_plan, complete_s05
        from vision_core.photography import View, PhotographySession
        from vision_core.archive import Archive
        with tempfile.TemporaryDirectory() as root:
            journal=Journal(os.path.join(root,'events.sqlite'))
            ctx=foundation.context()
            profiles=foundation.profiles()
            profiles['ecu']=replace(profiles['ecu'], view_quaternions_xyzw=((0,0,0,1),))
            workflow=Workflow(journal,ctx,profiles,{'cal':'v1'},{},10,lambda:NOW)
            observation=ObservedECU(ctx.frame_id,(0,0,0),0,NOW,'scene1','r1','example','a','synthetic')
            plan=create_plan(ctx,profiles,{'cal':'v1'},{},observation,NOW,10,min_coverage=.8,require_raw=True)
            archive=Archive(root,ctx.session_id)
            try:
                for i in range(1,7):
                    step=f'S{i:02}'
                    workflow.start(step,'req-'+step)
                    if step=='S05':
                        complete_s05(workflow,plan)
                    else:
                        workflow.complete(Evidence(ctx.session_id,step,'req-'+step,ctx,NOW,True,True,
                               frozenset(CHECKS[step]),'synthetic-terminal-evidence', plan.digest if step == 'S06' else None))
                workflow.start('S07','req-S07')
                changed=(View('view_001',(99,99,99),False,(0,0,0,1)),)
                with self.assertRaises(GateError):
                    PhotographySession(workflow,archive,changed)
            finally:
                archive.close()
                journal.close()
