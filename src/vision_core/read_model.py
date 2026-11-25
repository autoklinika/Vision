"""Immutable projections of an existing engine, with no workflow side effects.

This module reports committed state, not readiness or authorization. The report
clock is wall time at extraction, independent of the engine's evidence clock.
Sequence numbers define journal order; event timestamps need not be monotonic.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import math
import re
import sqlite3
import time

from .models import State

MAX_STAGES = 256
MAX_EVENTS = 50
MAX_SEQUENCE = 2 ** 53 - 1
READ_LOCK_TIMEOUT = 0.25
EVENT_KINDS = frozenset({
    'config_pinned', 'transition', 'dispatch', 'ack', 'denied',
    'result_accepted', 'result_rejected', 'localization_accepted',
    'context_invalidated', 'preparation_verified', 'planning_verified',
    'module_verified', 'motion_verified', 'capture_verified',
    'capture_complete_verified', 'quality_verified',
    'module_archive_verified', 'archive_verified', 'OTHER',
})
_STAGE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z', re.ASCII)


class ReadUnavailable(RuntimeError):
    """Fixed reason code; callers must not return database exception details."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class StageSnapshot:
    stage_id: str
    state: State
    historical_success: bool
    last_transition_sequence: int | None
    last_ack_sequence: int | None


@dataclass(frozen=True)
class WorkflowSnapshot:
    session_id: str
    captured_at: float
    high_water: int
    invalidated: bool
    stages: tuple[StageSnapshot, ...]


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    stage_id: str | None
    kind: str
    timestamp: float
    state: State | None


@dataclass(frozen=True)
class EventPage:
    session_id: str
    captured_at: float
    high_water: int
    after_sequence: int
    next_after_sequence: int | None
    events: tuple[JournalEvent, ...]


def _sequence(value, *, minimum=0):
    return type(value) is int and minimum <= value <= MAX_SEQUENCE


@contextmanager
def _committed_view(engine):
    # The same lock covers journal append/commit and the memory update that
    # follows commit in start(). A read never waits indefinitely for an owner.
    if not engine._owner_lock.acquire(timeout=READ_LOCK_TIMEOUT):
        raise ReadUnavailable('CORE_BUSY')
    try:
        if engine._mutation_depth:
            raise ReadUnavailable('CORE_BUSY')
        if engine._journal_uncertain:
            raise ReadUnavailable('JOURNAL_UNCERTAIN')
        if (not isinstance(engine.stages, tuple)
                or not 1 <= len(engine.stages) <= MAX_STAGES
                or len(set(engine.stages)) != len(engine.stages)
                or any(not isinstance(s, str) or not _STAGE_ID.fullmatch(s)
                       for s in engine.stages)
                or set(engine.states) != set(engine.stages)
                or any(type(s) is not State for s in engine.states.values())):
            raise ReadUnavailable('INCONSISTENT_STATE')
        try:
            with engine.journal.read_transaction() as db:
                yield db
        except (sqlite3.Error, RuntimeError) as exc:
            if isinstance(exc, ReadUnavailable):
                raise
            raise ReadUnavailable('JOURNAL_UNAVAILABLE') from exc
    finally:
        engine._owner_lock.release()


def _snapshot(engine, db):
    session_id = engine.context.session_id
    high_water = db.execute(
        'SELECT COALESCE(MAX(sequence),0) FROM events WHERE session_id=?',
        (session_id,)).fetchone()[0]
    if not _sequence(high_water):
        raise ReadUnavailable('INCONSISTENT_STATE')
    invalidated = bool(db.execute(
        "SELECT EXISTS(SELECT 1 FROM events WHERE session_id=? "
        "AND kind='context_invalidated')", (session_id,)).fetchone()[0])

    # SQL aggregates keep Python memory bounded by the scenario, including
    # sessions with an unbounded number of repeated ACK/denial events.
    latest = db.execute('''SELECT e.sequence,
            CASE WHEN length(e.step_id)<=64 THEN e.step_id ELSE NULL END,
            e.kind,
            CASE WHEN e.kind='transition' THEN json_extract(e.data,'$.to')
                 ELSE 'SUCCEEDED' END
        FROM events e JOIN (
            SELECT step_id,MAX(sequence) AS seq FROM events
            WHERE session_id=? AND kind IN ('transition','localization_accepted')
            GROUP BY step_id LIMIT ?
        ) last ON e.sequence=last.seq''', (session_id, MAX_STAGES + 1)).fetchall()
    if len(latest) > MAX_STAGES:
        raise ReadUnavailable('INCONSISTENT_STATE')
    current = {s: State.PENDING for s in engine.stages}
    transitions = {}
    for sequence, stage, _kind, state in latest:
        if stage not in current or not _sequence(sequence, minimum=1):
            raise ReadUnavailable('INCONSISTENT_STATE')
        try:
            current[stage] = State(state)
        except ValueError as exc:
            raise ReadUnavailable('INCONSISTENT_STATE') from exc
        transitions[stage] = sequence
    if invalidated:
        current = {s: State.BLOCKED for s in engine.stages}
    if engine.states != current:
        # Another owner or direct memory edit is never silently repaired by a
        # read. Reconciliation belongs to the active backend owner.
        raise ReadUnavailable('INCONSISTENT_STATE')

    placeholders = ','.join('?' for _ in engine.stages)
    args = (session_id, *engine.stages)
    successes = dict(db.execute(f'''SELECT step_id,MAX(sequence) FROM events
        WHERE session_id=? AND step_id IN ({placeholders}) AND (
            kind='localization_accepted' OR
            (kind='transition' AND json_extract(data,'$.to')='SUCCEEDED'))
        GROUP BY step_id''', args).fetchall())
    acknowledgements = dict(db.execute(f'''SELECT step_id,MAX(sequence)
        FROM events WHERE session_id=? AND step_id IN ({placeholders})
        AND kind='ack' GROUP BY step_id''', args).fetchall())
    if any(not _sequence(s, minimum=1)
           for s in (*successes.values(), *acknowledgements.values())):
        raise ReadUnavailable('INCONSISTENT_STATE')
    captured_at = time.time()
    if not math.isfinite(captured_at):
        raise ReadUnavailable('INCONSISTENT_STATE')
    return WorkflowSnapshot(session_id, captured_at, high_water, invalidated,
        tuple(StageSnapshot(s, current[s], s in successes,
                            transitions.get(s), acknowledgements.get(s))
              for s in engine.stages))


def read_snapshot(engine):
    """Extract a current committed projection; do not call Workflow(...)."""
    with _committed_view(engine) as db:
        return _snapshot(engine, db)


def read_events(engine, *, after_sequence=0, limit=MAX_EVENTS,
                through_sequence=None):
    """Page a pinned journal prefix, omitting payloads and free-form strings."""
    if (not _sequence(after_sequence) or type(limit) is not int
            or not 1 <= limit <= MAX_EVENTS
            or (through_sequence is not None and not _sequence(through_sequence))):
        raise ValueError('invalid event page bounds')
    with _committed_view(engine) as db:
        snapshot = _snapshot(engine, db)
        high_water = snapshot.high_water if through_sequence is None else through_sequence
        if not after_sequence <= high_water <= snapshot.high_water:
            raise ValueError('invalid event page bounds')
        stage_placeholders = ','.join('?' for _ in engine.stages)
        allowed_kinds = tuple(sorted(EVENT_KINDS))
        kind_placeholders = ','.join('?' for _ in allowed_kinds)
        rows = db.execute(f'''SELECT sequence,
                CASE WHEN step_id IN ({stage_placeholders}) THEN step_id ELSE NULL END,
                CASE WHEN kind IN ({kind_placeholders}) THEN kind ELSE 'OTHER' END,
                timestamp,
                CASE WHEN kind='transition' THEN json_extract(data,'$.to')
                     WHEN kind='localization_accepted' THEN 'SUCCEEDED'
                     ELSE NULL END
            FROM events WHERE session_id=? AND sequence>? AND sequence<=?
            ORDER BY sequence LIMIT ?''',
            (*engine.stages, *allowed_kinds, snapshot.session_id,
             after_sequence, high_water, limit + 1)).fetchall()
        result = []
        for sequence, stage, kind, timestamp, state in rows[:limit]:
            if (not _sequence(sequence, minimum=1)
                    or not after_sequence < sequence <= high_water
                    or type(timestamp) not in (int, float)
                    or not math.isfinite(timestamp)):
                raise ReadUnavailable('INCONSISTENT_STATE')
            try:
                state = State(state) if state is not None else None
            except ValueError as exc:
                raise ReadUnavailable('INCONSISTENT_STATE') from exc
            result.append(JournalEvent(sequence,
                stage if stage in engine.stages else None,
                kind if kind in EVENT_KINDS else 'OTHER', timestamp, state))
        next_after = result[-1].sequence if len(rows) > limit else None
        return EventPage(snapshot.session_id, snapshot.captured_at, high_water,
                         after_sequence, next_after, tuple(result))
