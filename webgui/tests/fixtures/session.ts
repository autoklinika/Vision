import type { EventsReport, SessionReport, StageReport } from '../../src/api/sessionContract';

export function sessionFixture(): SessionReport {
  const stages: StageReport[] = Array.from({length: 11}, (_, i) => ({
    id: `S${String(i + 1).padStart(2, '0')}`, state: 'PENDING', historicalSuccess: false,
    lastTransitionSequence: null, lastAckSequence: null,
  }));
  stages[0] = {...stages[0], state: 'SUCCEEDED', historicalSuccess: true, lastTransitionSequence: 6};
  stages[1] = {...stages[1], state: 'RUNNING', lastTransitionSequence: 10, lastAckSequence: 70};
  return {
    schema: 'vision.api.session.v1', scope: 'SESSION_READ_ONLY', source: 'SYNTHETIC_TEST',
    viewId: 'a'.repeat(32), sessionId: 'synthetic-api02', capturedAt: '2026-11-25T01:02:03Z',
    journalSequence: 70, invalidated: false, stages,
  };
}
export function eventsFixture(session = sessionFixture(), after = 0): EventsReport {
  const count = Math.min(50, session.journalSequence - after);
  const end = after + count;
  return {
    schema: 'vision.api.events.v1', scope: 'SESSION_READ_ONLY', source: session.source,
    viewId: session.viewId, sessionId: session.sessionId, capturedAt: session.capturedAt,
    throughSequence: session.journalSequence, afterSequence: after,
    nextAfterSequence: end < session.journalSequence ? end : null,
    events: Array.from({length: count}, (_, i) => ({
      sequence: after + i + 1, stageId: 'S02', kind: 'ack', timestamp: session.capturedAt, state: null,
    })),
  };
}
