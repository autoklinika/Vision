import os
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_workflow as foundation
from vision_core import GateError, Journal, State, Workflow


class JournalHardeningTests(unittest.TestCase):
    def test_failed_dispatch_rolls_back_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            journal = Journal(os.path.join(root, 'journal.sqlite'))
            workflow = Workflow(journal, foundation.context(), foundation.profiles(), {'cal': 'v1'}, {}, 10, lambda: foundation.NOW)
            append = journal.append
            def fail(session, step, request, kind, data):
                if kind == 'dispatch':
                    raise OSError('injected failure')
                return append(session, step, request, kind, data)
            with patch.object(journal, 'append', side_effect=fail):
                with self.assertRaises(OSError):
                    workflow.start('S01', 'req')
            self.assertEqual(journal.replay('session'), [])
            self.assertEqual(journal.db.execute('SELECT count(*) FROM stage_claims').fetchone()[0], 0)
            self.assertEqual(workflow.states['S01'], State.BLOCKED)
            journal.close()

    def test_concurrent_connections_only_one_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'journal.sqlite')
            journals = [Journal(path), Journal(path)]
            workflows = [Workflow(j, foundation.context(), foundation.profiles(), {'cal': 'v1'}, {}, 10, lambda: foundation.NOW) for j in journals]
            barrier = threading.Barrier(2)
            outcomes = []
            def run(index):
                barrier.wait()
                try:
                    workflows[index].start('S01', 'req' + str(index))
                    outcomes.append('ok')
                except GateError:
                    outcomes.append('denied')
            threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertCountEqual(outcomes, ['ok', 'denied'])
            self.assertEqual(sum(e.kind == 'dispatch' for e in journals[0].replay('session')), 1)
            for journal in journals: journal.close()
