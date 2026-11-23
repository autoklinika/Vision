"""Sequential fail-closed workflow. Callers supply independently verified evidence."""
import math
import time
from typing import Callable, Mapping
from .journal import Journal
from .models import Context, Evidence, GateError, State
from .profiles import PROFILE_KINDS, Profile, validate_profiles

STAGES = tuple(f'S{i:02}' for i in range(1, 12))
CHECKS = {
    'S01': {'readiness', 'device_state', 'calibrations'},
    'S02': {'operator_declaration', 'scenario_pinned'},
    'S03': {'rgb', 'depth', 'camera_info', 'transform', 'pose', 'orientation', 'pcb', 'obstacles', 'geometry'},
    'S04': {'identity_match', 'tolerances'},
    'S05': {'relative_targets', 'coverage_plan', 'capture_requirements'},
    'S06': {'ik', 'collision_check', 'planning_scene', 'plan'},
    'S07': {'goal_completed', 'actual_robot_state', 'capture_confirmed', 'transfer', 'file_integrity'},
    'S08': {'focus', 'exposure', 'field_of_view', 'coverage', 'originals_preserved'},
    'S09': {'park_authorized', 'motion_completed', 'actual_robot_state'},
    'S10': {'originals_immutable', 'derived_copies', 'manifest_hashes', 'profile_versions', 'observations', 'audit_persisted'},
    'S11': {'operator_summary', 'outcomes', 'exceptions', 'archive_reference'},
}
ALLOWED = {State.PENDING: {State.READY, State.BLOCKED}, State.READY: {State.RUNNING, State.BLOCKED},
           State.RUNNING: {State.SUCCEEDED, State.FAILED, State.CANCELLED, State.TIMED_OUT, State.BLOCKED}}


class Workflow:
    def __init__(self, journal: Journal, context: Context, profiles: Mapping[str, Profile], calibrations: Mapping[str, str], requirements: Mapping[str, frozenset[str]], max_age: float, clock: Callable[[], float] = time.time):
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('a positive finite freshness limit is required')
        self.journal, self.context, self.profiles = journal, context, dict(profiles)
        self.calibrations, self.requirements, self.max_age, self.clock = dict(calibrations), dict(requirements), max_age, clock
        self.states = {s: State.PENDING for s in STAGES}
        self.requests = {}
        self.snapshots = {}
        events = journal.replay(context.session_id)
        journal_context = None
        for event in events:
            if event.kind == 'transition':
                self.states[event.step_id] = State(event.data['to'])
            elif event.kind == 'dispatch':
                self.requests[event.step_id] = event.request_id
                self.snapshots[event.step_id] = Context(**event.data['context'])
                if journal_context is None:
                    journal_context = self.snapshots[event.step_id]
            elif event.kind == 'localization_accepted':
                journal_context = Context(**event.data['context'])
                self.states[event.step_id] = State.SUCCEEDED
        # An interrupted action is ambiguous. Never redispatch it or its dependents.
        for step in STAGES:
            if self.states[step] in (State.READY, State.RUNNING):
                self._transition(step, State.BLOCKED, 'restart requires external reconciliation')
                self._block_after(step, 'interrupted predecessor')
        if journal_context is not None:
            # An initial unlocalized context is a valid restart input after promotion.
            if context != journal_context and not (not context.scene_revision and context.session_id == journal_context.session_id and context.profile_revisions == journal_context.profile_revisions):
                self.invalidate('context differs from journal')
            self.context = journal_context

    def _record(self, step: str, kind: str, data: dict, request: str = '') -> None:
        self.journal.append(self.context.session_id, step, request or self.requests.get(step, ''), kind, data)

    def _deny(self, step: str, reason: str) -> None:
        self._record(step, 'denied', {'reason': reason})
        raise GateError(reason)

    def _transition(self, step: str, target: State, reason: str) -> None:
        old = self.states[step]
        if target not in ALLOWED.get(old, set()):
            self._deny(step, f'invalid transition {old} to {target}')
        self._record(step, 'transition', {'from': old.value, 'to': target.value, 'reason': reason})
        self.states[step] = target

    def _block_after(self, step: str, reason: str) -> None:
        for later in STAGES[STAGES.index(step) + 1:]:
            if self.states[later] in (State.PENDING, State.READY, State.RUNNING):
                self._transition(later, State.BLOCKED, reason)

    def invalidate(self, reason: str) -> None:
        self._record('', 'context_invalidated', {'reason': reason})
        for step in STAGES:
            if self.states[step] in (State.PENDING, State.READY, State.RUNNING):
                self._transition(step, State.BLOCKED, reason)

    def update_context(self, context: Context) -> None:
        if context != self.context:
            self.invalidate('context changed; new session and plan required')
            if context.session_id != self.context.session_id:
                raise GateError('session identity cannot change')
            self.context = context

    def _context_errors(self, c: Context, observation: bool = True, fresh: bool = True) -> list[str]:
        errors = validate_profiles(self.profiles, self.calibrations, self.requirements)
        if not c.session_id or set(c.profile_revisions) != PROFILE_KINDS:
            errors.append('incomplete context')
        if any(c.profile_revisions.get(k) != p.revision for k, p in self.profiles.items()):
            errors.append('profile revisions mismatch')
        now = self.clock()
        if observation:
            if not c.scene_revision or not c.frame_id or not isinstance(c.observation_timestamp, (int, float)) or not math.isfinite(c.observation_timestamp):
                errors.append('incomplete observation')
            elif not math.isfinite(now) or c.observation_timestamp > now or (fresh and now - c.observation_timestamp > self.max_age):
                errors.append('observation stale or in future')
        return errors

    def start(self, step: str, request_id: str) -> None:
        if step not in self.states:
            self._deny(step, 'unknown stage')
        if self.states[step] != State.PENDING:
            self._deny(step, 'stage is not pending')
        if not isinstance(request_id, str) or not request_id.strip() or request_id in self.requests.values():
            self._deny(step, 'missing or reused request ID')
        if any(self.states[s] != State.SUCCEEDED for s in STAGES[:STAGES.index(step)]):
            self._deny(step, 'predecessors not verified')
        errors = self._context_errors(self.context, observation=step not in ('S01', 'S02', 'S03'), fresh=step not in ('S10', 'S11'))
        if errors:
            self._record(step, 'denied', {'reason': '; '.join(errors)})
            self._transition(step, State.BLOCKED, '; '.join(errors))
            self._block_after(step, 'failed readiness')
            raise GateError('; '.join(errors))
        self._transition(step, State.READY, 'predecessors and readiness verified')
        self.requests[step] = request_id
        self.snapshots[step] = self.context
        self._record(step, 'dispatch', {'context': self.context.to_dict()}, request_id)
        self._transition(step, State.RUNNING, 'request dispatched')

    def ack(self, step: str, request_id: str) -> None:
        if self.states.get(step) != State.RUNNING or self.requests.get(step) != request_id:
            self._deny(step, 'uncorrelated acknowledgement')
        self._record(step, 'ack', {}, request_id)

    def complete(self, evidence: Evidence) -> None:
        step = evidence.step_id
        reasons = []
        if self.states.get(step) != State.RUNNING or self.requests.get(step) != evidence.request_id or not evidence.request_id:
            reasons.append('uncorrelated request or stage')
        if evidence.session_id != self.context.session_id or self.snapshots.get(step) != self.context:
            reasons.append('context mismatch')
        if step == 'S03':
            if evidence.context.session_id != self.context.session_id or evidence.context.profile_revisions != self.context.profile_revisions:
                reasons.append('context mismatch')
            reasons.extend(self._context_errors(evidence.context))
        else:
            if evidence.context != self.context:
                reasons.append('context mismatch')
            reasons.extend(self._context_errors(self.context, observation=step not in ('S01', 'S02'), fresh=step not in ('S10', 'S11')))
        now = self.clock()
        observation_time = evidence.context.observation_timestamp if step not in ('S01', 'S02') else None
        if (not isinstance(evidence.timestamp, (int, float)) or not math.isfinite(evidence.timestamp)
                or not math.isfinite(now) or not 0 <= now - evidence.timestamp <= self.max_age
                or (isinstance(observation_time, (int, float)) and evidence.timestamp < observation_time)):
            reasons.append('stale or invalid evidence timestamp')
        if evidence.quality is not True or evidence.terminal_success is not True or not evidence.reference or step not in CHECKS or not CHECKS.get(step, set()).issubset(evidence.checks):
            reasons.append('incomplete terminal evidence')
        if reasons:
            self._record(step, 'result_rejected', {'reason': '; '.join(reasons)}, evidence.request_id)
            if self.states.get(step) == State.RUNNING:
                self._transition(step, State.BLOCKED, 'result rejected')
                self._block_after(step, 'predecessor result rejected')
            raise GateError('; '.join(reasons))
        serialized = {'session_id': evidence.session_id, 'step_id': step, 'request_id': evidence.request_id,
                      'context': evidence.context.to_dict(), 'timestamp': evidence.timestamp,
                      'quality': evidence.quality, 'terminal_success': evidence.terminal_success,
                      'checks': sorted(evidence.checks), 'reference': evidence.reference}
        if step == 'S03':
            # One durable event commits both acceptance and context promotion.
            self._record(step, 'localization_accepted', {'evidence': serialized, 'context': evidence.context.to_dict(), 'transition': {'from': State.RUNNING.value, 'to': State.SUCCEEDED.value, 'reason': 'fresh localized scene verified'}}, evidence.request_id)
            self.context = evidence.context
            self.states[step] = State.SUCCEEDED
        else:
            self._record(step, 'result_accepted', {'evidence': serialized}, evidence.request_id)
            self._transition(step, State.SUCCEEDED, 'terminal evidence verified')

    def stop(self, step: str, state: State, reason: str) -> None:
        if state not in (State.FAILED, State.CANCELLED, State.TIMED_OUT) or not reason:
            self._deny(step, 'invalid stop')
        if step not in self.states:
            self._deny(step, 'unknown stage')
        self._transition(step, state, reason)
        self._block_after(step, reason)
