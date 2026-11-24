"""Independent final audit of strict proof concurrency and photography handoff."""
from contextlib import contextmanager
import copy
from dataclasses import replace
import threading
import unittest
from unittest.mock import patch

import test_strict_planning as strict_fixture
from vision_core import GateError, Journal, State, Workflow
from vision_core.archive import Archive, digest
from vision_core.photography import (
    CaptureResult, MotionResult, Original, PhotographySession, ResultIdentity,
)
from vision_core.repeatability import photography_views


class FinalCorePlanningAudit(unittest.TestCase):
    def setUp(self):
        self.fixture = strict_fixture.StrictPlanningTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_concurrent_s06_results_commit_only_one_motion_hash(self):
        f = self.fixture
        f.before_s06()
        other_journal = Journal(f.path)
        self.addCleanup(other_journal.close)
        other = copy.copy(f.w)
        other.journal = other_journal
        other.states = dict(f.w.states)
        barrier = threading.Barrier(2)
        outcomes = []

        def finish(worker, motion_hash):
            proof = replace(f.motion(), motion_hash=motion_hash,
                            reference='motion-plan:sha256:' + motion_hash)
            evidence = f.evidence('S06', reference=proof.reference)
            barrier.wait(timeout=5)
            try:
                worker.complete(evidence, _verified_motion=proof)
                outcomes.append(('accepted', motion_hash, worker))
            except GateError:
                outcomes.append(('rejected', motion_hash, worker))

        threads = [threading.Thread(target=finish, args=(worker, value))
                   for worker, value in ((f.w, 'b' * 64), (other, 'c' * 64))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual([row[0] for row in outcomes], ['accepted', 'rejected'])
        winner = next(row for row in outcomes if row[0] == 'accepted')
        events = f.journal.replay(f.ctx.session_id)
        proofs = [event for event in events if event.kind == 'planning_verified']
        accepted = [event for event in events
                    if event.step_id == 'S06' and event.kind == 'result_accepted']
        self.assertEqual(len(proofs), 1)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(proofs[0].data['motion_hash'], winner[1])
        self.assertEqual(winner[2].accepted_motion_hash, winner[1])
        winner[2].start('S07', 'winner-capture')
        self.assertEqual(winner[2].states['S07'], State.RUNNING)

    def test_restart_invalidation_prevents_late_strict_s06_acceptance(self):
        f = self.fixture
        f.before_s06()
        replay_journal = Journal(f.path)
        self.addCleanup(replay_journal.close)
        restarted = Workflow(replay_journal, f.ctx, f.profiles, {'cal': 'v1'}, {},
                             10, lambda: f.now, strict_planning=True)
        self.assertEqual(restarted.states['S06'], State.BLOCKED)
        with self.assertRaises(GateError):
            f.accept_s06()
        with self.assertRaises(GateError):
            f.w.start('S07', 'late-capture')
        events = f.journal.replay(f.ctx.session_id)
        self.assertFalse(any(event.kind == 'planning_verified' for event in events))
        self.assertFalse(any(event.kind == 'dispatch' and event.step_id == 'S07'
                             for event in events))

    def test_exception_after_real_commit_poisoned_original_worker(self):
        f = self.fixture
        f.before_s06()
        original = f.journal.transaction

        @contextmanager
        def ambiguous_commit():
            with original():
                yield
            # Simulate failure after the database committed but before the
            # caller received a successful completion result.
            raise OSError('synthetic failure after durable commit')

        with patch.object(f.journal, 'transaction', ambiguous_commit):
            with self.assertRaises(OSError):
                f.accept_s06()
        self.assertTrue(f.w._journal_uncertain)
        self.assertIsNone(f.w.accepted_motion_hash)
        self.assertTrue(all(state == State.BLOCKED for state in f.w.states.values()))
        with self.assertRaises(GateError):
            f.w.start('S07', 'uncertain-capture')
        events = f.journal.replay(f.ctx.session_id)
        self.assertEqual(sum(event.kind == 'planning_verified' for event in events), 1)
        self.assertFalse(any(event.kind == 'dispatch' and event.step_id == 'S07'
                             for event in events))

    def test_strict_replayed_plan_preserves_photography_contract(self):
        f = self.fixture
        f.before_s06()
        f.accept_s06()
        replay_journal = Journal(f.path)
        self.addCleanup(replay_journal.close)
        restarted = Workflow(replay_journal, f.ctx, f.profiles, {'cal': 'v1'}, {},
                             10, lambda: f.now, strict_planning=True)
        self.assertEqual(restarted.accepted_motion_hash, f.motion_hash)
        restarted.start('S07', 'strict-photo')
        views = photography_views(f.plan, f.ctx, f.profiles, {'cal': 'v1'}, {}, f.now, 10)
        archive = Archive(f.tmp.name, f.ctx.session_id)
        self.addCleanup(archive.close)
        photos = PhotographySession(restarted, archive, views, f.plan)
        identity = ResultIdentity(f.ctx, 'strict-photo', views[0].view_id, f.now)
        photos.accept_motion(MotionResult(identity, True, (0.,), True, f.now,
                                           'synthetic-terminal-motion:' + f.motion_hash))
        png = b'\x89PNG\r\n\x1a\nsynthetic-final-core-audit'
        photos.accept_capture(CaptureResult(identity, True, True,
            (Original('png', png, digest(png), 'synthetic-original'),),
            'synthetic-transfer-receipt'))
        photos.complete_capture()
        self.assertEqual(restarted.states['S07'], State.SUCCEEDED)
        self.assertEqual(restarted.states['S08'], State.PENDING)
        self.assertEqual(restarted.accepted_motion_hash, f.motion_hash)
        self.assertEqual(archive._read(views[0].view_id + '.png'), png)


if __name__ == '__main__':
    unittest.main()
