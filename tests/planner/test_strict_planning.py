"""Strict S05/S06 bindings and durable Core dispatch, without robot access."""
from contextlib import contextmanager
from dataclasses import replace
import os
import tempfile
import unittest
from unittest.mock import patch

from vision_core import Context, Evidence, GateError, Journal, State, Workflow
from vision_core.planning import PlanningProof, PreparationProof
from vision_core.profiles import ECUProfile, PROFILE_KINDS, Profile
from vision_core.repeatability import ObservedECU, create_plan
from vision_core.workflow import CHECKS, _fingerprint


class StrictPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'strict.sqlite')
        self.journal = Journal(self.path)
        self.addCleanup(lambda: self.journal.close())
        self.now = 1000.0
        self.ctx = Context('session', {k: 'r1' for k in PROFILE_KINDS}, 'scene', self.now, 'table')
        self.profiles = {k: Profile(k, k, '1', 'r1', True, {'basic', 'raw'}, {'basic'}, {'cal': 'v1'})
                         for k in PROFILE_KINDS}
        self.profiles['ecu'] = ECUProfile('ecu', 'synthetic', '1', 'r1', True,
            {'basic'}, {'basic'}, {'cal': 'v1'}, 'synthetic', 'test', (10, 20), 5,
            ((0, 0, 10, 20),), ((5, 10, 100),), (0.5,), ((0, 0, 0, 1),))
        self.w = self.make()
        observation = ObservedECU('table', (0, 0, 0), 0, self.now, 'scene', 'r1', 'synthetic', 'test', 'test-observation')
        self.plan = create_plan(self.ctx, self.profiles, {'cal': 'v1'}, {}, observation,
                                self.now, 10, min_coverage=1, require_raw=False)
        self.preparation_hash = 'a' * 64
        self.motion_hash = 'b' * 64

    def make(self, strict=True, context=None):
        return Workflow(self.journal, context or self.ctx, self.profiles, {'cal': 'v1'}, {}, 10,
                        lambda: self.now, strict_planning=strict)

    def evidence(self, step, **changes):
        evidence = Evidence('session', step, 'req-' + step, self.ctx, self.now, True, True,
                            frozenset(CHECKS[step]), 'synthetic-evidence',
                            self.plan.digest if step in ('S05', 'S06') else None)
        return replace(evidence, **changes)

    def before_s05(self):
        for step in ('S01', 'S02', 'S03', 'S04'):
            self.w.start(step, 'req-' + step)
            self.w.complete(self.evidence(step))
        self.w.start('S05', 'req-S05')

    def preparation(self):
        return PreparationProof(self.ctx, 'req-S05', self.plan.digest, self.preparation_hash,
                                self.now, 'inspection-preparation:sha256:' + self.preparation_hash)

    def accept_s05(self):
        proof = self.preparation()
        self.w.complete(self.evidence('S05', reference=proof.reference), _verified_plan=self.plan,
                        _verified_preparation=proof)

    def before_s06(self):
        self.before_s05()
        self.accept_s05()
        self.now += 1
        self.w.start('S06', 'req-S06')

    def motion(self):
        return PlanningProof(self.ctx, 'req-S06', self.plan.digest, self.preparation_hash,
                             self.motion_hash, self.now, 'motion-plan:sha256:' + self.motion_hash)

    def accept_s06(self):
        proof = self.motion()
        self.w.complete(self.evidence('S06', reference=proof.reference), _verified_motion=proof)

    def test_legacy_fingerprint_is_unchanged_and_strict_is_distinct(self):
        legacy = self.make(False)
        self.assertEqual(legacy._pin(), _fingerprint(self.profiles, {'cal': 'v1'}, {}, 10))
        self.assertNotEqual(self.w._pin(), legacy._pin())
        with self.assertRaises(ValueError): self.make(1)

    def test_generic_s05_cannot_claim_strict_preparation(self):
        self.before_s05()
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S05'), _verified_plan=self.plan)
        self.assertEqual(self.w.states['S06'], State.BLOCKED)
        self.assertNotIn('preparation_verified', [e.kind for e in self.journal.replay('session')])

    def test_preparation_requires_verified_core_plan(self):
        self.before_s05()
        proof = self.preparation()
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S05', reference=proof.reference), _verified_preparation=proof)
        self.assertEqual(self.w.states['S05'], State.BLOCKED)

    def test_generic_s06_cannot_claim_strict_motion(self):
        self.before_s06()
        with self.assertRaises(GateError): self.w.complete(self.evidence('S06'))
        self.assertEqual(self.w.states['S07'], State.BLOCKED)

    def test_extra_event_and_check_labels_cannot_replace_typed_motion(self):
        self.before_s06()
        self.journal.append('session', 'S06', 'req-S06', 'adapter_flags', {'planning_verified': True})
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S06', checks=frozenset(CHECKS['S06'] | {'planning_verified'})))
        self.assertEqual(self.w.states['S07'], State.BLOCKED)

    def test_wrong_preparation_request_is_rejected(self):
        self.before_s05()
        proof = replace(self.preparation(), request_id='other')
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S05', reference=proof.reference), _verified_plan=self.plan,
                            _verified_preparation=proof)
        self.assertEqual(self.w.states['S06'], State.BLOCKED)

    def test_motion_cannot_change_preparation_with_same_core_hash(self):
        self.before_s06()
        proof = replace(self.motion(), preparation_hash='c' * 64)
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S06', reference=proof.reference), _verified_motion=proof)
        self.assertEqual(self.w.states['S07'], State.BLOCKED)

    def test_wrong_context_is_rejected(self):
        self.before_s06()
        proof = replace(self.motion(), context=replace(self.ctx, scene_revision='different-scene'))
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S06', reference=proof.reference), _verified_motion=proof)

    def test_motion_timestamp_must_match_receipt_and_follow_dispatch(self):
        self.before_s06()
        proof = replace(self.motion(), timestamp=self.now - 0.5)
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S06', reference=proof.reference, timestamp=proof.timestamp),
                            _verified_motion=proof)
        self.assertEqual(self.w.states['S07'], State.BLOCKED)

    def test_future_motion_is_rejected(self):
        self.before_s06()
        proof = replace(self.motion(), timestamp=self.now + 1)
        with self.assertRaises(GateError):
            self.w.complete(self.evidence('S06', reference=proof.reference, timestamp=proof.timestamp),
                            _verified_motion=proof)

    def test_valid_proofs_are_atomic_and_allow_s07_dispatch(self):
        self.before_s06()
        self.accept_s06()
        events = self.journal.replay('session')
        for step, kind in (('S05', 'preparation_verified'), ('S06', 'planning_verified')):
            verified = next(e for e in events if e.kind == kind)
            accepted = next(e for e in events if e.step_id == step and e.kind == 'result_accepted')
            self.assertLess(verified.sequence, accepted.sequence)
            self.assertEqual(verified.data['configuration_pin'], self.w.config_pin)
        self.assertEqual(self.w.accepted_preparation_hash, self.preparation_hash)
        self.assertEqual(self.w.accepted_motion_hash, self.motion_hash)
        self.w.start('S07', 'req-S07')
        self.assertEqual(self.w.states['S07'], State.RUNNING)

    def test_completed_replay_restores_both_hashes(self):
        self.before_s06()
        self.accept_s06()
        replayed = self.make()
        self.assertEqual(replayed.states['S06'], State.SUCCEEDED)
        self.assertEqual(replayed.accepted_preparation_hash, self.preparation_hash)
        self.assertEqual(replayed.accepted_motion_hash, self.motion_hash)
        replayed.start('S07', 'req-S07')

    def test_replay_downgrade_is_blocked(self):
        self.before_s06()
        self.accept_s06()
        replayed = self.make(False)
        self.assertTrue(all(state == State.BLOCKED for state in replayed.states.values()))
        with self.assertRaises(GateError): replayed.start('S07', 'req-S07')

    def test_live_downgrade_is_blocked(self):
        self.before_s06()
        self.accept_s06()
        self.w.strict_planning = False
        with self.assertRaises(GateError): self.w.start('S07', 'req-S07')

    def test_unresolved_s06_replay_does_not_resume(self):
        self.before_s06()
        replayed = self.make()
        self.assertEqual(replayed.states['S06'], State.BLOCKED)
        self.assertIsNone(replayed.accepted_motion_hash)

    def test_duplicate_planning_proof_blocks_s07(self):
        self.before_s06()
        self.accept_s06()
        verified = next(e for e in self.journal.replay('session') if e.kind == 'planning_verified')
        self.journal.append('session', 'S06', verified.request_id, verified.kind, verified.data)
        with self.assertRaises(GateError): self.w.start('S07', 'req-S07')
        self.assertNotIn('S07', [e.step_id for e in self.journal.replay('session') if e.kind == 'dispatch'])

    def test_in_memory_hash_does_not_replace_proof(self):
        self.before_s06()
        self.accept_s06()
        self.w.accepted_motion_hash = 'c' * 64
        with self.assertRaises(GateError): self.w.start('S07', 'req-S07')

    def test_failed_result_write_rolls_back_verified_proof_and_poisons_worker(self):
        self.before_s06()
        original = self.journal.append
        def fail(session, step, request, kind, data):
            if step == 'S06' and kind == 'result_accepted':
                raise OSError('simulated result write failure after proof')
            return original(session, step, request, kind, data)
        with patch.object(self.journal, 'append', side_effect=fail):
            with self.assertRaises(OSError): self.accept_s06()
        self.assertNotIn('planning_verified', [e.kind for e in self.journal.replay('session')])
        self.assertIsNone(self.w.accepted_motion_hash)
        with self.assertRaises(GateError): self.accept_s06()
        with self.assertRaises(GateError): self.w.start('S07', 'req-S07')

    def test_failed_commit_never_exposes_usable_motion_success(self):
        self.before_s06()
        original = self.journal.transaction
        @contextmanager
        def fail_commit():
            with original():
                yield
                raise OSError('simulated ambiguous commit')
        with patch.object(self.journal, 'transaction', fail_commit):
            with self.assertRaises(OSError): self.accept_s06()
        self.assertTrue(all(state == State.BLOCKED for state in self.w.states.values()))
        self.assertIsNone(self.w.accepted_motion_hash)
        self.assertNotIn('planning_verified', [e.kind for e in self.journal.replay('session')])

    def test_failed_preparation_write_cannot_leave_partial_s05(self):
        self.before_s05()
        original = self.journal.append
        def fail(session, step, request, kind, data):
            if step == 'S05' and kind == 'result_accepted':
                raise OSError('simulated preparation result write failure')
            return original(session, step, request, kind, data)
        with patch.object(self.journal, 'append', side_effect=fail):
            with self.assertRaises(OSError): self.accept_s05()
        self.assertNotIn('preparation_verified', [e.kind for e in self.journal.replay('session')])
        self.assertIsNone(self.w.accepted_preparation_hash)

    def test_proof_datatypes_and_references_are_explicit(self):
        preparation = self.preparation()
        for changes in ({'timestamp': True}, {'timestamp': 10**1000}, {'preparation_hash': 'A' * 64},
                        {'request_id': ''}, {'reference': 'other'}, {'inspection_plan_hash': 'bad'}):
            with self.subTest(changes=changes), self.assertRaises(GateError):
                replace(preparation, **changes)
        with self.assertRaises(GateError): replace(self.motion(), motion_hash='x' * 64)
        with self.assertRaises(GateError): replace(self.motion(), reference='other')


if __name__ == '__main__':
    unittest.main()
