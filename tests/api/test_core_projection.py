"""Real Core/SQLite with synthetic evidence; no station or device involvement."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
import tempfile
import threading
import unittest
from unittest.mock import patch

from vision_core import Context, Evidence, Journal, Profile, ECUProfile, State, Workflow
from vision_core.extensions import ModuleRegistry, ModuleSpec, ScenarioSpec, StageSpec
from vision_core.profiles import PROFILE_KINDS
from vision_core.read_model import MAX_SEQUENCE, ReadUnavailable
from vision_core.workflow import CHECKS, STAGES


def make_engine(journal, session='synthetic-api02', *, extension=False):
    profiles = {k: Profile(k, k, '1', 'r1', True,
        frozenset({'basic', 'raw', 'af', 'depth'}), frozenset({'basic'}),
        {'cal': 'v1'}) for k in PROFILE_KINDS}
    profiles['ecu'] = ECUProfile('ecu', 'synthetic', '1', 'r1', True,
        {'basic'}, {'basic'}, {'cal': 'v1'}, 'example', 'a', (10, 20), 5,
        ((0, 0, 10, 20),), ((1, 2, 3),), (0.5,))
    kwargs = {}
    if extension:
        registry = ModuleRegistry()
        registry.register(ModuleSpec('test', '1', 'test', {'inspect'}, True, ('T1',)))
        profiles['test'] = Profile('test', 'test', '1', 'r1', True,
            {'inspect'}, frozenset(), {'cal': 'v1'})
        stages = []
        for i, stage in enumerate(STAGES):
            dependencies = [] if not i else [STAGES[i - 1]]
            if stage == 'S04':
                stages.append(StageSpec('T1', ('S03',), {'verified'}, 'test'))
                dependencies.append('T1')
            stages.append(StageSpec(stage, tuple(dependencies), CHECKS[stage]))
        kwargs = {'scenario': ScenarioSpec('synthetic', '1', tuple(stages), ('test',)),
                  'registry': registry}
    context = Context(session, {k: 'r1' for k in profiles}, 'scene', 1000.0, 'frame')
    return Workflow(journal, context, profiles, {'cal': 'v1'}, {}, 10,
                    lambda: 1000.0, **kwargs)


def complete(engine, stage):
    engine.start(stage, 'synthetic-' + stage)
    engine.complete(Evidence(engine.context.session_id, stage, 'synthetic-' + stage,
        engine.context, 1000.0, True, True, frozenset(CHECKS[stage]),
        'private-synthetic-proof'))


class CoreProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Journal(self.tmp.name + '/events.sqlite')
        self.engine = make_engine(self.journal)

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def test_pending_snapshot_is_immutable_and_clock_is_read_time(self):
        with patch('vision_core.read_model.time.time', return_value=2000.0):
            snapshot = self.engine.read_snapshot()
        self.assertEqual(snapshot.captured_at, 2000.0)
        self.assertEqual(snapshot.high_water, 0)
        self.assertFalse(snapshot.invalidated)
        self.assertEqual(tuple(s.stage_id for s in snapshot.stages), STAGES)
        self.assertTrue(all(s.state == State.PENDING and not s.historical_success
                            for s in snapshot.stages))
        with self.assertRaises(FrozenInstanceError):
            snapshot.high_water = 123
        with self.assertRaises(FrozenInstanceError):
            snapshot.stages[0].state = State.SUCCEEDED

    def test_ack_is_recorded_without_success_or_transition(self):
        self.engine.start('S01', 'synthetic-S01')
        initial = self.engine.read_snapshot().stages[0]
        self.engine.ack('S01', 'synthetic-S01')
        snapshot = self.engine.read_snapshot()
        stage = snapshot.stages[0]
        self.assertEqual(stage.state, State.RUNNING)
        self.assertFalse(stage.historical_success)
        self.assertEqual(stage.last_transition_sequence, initial.last_transition_sequence)
        self.assertEqual(stage.last_ack_sequence, snapshot.high_water)
        event = self.engine.read_events().events[-1]
        self.assertEqual(event.kind, 'ack')
        self.assertIsNone(event.state)

    def test_full_success_then_invalidation_retains_historical_success(self):
        for stage in STAGES:
            complete(self.engine, stage)
        before = self.engine.read_snapshot()
        self.assertTrue(all(s.state == State.SUCCEEDED for s in before.stages))
        self.engine.invalidate('private reason and path /do/not/expose')
        after = self.engine.read_snapshot()
        self.assertTrue(after.invalidated)
        self.assertTrue(all(s.state == State.BLOCKED and s.historical_success
                            for s in after.stages))
        self.assertEqual([s.last_transition_sequence for s in after.stages],
                         [s.last_transition_sequence for s in before.stages])

    def test_failure_and_block_are_authoritative_states(self):
        self.engine.start('S01', 'synthetic-S01')
        self.engine.stop('S01', State.FAILED, 'private failure')
        snapshot = self.engine.read_snapshot()
        self.assertEqual(snapshot.stages[0].state, State.FAILED)
        self.assertTrue(all(s.state == State.BLOCKED for s in snapshot.stages[1:]))
        self.assertTrue(all(not s.historical_success for s in snapshot.stages))

    def test_real_scenario_additional_stage_is_reported_in_order(self):
        engine = make_engine(self.journal, 'synthetic-extension', extension=True)
        snapshot = engine.read_snapshot()
        self.assertEqual(tuple(s.stage_id for s in snapshot.stages),
                         (*STAGES[:3], 'T1', *STAGES[3:]))
        for stage in STAGES[:3]:
            complete(engine, stage)
        engine.start('T1', 'synthetic-T1')
        self.assertEqual(engine.read_snapshot().stages[3].state, State.RUNNING)

    def test_reads_do_not_write_replay_construct_or_dispatch(self):
        complete(self.engine, 'S01')
        before = self.journal.db.total_changes
        history = self.journal.replay(self.engine.context.session_id)
        statements = []
        self.journal.db.set_trace_callback(statements.append)
        with (patch.object(Workflow, '__init__', side_effect=AssertionError('constructor')),
                patch.object(Journal, 'replay', side_effect=AssertionError('replay')),
                patch.object(Workflow, 'start', side_effect=AssertionError('dispatch'))):
            for _ in range(3):
                self.engine.read_snapshot()
                self.engine.read_events(limit=2)
        self.journal.db.set_trace_callback(None)
        self.assertEqual(before, self.journal.db.total_changes)
        self.assertEqual(history, self.journal.replay(self.engine.context.session_id))
        self.assertTrue(all(s.lstrip().upper().startswith(('SELECT', 'BEGIN', 'ROLLBACK'))
                            for s in statements))

    def test_page_is_bounded_pinned_and_payloads_are_redacted(self):
        self.engine.start('S01', 'secret-request-id')
        for _ in range(120):
            self.engine.ack('S01', 'secret-request-id')
        self.journal.append(self.engine.context.session_id, '/private/stage',
            'secret-request-id', 'secret-event-kind',
            {'path': '/private/path', 'token': 'private-token'})
        statements = []
        self.journal.db.set_trace_callback(statements.append)
        first = self.engine.read_events(limit=3)
        self.journal.db.set_trace_callback(None)
        self.assertEqual(len(first.events), 3)
        self.assertEqual(first.next_after_sequence, first.events[-1].sequence)
        self.assertTrue(any('ORDER BY sequence LIMIT 4' in s for s in statements))
        self.engine.ack('S01', 'secret-request-id')
        events = list(first.events)
        cursor = first.next_after_sequence
        while cursor is not None:
            page = self.engine.read_events(after_sequence=cursor, limit=50,
                                           through_sequence=first.high_water)
            self.assertEqual(page.high_water, first.high_water)
            self.assertLessEqual(len(page.events), 50)
            events.extend(page.events)
            cursor = page.next_after_sequence
        self.assertEqual(events[-1].sequence, first.high_water)
        self.assertEqual(events[-1].kind, 'OTHER')
        self.assertIsNone(events[-1].stage_id)
        self.assertIsNone(events[-1].state)
        self.assertEqual(len({e.sequence for e in events}), len(events))
        serialized = repr(events)
        for secret in ('secret-request-id', '/private/', 'private-token', 'secret-event-kind'):
            self.assertNotIn(secret, serialized)

    def test_interleaved_sessions_do_not_leak_events(self):
        other = make_engine(self.journal, 'other-synthetic-session')
        self.engine.start('S01', 'synthetic-S01')
        other.start('S01', 'other-S01')
        self.engine.ack('S01', 'synthetic-S01')
        own = self.engine.read_events()
        others = other.read_events()
        self.assertFalse({e.sequence for e in own.events} & {e.sequence for e in others.events})

    def test_invalid_cursors_and_limits_are_rejected(self):
        for kwargs in ({'after_sequence': True}, {'after_sequence': -1},
                {'after_sequence': MAX_SEQUENCE + 1}, {'limit': True}, {'limit': 0},
                {'limit': 51}, {'through_sequence': True}, {'through_sequence': -1},
                {'after_sequence': 1}, {'through_sequence': 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.engine.read_events(**kwargs)
        self.assertEqual(self.engine.read_events(through_sequence=0).events, ())
        self.assertEqual(self.journal.db.total_changes, 0)

    def test_inconsistent_memory_is_not_repaired_by_read(self):
        self.engine.states['S01'] = State.SUCCEEDED
        with self.assertRaises(ReadUnavailable) as caught:
            self.engine.read_snapshot()
        self.assertEqual(caught.exception.reason, 'INCONSISTENT_STATE')
        self.assertEqual(self.engine.states['S01'], State.SUCCEEDED)
        self.assertEqual(self.journal.db.total_changes, 0)

    def test_other_engine_write_causes_unavailability_not_replay(self):
        stale = make_engine(self.journal)
        self.engine.start('S01', 'synthetic-S01')
        before = self.journal.db.total_changes
        with self.assertRaises(ReadUnavailable) as caught:
            stale.read_snapshot()
        self.assertEqual(caught.exception.reason, 'INCONSISTENT_STATE')
        self.assertEqual(self.journal.db.total_changes, before)
        self.assertEqual(stale.states['S01'], State.PENDING)

    def test_persistence_uncertainty_stays_unavailable_without_read_writes(self):
        original = self.journal.append
        def uncertain(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('private persistence detail')
        with patch.object(self.journal, 'append', side_effect=uncertain):
            with self.assertRaises(OSError):
                self.engine._record('S01', 'capture_verified', {'private': True})
        before = self.journal.db.total_changes
        for operation in (self.engine.read_snapshot, self.engine.read_events):
            with self.assertRaises(ReadUnavailable) as caught:
                operation()
            self.assertEqual(caught.exception.reason, 'JOURNAL_UNCERTAIN')
        self.assertEqual(self.journal.db.total_changes, before)

    def test_read_cannot_observe_commit_before_memory_update(self):
        committed = threading.Event()
        release = threading.Event()
        errors = []
        original = self.journal.transaction
        @contextmanager
        def pause_after_commit():
            with original():
                yield
            committed.set()
            if not release.wait(3):
                raise TimeoutError('test barrier')
        def start():
            try:
                self.engine.start('S01', 'synthetic-S01')
            except BaseException as exc:
                errors.append(exc)
        with patch.object(self.journal, 'transaction', pause_after_commit):
            worker = threading.Thread(target=start)
            worker.start()
            try:
                self.assertTrue(committed.wait(3))
                with self.assertRaises(ReadUnavailable) as caught:
                    self.engine.read_snapshot()
                self.assertEqual(caught.exception.reason, 'CORE_BUSY')
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertEqual(self.engine.read_snapshot().stages[0].state, State.RUNNING)

    def test_reentrant_read_inside_owner_operation_is_unavailable(self):
        with self.engine.owner_operation():
            with self.assertRaises(ReadUnavailable) as caught:
                self.engine.read_snapshot()
        self.assertEqual(caught.exception.reason, 'CORE_BUSY')
        self.assertEqual(self.engine.read_snapshot().high_water, 0)

    def test_uncommitted_journal_view_is_unavailable(self):
        with self.journal.transaction():
            with self.assertRaises(ReadUnavailable) as caught:
                self.engine.read_snapshot()
            self.assertEqual(caught.exception.reason, 'JOURNAL_UNAVAILABLE')

    def test_closed_journal_never_exposes_internal_exception(self):
        self.journal.close()
        with self.assertRaises(ReadUnavailable) as caught:
            self.engine.read_snapshot()
        self.assertEqual(str(caught.exception), 'JOURNAL_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
