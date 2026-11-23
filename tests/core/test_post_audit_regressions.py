"""Independent second-review regressions, must fail before and pass after fixes."""
import os
import tempfile
import unittest
from vision_core import Journal, Workflow, Evidence, GateError, State
from vision_core.workflow import CHECKS
import test_workflow as fx


class SecondAudit(unittest.TestCase):
    def test_stale_instance_cannot_reverse_restart_block(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'events.sqlite')
            first_j=Journal(path)
            ctx=fx.context()
            opts=dict(context=ctx,profiles=fx.profiles(),calibrations={'cal':'v1'},
                 requirements={},max_age=10,clock=lambda:fx.NOW)
            first=Workflow(first_j,**opts)
            first.start('S01','request-first')
            # Simulate second process reconstructing an unfinished session,
            # which must durably block/require external reconciliation.
            second_j=Journal(path)
            recovered=Workflow(second_j,**opts)
            self.assertEqual(recovered.states['S01'],State.BLOCKED)
            evidence=Evidence(ctx.session_id,'S01','request-first',ctx,fx.NOW,True,True,
                 frozenset(CHECKS['S01']),'late-result')
            try:
                with self.assertRaises(GateError):
                    first.complete(evidence)
                with self.assertRaises(GateError):
                    first.start('S02','request-after-block')
                self.assertEqual([e.step_id for e in first_j.replay(ctx.session_id)
                                  if e.kind=='dispatch'],['S01'])
            finally:
                first_j.close(); second_j.close()

    def test_cannot_relax_pinned_freshness_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=os.path.join(root,'events.sqlite')
            ctx=fx.context()
            j=Journal(path)
            original=Workflow(j,ctx,fx.profiles(),{'cal':'v1'},{},10,lambda:fx.NOW)
            original.start('S01','req-S01')
            original.complete(Evidence(ctx.session_id,'S01','req-S01',ctx,fx.NOW,True,True,
                     frozenset(CHECKS['S01']),'valid'))
            j.close()
            reopened=Journal(path)
            changed=Workflow(reopened,ctx,fx.profiles(),{'cal':'v1'},{},100,lambda:fx.NOW+30)
            try:
                with self.assertRaises(GateError):
                    changed.start('S02','req-S02')
                self.assertEqual(changed.states['S02'],State.BLOCKED)
            finally:
                reopened.close()

    def test_live_freshness_mutation_blocks_completion(self):
        with tempfile.TemporaryDirectory() as root:
            j = Journal(os.path.join(root, 'journal'))
            ctx = fx.context()
            w = Workflow(j, ctx, fx.profiles(), {'cal': 'v1'}, {}, 10, lambda: fx.NOW)
            w.start('S01', 'req')
            w.max_age = 100
            with self.assertRaises(GateError):
                w.complete(Evidence(ctx.session_id, 'S01', 'req', ctx, fx.NOW, True, True, frozenset(CHECKS['S01']), 'result'))
            self.assertEqual(w.states['S02'], State.BLOCKED)
            j.close()

    def test_concurrent_completions_only_one_commits(self):
        import copy
        import threading
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'journal')
            j, other = Journal(path), Journal(path)
            ctx = fx.context()
            w = Workflow(j, ctx, fx.profiles(), {'cal': 'v1'}, {}, 10, lambda: fx.NOW)
            w.start('S01', 'req')
            second = copy.copy(w)
            second.journal = other
            second.states = dict(w.states)
            barrier = threading.Barrier(2)
            outcomes = []
            evidence = Evidence(ctx.session_id, 'S01', 'req', ctx, fx.NOW, True, True, frozenset(CHECKS['S01']), 'result')
            def complete(worker):
                barrier.wait()
                try:
                    worker.complete(evidence)
                    outcomes.append('accepted')
                except GateError:
                    outcomes.append('rejected')
            threads = [threading.Thread(target=complete, args=(worker,)) for worker in (w, second)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertCountEqual(outcomes, ['accepted', 'rejected'])
            self.assertEqual(sum(e.kind == 'result_accepted' for e in j.replay(ctx.session_id)), 1)
            j.close(); other.close()
