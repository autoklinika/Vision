"""Regression: a failing SQLite commit must poison that worker fail-closed."""
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import test_workflow as fx
from vision_core import Journal, Workflow, Evidence, GateError, State
from vision_core.workflow import CHECKS


class UncertainJournalTransaction(unittest.TestCase):
    def test_failed_stop_cannot_be_reversed_by_late_completion(self):
        with tempfile.TemporaryDirectory() as root:
            j=Journal(os.path.join(root,'journal.sqlite'))
            ctx=fx.context()
            w=Workflow(j,ctx,fx.profiles(),{'cal':'v1'},{},10,lambda:fx.NOW)
            w.start('S01','r')
            original=j.transaction
            @contextmanager
            def break_before_commit():
                with original():
                    yield
                    raise OSError('disk write uncertainty injected')
            with patch.object(j,'transaction',break_before_commit):
                with self.assertRaises(OSError):
                    w.stop('S01',State.FAILED,'failure noted')
            valid=Evidence('session','S01','r',ctx,fx.NOW,True,True,frozenset(CHECKS['S01']),'late-success')
            with self.assertRaises(GateError): w.complete(valid)
            with self.assertRaises(GateError): w.start('S02','after-write-failure')
            self.assertNotEqual(w.states['S01'],State.RUNNING)
            self.assertNotIn('S02',[e.step_id for e in j.replay('session') if e.kind=='dispatch'])
            j.close()

    def test_failed_result_persistence_cannot_be_retried_in_same_worker(self):
        with tempfile.TemporaryDirectory() as root:
            j=Journal(os.path.join(root,'journal.sqlite'))
            ctx=fx.context()
            w=Workflow(j,ctx,fx.profiles(),{'cal':'v1'},{},10,lambda:fx.NOW)
            w.start('S01','r')
            valid=Evidence('session','S01','r',ctx,fx.NOW,True,True,frozenset(CHECKS['S01']),'terminal-result')
            orig=j.append
            def fail(session,step,request,kind,data):
                if kind=='result_accepted':
                    raise OSError('simulated interrupted journal append')
                return orig(session,step,request,kind,data)
            with patch.object(j,'append',side_effect=fail):
                with self.assertRaises(OSError): w.complete(valid)
            with self.assertRaises(GateError): w.complete(valid)
            self.assertNotEqual(w.states['S01'],State.RUNNING)
            j.close()
