"""Offline result verification and sequential photography orchestration.

No methods in this module issue hardware requests. Adapter results are inputs.
"""
from dataclasses import dataclass
import math
from .archive import Archive, digest, _name
from .models import Context, Evidence, GateError, State
from .workflow import CHECKS, Workflow


@dataclass(frozen=True)
class View:
    view_id: str
    target: tuple[float, float, float]  # ECU-relative, not joints
    require_raw: bool = False


@dataclass(frozen=True)
class ResultIdentity:
    context: Context
    request_id: str
    view_id: str
    timestamp: float


@dataclass(frozen=True)
class MotionResult:
    identity: ResultIdentity
    terminal_success: bool
    measured_state: tuple[float, ...]
    goal_verified: bool
    state_timestamp: float
    reference: str


@dataclass(frozen=True)
class Original:
    kind: str
    data: bytes
    sha256: str
    source_id: str


@dataclass(frozen=True)
class CaptureResult:
    identity: ResultIdentity
    shutter_ack: bool
    transfer_complete: bool
    originals: tuple[Original, ...]
    reference: str


@dataclass(frozen=True)
class CoverageProof:
    context: Context
    request_id: str
    view_ids: frozenset[str]
    timestamp: float
    verified: bool
    reference: str


class PhotographySession:
    def __init__(self, workflow: Workflow, archive: Archive, views: tuple[View, ...]):
        self.workflow, self.archive, self.views = workflow, archive, tuple(views)
        if workflow.states['S07'] != State.RUNNING or workflow.states['S06'] != State.SUCCEEDED:
            raise GateError('S07 must be running after verified S06')
        try:
            if not views or len({v.view_id for v in views}) != len(views):
                raise ValueError('empty or duplicate views')
            for v in views:
                _name(v.view_id)
                if len(v.target) != 3 or any(not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) for n in v.target):
                    raise ValueError('invalid ECU-relative target')
                if v.require_raw and 'raw' not in workflow.profiles['capture'].capabilities:
                    raise ValueError('capture profile lacks raw capability')
            if archive.path.name != workflow.context.session_id:
                raise ValueError('archive session mismatch')
        except Exception as exc:
            self._fail(str(exc))
        self.records = []
        self.sources = set()
        self.hashes = set()
        self.motion = None

    def _fail(self, reason: str):
        if self.workflow.states['S07'] == State.RUNNING:
            self.workflow.stop('S07', State.FAILED, reason)
        raise GateError(reason)

    def _identity(self, identity: ResultIdentity):
        w = self.workflow
        if w.states['S07'] != State.RUNNING or w.snapshots.get('S07') != w.context:
            raise ValueError('S07 is not running with its dispatched context')
        if len(self.records) >= len(self.views):
            raise ValueError('duplicate or late view')
        if (identity.context != w.context or identity.request_id != w.requests['S07']
                or identity.view_id != self.views[len(self.records)].view_id
                or not isinstance(identity.timestamp, (int, float)) or not math.isfinite(identity.timestamp)
                or not 0 <= w.clock() - identity.timestamp <= w.max_age
                or identity.timestamp < w.context.observation_timestamp):
            raise ValueError('mismatched or stale result identity')

    def accept_motion(self, result: MotionResult):
        try:
            self._identity(result.identity)
            if (self.motion is not None or result.terminal_success is not True or result.goal_verified is not True
                    or not result.reference or not result.measured_state
                    or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in result.measured_state)
                    or not math.isfinite(result.state_timestamp) or result.state_timestamp < result.identity.timestamp
                    or not 0 <= self.workflow.clock() - result.state_timestamp <= self.workflow.max_age):
                raise ValueError('motion lacks terminal goal and fresh measured state')
            self.motion = result
            self.workflow._record('S07', 'motion_verified', {'view_id': result.identity.view_id, 'reference': result.reference, 'timestamp': result.identity.timestamp, 'state_timestamp': result.state_timestamp, 'measured_state': result.measured_state})
        except (ValueError, TypeError, AttributeError) as exc:
            self._fail(str(exc))

    def accept_capture(self, result: CaptureResult):
        try:
            self._identity(result.identity)
            if (self.motion is None or result.identity.timestamp < self.motion.state_timestamp
                    or result.shutter_ack is not True or result.transfer_complete is not True or not result.reference):
                raise ValueError('capture lacks prior motion, ACK or completed transfer')
            kinds = [o.kind for o in result.originals]
            required = {'raw'} if self.views[len(self.records)].require_raw else set()
            if not ({'jpeg', 'png'} & set(kinds)) or not required.issubset(kinds) or len(kinds) != len(set(kinds)) or set(kinds) - {'jpeg', 'png', 'raw'}:
                raise ValueError('missing or duplicate required original')
            files = []
            sources, hashes = set(self.sources), set(self.hashes)
            for original in result.originals:
                if ((original.kind == 'jpeg' and not original.data.startswith(b'\xff\xd8\xff'))
                        or (original.kind == 'png' and not original.data.startswith(b'\x89PNG\r\n\x1a\n'))
                        or not original.source_id or original.source_id in sources or not original.data
                        or digest(original.data) != original.sha256 or original.sha256 in hashes):
                    raise ValueError('corrupt or duplicate source original')
                sources.add(original.source_id)
                hashes.add(original.sha256)
            for original in result.originals:
                name = result.identity.view_id + '.' + {'jpeg': 'jpg', 'png': 'png', 'raw': 'raw'}[original.kind]
                self.archive.write(name, original.data)
                files.append({'name': name, 'kind': original.kind, 'sha256': original.sha256, 'source_id': original.source_id})
            record = {'view_id': result.identity.view_id, 'target': self.views[len(self.records)].target,
                      'motion_reference': self.motion.reference, 'motion_timestamp': self.motion.identity.timestamp,
                      'state_timestamp': self.motion.state_timestamp, 'measured_state': self.motion.measured_state,
                      'capture_reference': result.reference, 'capture_timestamp': result.identity.timestamp, 'files': files}
            self.sources, self.hashes = sources, hashes
            self.records.append(record)
            self.motion = None
            self.workflow._record('S07', 'capture_verified', record)
        except (ValueError, TypeError, AttributeError, OSError) as exc:
            self._fail(str(exc))

    def complete_capture(self):
        if self.workflow.states['S07'] != State.RUNNING or self.workflow.snapshots.get('S07') != self.workflow.context:
            raise GateError('S07 is not running with its dispatched context')
        if len(self.records) != len(self.views) or self.motion is not None:
            self._fail('not all views transferred')
        try:
            for record in self.records:
                for file in record['files']:
                    self.archive.verify(file['name'], file['sha256'])
            self._complete('S07', 'verified originals and motion journal')
        except (ValueError, OSError) as exc:
            self._fail(str(exc))

    def _complete(self, step: str, reference: str):
        w = self.workflow
        w.complete(Evidence(w.context.session_id, step, w.requests[step], w.context, w.clock(), True, True, frozenset(CHECKS[step]), reference))

    def assess(self, policy, proof: CoverageProof):
        from .quality import evaluate
        w = self.workflow
        try:
            if w.states['S08'] != State.RUNNING:
                raise ValueError('S08 must be running')
            if (proof.context != w.context or proof.request_id != w.requests['S08'] or proof.verified is not True
                    or proof.view_ids != frozenset(v.view_id for v in self.views) or not proof.reference
                    or not math.isfinite(proof.timestamp) or not 0 <= w.clock() - proof.timestamp <= w.max_age
                    or proof.timestamp < w.context.observation_timestamp):
                raise ValueError('independent spatial coverage proof missing or invalid')
            for record in self.records:
                for f in record['files']:
                    self.archive.verify(f['name'], f['sha256'])
                image = next(f for f in record['files'] if f['kind'] in ('jpeg', 'png'))
                data = self.archive._read(image['name'])
                record['qa'] = evaluate(data, policy)
                derived_name = record['view_id'] + '.derived.' + image['kind']
                derived_hash = self.archive.write(derived_name, data)
                record['derived'] = {'name': derived_name, 'sha256': derived_hash}
            w._record('S08', 'quality_verified', {'views': self.records, 'coverage_reference': proof.reference, 'coverage_timestamp': proof.timestamp})
            self.coverage = {'reference': proof.reference, 'timestamp': proof.timestamp, 'view_ids': sorted(proof.view_ids)}
            self._complete('S08', proof.reference)
        except (ValueError, TypeError, AttributeError, OSError, StopIteration) as exc:
            if w.states['S08'] == State.RUNNING:
                w.stop('S08', State.FAILED, str(exc) or 'missing QA image')
            raise GateError(str(exc)) from exc

    def archive_session(self):
        w = self.workflow
        try:
            if w.states['S10'] != State.RUNNING or w.states['S09'] != State.SUCCEEDED:
                raise ValueError('S10 requires separately successful S09')
            for record in self.records:
                for f in record['files']:
                    self.archive.verify(f['name'], f['sha256'])
            for record in self.records:
                self.archive.verify(record['derived']['name'], record['derived']['sha256'])
            events = [{'sequence': e.sequence, 'step_id': e.step_id, 'request_id': e.request_id, 'kind': e.kind, 'data': e.data, 'timestamp': e.timestamp} for e in w.journal.replay(w.context.session_id)]
            document = {'schema_version': 1, 'context': w.context.to_dict(), 'request_id': w.requests['S07'], 'views': self.records, 'coverage': self.coverage, 'events': events, 'status': 'prepared'}
            name, hash_value = self.archive.manifest(document)
            self.archive.verify(name, hash_value)
            w._record('S10', 'archive_verified', {'manifest': name, 'sha256': hash_value})
            self._complete('S10', name + ':' + hash_value)
        except (ValueError, TypeError, OSError, AttributeError) as exc:
            if w.states['S10'] == State.RUNNING:
                w.stop('S10', State.FAILED, str(exc))
            raise GateError(str(exc)) from exc
