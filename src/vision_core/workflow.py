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
from .extensions import ScenarioSpec, ModuleRegistry, ModuleReceipt

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
    def __init__(self, journal: Journal, context: Context, profiles: Mapping[str, Profile], calibrations: Mapping[str, str], requirements: Mapping[str, frozenset[str]], max_age: float, clock: Callable[[], float] = time.time, *, scenario: ScenarioSpec | None = None, registry: ModuleRegistry | None = None):
        if not math.isfinite(max_age) or max_age <= 0:
            raise ValueError('a positive finite freshness limit is required')
        self.journal, self.context, self.profiles = journal, context, dict(profiles)
        self.calibrations, self.requirements, self.max_age, self.clock = dict(calibrations), dict(requirements), max_age, clock
        self.scenario = scenario
        self.modules = {}
        self.stages = STAGES
        self.checks = {s: frozenset(CHECKS[s]) for s in self.stages}
        self.dependencies = {s: (() if i == 0 else (STAGES[i-1],)) for i, s in enumerate(STAGES)}
        if scenario is not None:
            if not isinstance(scenario, ScenarioSpec) or not isinstance(registry, ModuleRegistry):
                raise ValueError('scenario and registry required')
            registry.freeze()
            self.modules = {mid: registry.resolve(mid) for mid in scenario.required_module_ids}
            if any(m.profile_kind in PROFILE_KINDS for m in self.modules.values()):
                raise ValueError('module profile conflicts with builtin')
            specs = {s.stage_id: s for s in scenario.stages}
            for i, name in enumerate(STAGES):
                stage = specs.get(name)
                if (stage is None or stage.module_id is not None or not CHECKS[name] <= stage.checks
                        or (i and STAGES[i-1] not in stage.dependencies)):
                    raise ValueError('builtin stage chain and checks required')
            for stage in scenario.stages:
                if stage.stage_id not in STAGES:
                    module = self.modules.get(stage.module_id)
                    if module is None or stage.stage_id not in module.stage_ids:
                        raise ValueError('stage module mismatch')
                    if 'S03' not in self._ancestors(stage.stage_id, specs):
                        raise ValueError('module stage requires localization')
                    # Every selected module step is REQUIRED: it must be a
                    # transitive prerequisite of terminal S11, or the session
                    # could finish successfully without executing it.
                    if stage.stage_id not in self._ancestors('S11', specs):
                        raise ValueError('required module stage not linked to S11 completion')
            if set(self.modules) != {s.module_id for s in scenario.stages if s.module_id}:
                raise ValueError('unused or missing module')
            for module in self.modules.values():
                enabled = {s.stage_id for s in scenario.stages if s.module_id == module.module_id}
                if not set(module.required_stage_ids).issubset(enabled):
                    raise ValueError('required module stages missing from scenario')
            self.stages = tuple(specs)
            self.checks = {s.stage_id: s.checks for s in scenario.stages}
            self.dependencies = {s.stage_id: s.dependencies for s in scenario.stages}
        elif registry is not None:
            raise ValueError('registry requires scenario')
        self.ancestors = {}
        for stage in self.stages:
            self.ancestors[stage] = frozenset(self.dependencies[stage]).union(
                *(self.ancestors[parent] for parent in self.dependencies[stage]))
        self.extra_kinds = frozenset(m.profile_kind for m in self.modules.values())
        self.states = {s: State.PENDING for s in self.stages}
        self.requests = {}
        self.snapshots = {}
        self.dispatch_times = {}
        self.accepted_plan_hash = None
        self.config_pin = None
        self._journal_uncertain = False
        self._initial_pin = self._pin() if self.scenario is not None else None
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
            elif event.kind == 'transition' and event.step_id in self.states:
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
            # Replay keeps the historical success events in SQLite, but a
            # session invalidated for this selected graph/config must not
            # expose its old S11 success as a CURRENT successful outcome.
            for step in self.stages:
                self.states[step] = State.BLOCKED
        if invalidation is None and events and self.requests and self.config_pin is None:
            self.invalidate('journal has no pinned configuration')
        elif invalidation is None and self.config_pin is not None and self.config_pin != self._pin():
            self.invalidate('pinned configuration changed')
        # An interrupted action is ambiguous. Never redispatch it or its dependents.
        if any(self.states[step] in (State.READY, State.RUNNING) for step in self.stages):
            self.invalidate('restart requires external reconciliation')
        if journal_context is not None:
            # An initial unlocalized context is a valid restart input after promotion.
            if context != journal_context and not (not context.scene_revision and context.session_id == journal_context.session_id and context.profile_revisions == journal_context.profile_revisions):
                self.invalidate('context differs from journal')
            self.context = journal_context

    @staticmethod
    def _ancestors(stage, specs):
        result = set()
        pending = list(specs[stage].dependencies)
        while pending:
            item = pending.pop()
            if item not in result:
                result.add(item)
                pending.extend(specs[item].dependencies)
        return result

    def _pin(self):
        legacy = _fingerprint(self.profiles, self.calibrations, self.requirements, self.max_age)
        if self.scenario is None:
            return legacy
        data = _canonical({'legacy': legacy, 'scenario': self.scenario, 'modules': self.modules, 'stages': self.stages, 'checks': self.checks, 'dependencies': self.dependencies})
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

    def _poison(self) -> None:
        # A failed journal write/commit may have reached persistent storage.
        # This worker must never accept another result or dispatch another task.
        self._journal_uncertain = True
        for stage in self.stages:
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
        for later in self.stages:
            if step not in self.ancestors[later]:
                continue
            if self.states[later] in (State.PENDING, State.READY, State.RUNNING):
                self._transition(later, State.BLOCKED, reason)

    def _durable(self):
        history = self.journal.replay(self.context.session_id)
        states = {s: State.PENDING for s in self.stages}
        for event in history:
            if event.kind == 'transition' and event.step_id in states:
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
                or pins[0] != self._pin()
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
                for step in self.stages:
                    if self.states[step] in (State.PENDING, State.READY, State.RUNNING):
                        self._transition(step, State.BLOCKED, reason)
        if error:
            raise error
        # Historical SUCCEEDED transitions stay in the journal, while all
        # effective stage states for the invalidated context become BLOCKED.
        self.states.update({s: State.BLOCKED for s in self.stages})

    def update_context(self, context: Context) -> None:
        self._require_usable()
        if context != self.context:
            self.invalidate('context changed; new session and plan required')
            if context.session_id != self.context.session_id:
                raise GateError('session identity cannot change')
            self.context = context

    def _context_errors(self, c: Context, observation: bool = True, fresh: bool = True) -> list[str]:
        errors = validate_profiles(self.profiles, self.calibrations, self.requirements, extra_kinds=self.extra_kinds)
        if self._initial_pin is not None and self._initial_pin != self._pin():
            errors.append('scenario configuration changed')
        for module in self.modules.values():
            profile = self.profiles.get(module.profile_kind)
            if profile is None or not module.capabilities <= profile.capabilities:
                errors.append(f'{module.module_id}: missing module capabilities')
        if self.config_pin is not None and self.config_pin != self._pin():
            errors.append('pinned configuration changed')
        if not c.session_id or set(c.profile_revisions) != PROFILE_KINDS | self.extra_kinds:
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
        if self.scenario is not None and self._initial_pin != self._pin():
            self.invalidate('scenario configuration changed')
            raise GateError('scenario configuration changed; new session required')
        if step not in self.states:
            self._deny(step, 'unknown stage')
        if self.states[step] != State.PENDING:
            self._deny(step, 'stage is not pending')
        if not isinstance(request_id, str) or not request_id.strip() or request_id in self.requests.values():
            self._deny(step, 'missing or reused request ID')
        if any(self.states[s] != State.SUCCEEDED for s in self.dependencies[step]):
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
        pin = self._pin()
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
                durable_states = {s: State.PENDING for s in self.stages}
                for event in history:
                    if event.kind == 'transition' and event.step_id in durable_states:
                        durable_states[event.step_id] = State(event.data['to'])
                    elif event.kind == 'localization_accepted':
                        durable_states[event.step_id] = State.SUCCEEDED
                if durable_states[step] != State.PENDING:
                    raise GateError('durable stage is not pending')
                if any(durable_states[s] != State.SUCCEEDED for s in self.dependencies[step]):
                    raise GateError('durable predecessors not verified')
                if any(e.step_id == step and e.kind == 'dispatch' for e in history):
                    raise GateError('stage already dispatched')
                self.journal.db.execute('INSERT INTO stage_claims(session_id,step_id) VALUES (?,?)', (self.context.session_id, step))
                pins = [e.data['sha256'] for e in history if e.kind == 'config_pinned']
                if pins and (len(set(pins)) != 1 or pins[0] != pin):
                    raise GateError('pinned configuration changed')
                if not pins:
                    self._record(step, 'config_pinned', {'sha256': pin, **({'manifest': _canonical({'scenario': self.scenario, 'modules': self.modules, 'profiles': self.profiles, 'calibrations': self.calibrations, 'requirements': self.requirements, 'max_age': self.max_age})} if self.scenario is not None else {})}, request_id)
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

    def verify_module_receipt(self, receipt: ModuleReceipt, payload: bytes) -> None:
        """Record a trusted adapter's correlated result after checking payload integrity."""
        self._require_usable()
        if not isinstance(receipt, ModuleReceipt) or not isinstance(payload, bytes) or len(payload) > 128 * 1024 * 1024:
            raise GateError('typed receipt and payload required')
        try:
            with self.journal.transaction():
                history, states = self._durable()
                self._verify_running(receipt.step_id, history, states)
                spec = next((s for s in self.scenario.stages if s.stage_id == receipt.step_id), None) if self.scenario else None
                module = self.modules.get(spec.module_id) if spec else None
                now = self.clock()
                if (module is None or receipt.module_id != module.module_id or receipt.module_version != module.version
                    or receipt.session_id != self.context.session_id or receipt.request_id != self.requests.get(receipt.step_id)
                    or receipt.context != self.context or receipt.profile_revision != self.profiles[module.profile_kind].revision
                    or receipt.terminal_success is not True or not isinstance(receipt.reference, str) or not receipt.reference.strip()
                    or not isinstance(receipt.timestamp, (int, float)) or isinstance(receipt.timestamp, bool)
                    or not math.isfinite(receipt.timestamp) or not math.isfinite(now)
                    or not 0 <= now - receipt.timestamp <= self.max_age
                    or receipt.timestamp < self.dispatch_times[receipt.step_id]
                    or receipt.timestamp < self.context.observation_timestamp
                    or hashlib.sha256(payload).hexdigest() != receipt.payload_sha256
                    or self._context_errors(self.context)
                    or any(e.kind == 'module_verified' and e.step_id == receipt.step_id for e in history)):
                    raise GateError('invalid or duplicate module receipt')
                self._record(receipt.step_id, 'module_verified', _canonical(receipt), receipt.request_id)
        except GateError:
            raise
        except BaseException:
            self._poison()
            raise

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
                            and self.config_pin != self._pin()):
                        self._record('', 'context_invalidated', {'reason': 'pinned configuration changed'})
                        for stage in self.stages:
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
                verify_plan(_verified_plan, self.context, self.profiles, self.calibrations, self.requirements, self.clock(), self.max_age, extra_kinds=self.extra_kinds)
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
        if evidence.quality is not True or evidence.terminal_success is not True or not evidence.reference or step not in self.checks or not self.checks.get(step, set()).issubset(evidence.checks):
            reasons.append('incomplete terminal evidence')
        if step in self.stages and self.scenario is not None:
            spec = next(s for s in self.scenario.stages if s.stage_id == step)
            if spec.module_id:
                verified = [e for e in self.journal.replay(self.context.session_id)
                            if e.kind == 'module_verified' and e.step_id == step and e.request_id == evidence.request_id]
                if (len(verified) != 1 or verified[0].data.get('module_id') != spec.module_id
                    or verified[0].data.get('reference') != evidence.reference
                    or verified[0].data.get('module_version') != self.modules[spec.module_id].version
                    or verified[0].data.get('context') != self.context.to_dict()
                    or verified[0].data.get('profile_revision') != self.profiles[self.modules[spec.module_id].profile_kind].revision
                    or not 0 <= now - verified[0].data.get('timestamp', float('-inf')) <= self.max_age):
                    reasons.append('fresh verified module receipt required')
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
                            and self.config_pin != self._pin()):
                        self._record('', 'context_invalidated', {'reason': 'pinned configuration changed'})
                        for stage in self.stages:
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
