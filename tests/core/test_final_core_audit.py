"""Independent final pre-merge state-machine regression tests."""
import os
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch
import test_workflow as base
from vision_core import Journal,Workflow,Evidence,GateError,State
from vision_core.workflow import CHECKS
from vision_core.extensions import StageSpec,ScenarioSpec

class TransactionalResultRegression(unittest.TestCase):
    def fresh(self,root):
        j=Journal(os.path.join(root,'j.sqlite'))
        c=base.context()
        w=Workflow(j,c,base.profiles(),{'cal':'v1'},{},10,lambda:base.NOW)
        return j,w,c

    def test_failed_result_commit_never_exposes_succeeded_in_memory(self):
        with tempfile.TemporaryDirectory() as root:
            j,w,c=self.fresh(root)
            try:
                w.start('S01','req')
                result=Evidence(c.session_id,'S01','req',c,base.NOW,True,True,frozenset(CHECKS['S01']),'evidence')
                tx=j.transaction
                @contextmanager
                def failure():
                    with tx():
                        yield
                        raise OSError('synthetic write fault before commit')
                with patch.object(j,'transaction',failure):
                    with self.assertRaises(OSError):
                        w.complete(result)
                self.assertNotEqual(w.states['S01'],State.SUCCEEDED)
                self.assertTrue(w._journal_uncertain)
                with self.assertRaises(GateError):w.complete(result)
            finally:j.close()

    def test_failed_invalidation_cannot_be_retried_then_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            j,w,c=self.fresh(root)
            try:
                tx=j.transaction
                @contextmanager
                def failure():
                    with tx():
                        yield
                        raise OSError('synthetic invalidation write fault')
                with patch.object(j,'transaction',failure):
                    with self.assertRaises(OSError):w.invalidate('scene changed')
                self.assertTrue(w._journal_uncertain)
                with self.assertRaises(GateError):w.invalidate('retry')
                with self.assertRaises(GateError):w.start('S01','try-again')
                self.assertNotIn('S01',[e.step_id for e in j.replay(c.session_id) if e.kind=='dispatch'])
            finally:j.close()

    def test_simultaneous_config_and_context_change_replays_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            j,w,c=self.fresh(root)
            try:
                w.start('S01','req')
                w.complete(Evidence(c.session_id,'S01','req',c,base.NOW,True,True,frozenset(CHECKS['S01']),'ok'))
                other=Workflow(j,replace(c,frame_id='another-frame'),base.profiles(),{'cal':'v1'},{},11,lambda:base.NOW)
                self.assertEqual(other.states['S11'],State.BLOCKED)
                self.assertEqual(sum(e.kind=='context_invalidated' for e in j.replay(c.session_id)),1)
            finally:j.close()

class GraphBoundTest(unittest.TestCase):
    def test_large_scenario_rejected_during_schema_validation(self):
        nodes=[StageSpec('G'+str(i),() if i==0 else ('G'+str(i-1),),{'done'}) for i in range(350)]
        with self.assertRaises(ValueError):
            ScenarioSpec('huge','1',tuple(nodes),())
