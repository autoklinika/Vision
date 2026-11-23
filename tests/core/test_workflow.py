import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace

from vision_core import Context, Evidence, GateError, Journal, Profile, ECUProfile, State, Workflow
from vision_core.ports import InertMock, Request
from vision_core.profiles import PROFILE_KINDS
from vision_core.workflow import CHECKS, STAGES

NOW = 1000.0


def profiles():
    result = {k: Profile(k, k, '1', 'r1', True, frozenset({'basic', 'raw', 'af', 'depth'}), frozenset({'basic'}), {'cal': 'v1'}) for k in PROFILE_KINDS}
    result['ecu'] = ECUProfile('ecu', 'synthetic', '1', 'r1', True, {'basic'}, {'basic'}, {'cal': 'v1'}, 'example', 'a', (10, 20), 5, ((0, 0, 10, 20),), ((1, 2, 3),), (0.5,))
    return result


def context():
    return Context('session', {k: 'r1' for k in PROFILE_KINDS}, 'scene1', NOW, 'synthetic_frame')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'events.sqlite')
        self.journal = Journal(self.path)
        self.profiles = profiles()
        self.ctx = context()
        self.engine = self.make()

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def make(self, ctx=None, ps=None, requirements=None, calibrations=None):
        return Workflow(self.journal, ctx or self.ctx, ps or self.profiles, {'cal': 'v1'} if calibrations is None else calibrations, requirements or {}, 10, lambda: NOW)

    def evidence(self, stage, **kwargs):
        e = Evidence('session', stage, 'req-' + stage, self.ctx, NOW, True, True, frozenset(CHECKS[stage]), 'synthetic-reference')
        return replace(e, **kwargs)

    def advance(self, through):
        for s in STAGES[:through]:
            self.engine.start(s, 'req-' + s)
            self.engine.complete(self.evidence(s))

    def test_full_session_and_audit(self):
        self.advance(11)
        self.assertTrue(all(s == State.SUCCEEDED for s in self.engine.states.values()))
        events = self.journal.replay('session')
        self.assertEqual(sum(e.kind in ('result_accepted', 'localization_accepted') for e in events), 11)
        self.assertEqual(sum(e.kind == 'dispatch' for e in events), 11)
        with self.assertRaises(sqlite3.IntegrityError):
            self.journal.db.execute('DELETE FROM events')
        self.journal.db.rollback()

    def test_dependencies_ack_and_invalid_transition(self):
        with self.assertRaises(GateError): self.engine.start('S02', 'early')
        self.engine.start('S01', 'req-S01')
        self.engine.ack('S01', 'req-S01')
        with self.assertRaises(GateError): self.engine.start('S02', 'early')
        with self.assertRaises(GateError): self.engine.start('S01', 'again')
        self.assertEqual(self.engine.states['S01'], State.RUNNING)
        self.assertIn('denied', [e.kind for e in self.journal.replay('session')])

    def test_bad_evidence_blocks(self):
        variants = [dict(request_id='wrong'), dict(session_id='other'), dict(timestamp=980), dict(quality=False), dict(terminal_success=False), dict(checks=frozenset()), dict(reference=''), dict(context=replace(self.ctx, scene_revision='other')), dict(context=replace(self.ctx, frame_id=''))]
        for i, changes in enumerate(variants):
            with self.subTest(changes=changes):
                ctx = replace(self.ctx, session_id=f's{i}')
                engine = self.make(ctx)
                engine.start('S01', 'req-S01')
                e = replace(self.evidence('S01'), session_id=ctx.session_id, context=ctx, **{k: v for k, v in changes.items() if k not in ('session_id', 'context')})
                if 'session_id' in changes: e = replace(e, session_id=changes['session_id'])
                if 'context' in changes: e = replace(e, context=replace(changes['context'], session_id=ctx.session_id))
                with self.assertRaises(GateError): engine.complete(e)
                self.assertEqual(engine.states['S02'], State.BLOCKED)

    def test_failure_cancel_timeout_block(self):
        for i, state in enumerate((State.FAILED, State.CANCELLED, State.TIMED_OUT)):
            engine = self.make(replace(self.ctx, session_id=f'stop{i}'))
            engine.start('S01', 'r')
            engine.stop('S01', state, 'synthetic fault')
            self.assertEqual(engine.states['S09'], State.BLOCKED)
            with self.assertRaises(GateError): engine.start('S09', 'park')

    def test_capabilities_and_calibration(self):
        for i, (ps, cal, req) in enumerate([
            (self.profiles, {}, {}),
            ({**self.profiles, 'sensor': replace(self.profiles['sensor'], approved=False)}, {'cal': 'v1'}, {}),
            ({**self.profiles, 'capture': replace(self.profiles['capture'], capabilities=frozenset({'basic'}))}, {'cal': 'v1'}, {'capture': frozenset({'raw'})}),
        ]):
            engine = self.make(replace(self.ctx, session_id=f'cap{i}'), ps, req, cal)
            with self.assertRaises(GateError): engine.start('S01', 'r')
            self.assertEqual(engine.states['S02'], State.BLOCKED)

    def test_synthetic_profiles_share_workflow(self):
        for i in range(2):
            ps = dict(self.profiles)
            ps['sensor'] = replace(ps['sensor'], identifier=f'sensor{i}')
            ps['capture'] = replace(ps['capture'], identifier=f'capture{i}', capabilities=frozenset({'basic', 'raw'} if i else {'basic'}))
            engine = self.make(replace(self.ctx, session_id=f'variant{i}'), ps, {'sensor': frozenset({'depth'}), 'capture': frozenset({'basic'})})
            engine.start('S01', 'r')
            self.assertEqual(engine.states['S01'], State.RUNNING)

    def test_context_changes_invalidate_plan(self):
        changes = [dict(scene_revision='scene2'), dict(observation_timestamp=NOW - 1), dict(frame_id='other')]
        for kind in ('tool', 'robot', 'sensor', 'capture'):
            changes.append(dict(profile_revisions={**self.ctx.profile_revisions, kind: 'r2'}))
        for i, change in enumerate(changes):
            ctx = replace(self.ctx, session_id=f'change{i}')
            engine = self.make(ctx)
            for stage in STAGES[:6]:
                engine.start(stage, 'req-' + stage)
                engine.complete(replace(self.evidence(stage), session_id=ctx.session_id, context=ctx))
            engine.update_context(replace(ctx, **change))
            with self.assertRaises(GateError): engine.start('S07', 'motion')
            self.assertEqual(engine.states['S07'], State.BLOCKED)

    def test_restart_blocks_running_and_no_redispatch(self):
        self.engine.start('S01', 'req-S01')
        before = len([e for e in self.journal.replay('session') if e.kind == 'dispatch'])
        self.journal.close()
        self.journal = Journal(self.path)
        replayed = self.make()
        self.assertEqual(replayed.states['S01'], State.BLOCKED)
        self.assertEqual(replayed.states['S09'], State.BLOCKED)
        self.assertEqual(before, len([e for e in self.journal.replay('session') if e.kind == 'dispatch']))
        with self.assertRaises(GateError): replayed.start('S01', 'new')

    def test_unlocalized_promotion_and_restart(self):
        initial = replace(self.ctx, scene_revision='', frame_id='', observation_timestamp=None)
        engine = self.make(initial)
        for stage in ('S01', 'S02'):
            engine.start(stage, 'req-' + stage)
            engine.complete(replace(self.evidence(stage), context=initial))
        engine.start('S03', 'req-S03')
        engine.complete(self.evidence('S03'))
        self.assertEqual(engine.context, self.ctx)
        self.journal.close()
        self.journal = Journal(self.path)
        engine = self.make(initial)
        self.assertEqual(engine.context, self.ctx)
        self.assertEqual(engine.states['S03'], State.SUCCEEDED)
        engine.start('S04', 'req-S04')
        engine.complete(self.evidence('S04'))

    def test_localization_requires_fresh_observation(self):
        for i, changes in enumerate(({'scene_revision': ''}, {'frame_id': ''}, {'observation_timestamp': None}, {'observation_timestamp': NOW - 11})):
            initial = replace(self.ctx, session_id=f'loc{i}', scene_revision='', frame_id='', observation_timestamp=None)
            engine = self.make(initial)
            for stage in ('S01', 'S02'):
                engine.start(stage, 'req-' + stage)
                engine.complete(replace(self.evidence(stage), session_id=initial.session_id, context=initial))
            engine.start('S03', 'req-S03')
            observed = replace(self.ctx, session_id=initial.session_id, **changes)
            with self.assertRaises(GateError):
                engine.complete(replace(self.evidence('S03'), session_id=initial.session_id, context=observed))
            self.assertEqual(engine.states['S04'], State.BLOCKED)

    def test_context_defensive_copy(self):
        revisions = dict(self.ctx.profile_revisions)
        ctx = replace(self.ctx, profile_revisions=revisions)
        engine = self.make(ctx)
        engine.start('S01', 'req-S01')
        revisions['ecu'] = 'changed'
        self.assertEqual(engine.context.profile_revisions['ecu'], 'r1')
        self.assertEqual(engine.snapshots['S01'].profile_revisions['ecu'], 'r1')
        engine.complete(replace(self.evidence('S01'), context=ctx))
        accepted = [e for e in self.journal.replay('session') if e.kind == 'result_accepted'][-1]
        self.assertEqual(accepted.data['evidence']['context']['profile_revisions']['ecu'], 'r1')
        with self.assertRaises(TypeError): ctx.profile_revisions['ecu'] = 'changed'

    def test_ecu_view_contract(self):
        ecu = self.profiles['ecu']
        for invalid in (replace(ecu, nominal_dimensions=()), replace(ecu, max_height=0), replace(ecu, view_targets=()), replace(ecu, pcb_regions=()), replace(ecu, tolerances=())):
            engine = self.make(replace(self.ctx, session_id='invalid' + str(id(invalid))), {**self.profiles, 'ecu': invalid})
            with self.assertRaises(GateError): engine.start('S01', 'r')
        self.assertEqual(ecu.view_targets, ((1, 2, 3),))
        self.assertNotIn('robot', ecu.__dataclass_fields__)

    def test_archive_accepts_old_observation_with_fresh_evidence(self):
        self.advance(9)
        self.engine.clock = lambda: NOW + 100
        for stage in ('S10', 'S11'):
            self.engine.start(stage, 'req-' + stage)
            self.engine.complete(replace(self.evidence(stage), timestamp=NOW + 100))
        self.assertEqual(self.engine.states['S11'], State.SUCCEEDED)

    def test_mock_is_inert(self):
        mock = InertMock()
        request = Request('S03', 'id', self.ctx)
        self.assertIsNone(mock.observe(request))
        self.assertEqual(mock.requests, [request])


if __name__ == '__main__': unittest.main()
