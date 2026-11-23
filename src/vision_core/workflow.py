"""Sequential fail-closed workflow. Callers supply independently verified evidence."""
import math
import hashlib
import json
import sqlite3
from dataclasses import fields, is_dataclass
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


def _canonical(value):
    if is_dataclass(value):
        return {f.name: _canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    return value


def _fingerprint(profiles, calibrations, requirements, max_age):
    data = _canonical({'profiles': profiles, 'calibrations': calibrations, 'requirements': requirements, 'max_age': max_age})
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Workflow:
    def __init__(self, journal: Journal, context: Context, profiles: Mapping[str, Profile], calibrations: Mapping[str, str], requirements: Mapping[str, frozenset[str]], max_age: float, clock: Callable[[], float] = time.time):
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('a positive finite freshness limit is required')
        self.journal, self.context, self.profiles = journal, context, dict(profiles)
        self.calibrations, self.requirements, self.max_age, self.clock = dict(calibrations), dict(requirements), max_age, clock
        self.states = {s: State.PENDING for s in STAGES}
        self.requests = {}
        self.snapshots = {}
        self.dispatch_times = {}
        self.accepted_plan_hash = None
        self.config_pin = None
        self._journal_uncertain = False
        invalidation = None
        events = journal.replay(context.session_id)
        journal_context = None
        for event in events:
            if event.kind == 'config_pinned':
                self.config_pin = event.data['sha256']
            elif event.kind == 'result_accepted' and event.step_id == 'S05':
                self.accepted_plan_hash = event.data['evidence'].get('plan_hash')
            elif event.kind == 'context_invalidated':
                invalidation = event.data.get('reason', 'context invalidated')
            elif event.kind == 'transition':
                self.states[event.step_id] = State(event.data['to'])
            elif event.kind == 'dispatch':
                self.requests[event.step_id] = event.request_id
                self.dispatch_times[event.step_id] = event.data.get('dispatch_time')
                self.snapshots[event.step_id] = Context(**event.data['context'])
                if journal_context is None:
                    journal_context = self.snapshots[event.step_id]
            elif event.kind == 'localization_accepted':
                journal_context = Context(**event.data['context'])
                self.states[event.step_id] = State.SUCCEEDED
        if invalidation is not None:
            for step in STAGES:
                if self.states[step] in (State.PENDING, State.READY, State.RUNNING):
                    self.states[step] = State.BLOCKED
        if invalidation is None and events and self.requests and self.config_pin is None:
            self.invalidate('journal has no pinned configuration')
        elif invalidation is None and self.config_pin is not None and self.config_pin != _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age):
            self.invalidate('pinned configuration changed')
        # An interrupted action is ambiguous. Never redispatch it or its dependents.
        if any(self.states[step] in (State.READY, State.RUNNING) for step in STAGES):
            self.invalidate('restart requires external reconciliation')
        if journal_context is not None:
            # An initial unlocalized context is a valid restart input after promotion.
            if context != journal_context and not (not context.scene_revision and context.session_id == journal_context.session_id and context.profile_revisions == journal_context.profile_revisions):
                self.invalidate('context differs from journal')
            self.context = journal_context

    def _poison(self) -> None:
        # A failed journal write/commit may have reached persistent storage.
        # This worker must never accept another result or dispatch another task.
        self._journal_uncertain = True
        for stage in STAGES:
            if self.states[stage] in (State.PENDING, State.READY, State.RUNNING):
                self.states[stage] = State.BLOCKED

    def _require_usable(self) -> None:
        if self._journal_uncertain:
            raise GateError('journal persistence uncertain; external reconciliation required')

    def _record(self, step: str, kind: str, data: dict, request: str = '') -> None:
        try:
            self.journal.append(self.context.session_id, step, request or self.requests.get(step, ''), kind, data)
        except BaseException:
            self._poison()
            raise

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

    def _durable(self):
        history = self.journal.replay(self.context.session_id)
        states = {s: State.PENDING for s in STAGES}
        for event in history:
            if event.kind == 'transition':
                states[event.step_id] = State(event.data['to'])
            elif event.kind == 'localization_accepted':
                states[event.step_id] = State.SUCCEEDED
        return history, states

    def _verify_running(self, step, history, states):
        dispatches = [e for e in history if e.kind == 'dispatch' and e.step_id == step]
        pins = [e.data['sha256'] for e in history if e.kind == 'config_pinned']
        contexts = [e.data['context'] for e in history if e.kind == 'localization_accepted']
        if (states.get(step) != State.RUNNING or len(dispatches) != 1
                or dispatches[0].request_id != self.requests.get(step)
                or (self.snapshots.get(step) is None or dispatches[0].data.get('context') != self.snapshots[step].to_dict())
                or dispatches[0].data.get('dispatch_time') != self.dispatch_times.get(step)
                or any(e.kind == 'context_invalidated' for e in history)
                or len(set(pins)) != 1 or not pins
                or pins[0] != _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age)
                or (contexts and contexts[-1] != self.context.to_dict())):
            raise GateError('durable state, request, context or configuration mismatch')

    def invalidate(self, reason: str) -> None:
        self._require_usable()
        error = None
        with self.journal.transaction():
            history, states = self._durable()
            if any(e.kind == 'context_invalidated' for e in history) or self.states != states:
                self.states.update(states)
                error = GateError('stale or duplicate invalidation')
                self._record('', 'denied', {'reason': str(error)})
            else:
                self._record('', 'context_invalidated', {'reason': reason})
                for step in STAGES:
                    if self.states[step] in (State.PENDING, State.READY, State.RUNNING):
                        self._transition(step, State.BLOCKED, reason)
        if error:
            raise error

    def update_context(self, context: Context) -> None:
        self._require_usable()
        if context != self.context:
            self.invalidate('context changed; new session and plan required')
            if context.session_id != self.context.session_id:
                raise GateError('session identity cannot change')
            self.context = context

    def _context_errors(self, c: Context, observation: bool = True, fresh: bool = True) -> list[str]:
        errors = validate_profiles(self.profiles, self.calibrations, self.requirements)
        if self.config_pin is not None and self.config_pin != _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age):
            errors.append('pinned configuration changed')
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
        self._require_usable()
        if step not in self.states:
            self._deny(step, 'unknown stage')
        if self.states[step] != State.PENDING:
            self._deny(step, 'stage is not pending')
        if not isinstance(request_id, str) or not request_id.strip() or request_id in self.requests.values():
            self._deny(step, 'missing or reused request ID')
        if any(self.states[s] != State.SUCCEEDED for s in STAGES[:STAGES.index(step)]):
            self._deny(step, 'predecessors not verified')
        if step in ('S06', 'S07', 'S08') and self._repeatable() and not self.accepted_plan_hash:
            self._deny(step, 'accepted inspection plan missing')
        errors = self._context_errors(self.context, observation=step not in ('S01', 'S02', 'S03'), fresh=step not in ('S10', 'S11'))
        if errors:
            self._record(step, 'denied', {'reason': '; '.join(errors)})
            self._transition(step, State.BLOCKED, '; '.join(errors))
            self._block_after(step, 'failed readiness')
            raise GateError('; '.join(errors))
        dispatch_time = self.clock()
        if not isinstance(dispatch_time, (int, float)) or not math.isfinite(dispatch_time):
            self._deny(step, 'invalid dispatch time')
        pin = _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age)
        try:
            with self.journal.transaction():
                # Recheck durable state while holding the writer lock.
                history = self.journal.replay(self.context.session_id)
                if any(e.kind == 'context_invalidated' for e in history):
                    raise GateError('context previously invalidated')
                contexts = [e.data['context'] for e in history if e.kind == 'localization_accepted']
                if contexts and contexts[-1] != self.context.to_dict():
                    raise GateError('durable scene mismatch')
                if any(e.kind == 'dispatch' and e.request_id == request_id for e in history):
                    raise GateError('request ID already dispatched')
                durable_states = {s: State.PENDING for s in STAGES}
                for event in history:
                    if event.kind == 'transition':
                        durable_states[event.step_id] = State(event.data['to'])
                    elif event.kind == 'localization_accepted':
                        durable_states[event.step_id] = State.SUCCEEDED
                if durable_states[step] != State.PENDING:
                    raise GateError('durable stage is not pending')
                if any(durable_states[s] != State.SUCCEEDED for s in STAGES[:STAGES.index(step)]):
                    raise GateError('durable predecessors not verified')
                if any(e.step_id == step and e.kind == 'dispatch' for e in history):
                    raise GateError('stage already dispatched')
                self.journal.db.execute('INSERT INTO stage_claims(session_id,step_id) VALUES (?,?)', (self.context.session_id, step))
                pins = [e.data['sha256'] for e in history if e.kind == 'config_pinned']
                if pins and (len(set(pins)) != 1 or pins[0] != pin):
                    raise GateError('pinned configuration changed')
                if not pins:
                    self._record(step, 'config_pinned', {'sha256': pin}, request_id)
                self._record(step, 'transition', {'from': 'PENDING', 'to': 'READY', 'reason': 'predecessors and readiness verified'})
                self._record(step, 'dispatch', {'context': self.context.to_dict(), 'dispatch_time': dispatch_time}, request_id)
                self._record(step, 'transition', {'from': 'READY', 'to': 'RUNNING', 'reason': 'request dispatched'}, request_id)
        except sqlite3.IntegrityError as exc:
            raise GateError('stage already claimed') from exc
        except BaseException:
            # Even if an error was raised after a write, the worker cannot know
            # whether the dispatch reservation is durable.
            self._poison()
            raise
        self.config_pin = pin
        self.requests[step] = request_id
        self.snapshots[step] = self.context
        self.dispatch_times[step] = dispatch_time
        self.states[step] = State.RUNNING

    def ack(self, step: str, request_id: str) -> None:
        self._require_usable()
        if self.states.get(step) != State.RUNNING or self.requests.get(step) != request_id:
            self._deny(step, 'uncorrelated acknowledgement')
        self._record(step, 'ack', {}, request_id)

    def _repeatable(self):
        return bool(getattr(self.profiles.get('ecu'), 'view_quaternions_xyzw', ()))

    def complete(self, evidence: Evidence, *, _verified_plan=None) -> None:
        self._require_usable()
        error = None
        try:
            with self.journal.transaction():
                history, states = self._durable()
                try:
                    self._verify_running(evidence.step_id, history, states)
                except GateError as exc:
                    self.states.update(states)
                    if (states.get(evidence.step_id) == State.RUNNING and self.config_pin is not None
                            and self.config_pin != _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age)):
                        self._record('', 'context_invalidated', {'reason': 'pinned configuration changed'})
                        for stage in STAGES:
                            if self.states[stage] in (State.PENDING, State.READY, State.RUNNING):
                                self._transition(stage, State.BLOCKED, 'pinned configuration changed')
                    self._record(evidence.step_id, 'result_rejected', {'reason': str(exc)}, evidence.request_id)
                    error = exc
                else:
                    try:
                        self._complete_locked(evidence, _verified_plan=_verified_plan)
                    except GateError as exc:
                        error = exc
        except BaseException:
            self._poison()
            raise
        if error:
            raise error

    def _complete_locked(self, evidence: Evidence, *, _verified_plan=None) -> None:
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
        if step == 'S05' and (self._repeatable() or evidence.plan_hash is not None):
            try:
                from .repeatability import InspectionPlan, verify_plan
                if not isinstance(_verified_plan, InspectionPlan) or evidence.plan_hash != _verified_plan.digest:
                    raise GateError('verified inspection plan required')
                verify_plan(_verified_plan, self.context, self.profiles, self.calibrations, self.requirements, self.clock(), self.max_age)
            except (GateError, ValueError, TypeError, AttributeError):
                reasons.append('verified inspection plan required')
        if step in ('S06', 'S07', 'S08') and (self._repeatable() or self.accepted_plan_hash):
            if not self.accepted_plan_hash or evidence.plan_hash != self.accepted_plan_hash:
                reasons.append('inspection plan binding mismatch')
            if step in ('S07', 'S08'):
                kind = 'capture_complete_verified' if step == 'S07' else 'quality_verified'
                if not any(e.kind == kind and e.request_id == evidence.request_id and e.data.get('plan_hash') == self.accepted_plan_hash for e in self.journal.replay(self.context.session_id)):
                    reasons.append('verified photography evidence missing')
        now = self.clock()
        observation_time = evidence.context.observation_timestamp if step not in ('S01', 'S02') else None
        if (not isinstance(evidence.timestamp, (int, float)) or not math.isfinite(evidence.timestamp)
                or not math.isfinite(now) or not 0 <= now - evidence.timestamp <= self.max_age
                or self.dispatch_times.get(step) is None or evidence.timestamp < self.dispatch_times[step]
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
                      'checks': sorted(evidence.checks), 'reference': evidence.reference, 'plan_hash': evidence.plan_hash}
        if step == 'S03':
            # One durable event commits both acceptance and context promotion.
            self._record(step, 'localization_accepted', {'evidence': serialized, 'context': evidence.context.to_dict(), 'transition': {'from': State.RUNNING.value, 'to': State.SUCCEEDED.value, 'reason': 'fresh localized scene verified'}}, evidence.request_id)
            self.context = evidence.context
            self.states[step] = State.SUCCEEDED
        else:
            self._record(step, 'result_accepted', {'evidence': serialized}, evidence.request_id)
            self._transition(step, State.SUCCEEDED, 'terminal evidence verified')
            if step == 'S05':
                self.accepted_plan_hash = evidence.plan_hash

    def stop(self, step: str, state: State, reason: str) -> None:
        self._require_usable()
        if state not in (State.FAILED, State.CANCELLED, State.TIMED_OUT) or not reason or step not in self.states:
            self._deny(step, 'invalid stop')
        error = None
        try:
            with self.journal.transaction():
                history, states = self._durable()
                try:
                    self._verify_running(step, history, states)
                except GateError as exc:
                    self.states.update(states)
                    if (states.get(step) == State.RUNNING and self.config_pin is not None
                            and self.config_pin != _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age)):
                        self._record('', 'context_invalidated', {'reason': 'pinned configuration changed'})
                        for stage in STAGES:
                            if self.states[stage] in (State.PENDING, State.READY, State.RUNNING):
                                self._transition(stage, State.BLOCKED, 'pinned configuration changed')
                    self._record(step, 'denied', {'reason': str(exc)})
                    error = exc
                else:
                    self._transition(step, state, reason)
                    self._block_after(step, reason)
        except BaseException:
            self._poison()
            raise
        if error:
            raise error
