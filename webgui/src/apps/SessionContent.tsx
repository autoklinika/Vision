import type { SessionControls } from '../api/useSessionView';

const messages = {
  NOT_REQUESTED: 'No session report requested. Use Refresh session to read the authorized Core report.',
  LOADING: 'Reading a protected point-in-time report…',
  AVAILABLE: 'Point-in-time report from Core / Runtime. Refresh to request a new report.',
  ACCESS_DENIED: 'Access denied. A server-authorized session is required; no protected report is retained.',
  UNAVAILABLE: 'Session report unavailable. The provider, connection or response could not be verified. No protected report is retained.',
  DISABLED: 'Protected session reads are disabled for this client mode. No session request is sent.',
} as const;

export function SessionContent({section, controls}: {section: 'summary' | 'inspection' | 'events'; controls: SessionControls}) {
  const {view, refreshSession, nextEvents} = controls;
  const {session, events} = view;
  return <section className="session-report" aria-label="Protected Core report">
    <h2>{section === 'summary' ? 'Core / Runtime session' : section === 'inspection' ? 'Inspection session report' : 'Session event journal'}</h2>
    <p className="protected-read-status" role="status">{messages[view.status]}</p>
    <div className="app-actions"><button onClick={refreshSession} disabled={view.status === 'DISABLED' || view.status === 'LOADING'}>Refresh session</button>{section === 'events' && <button onClick={nextEvents} disabled={!events || events.nextAfterSequence === null || view.status !== 'AVAILABLE'}>Load more events</button>}</div>
    {session && <>
      {session.source === 'SYNTHETIC_TEST' && <p className="synthetic-label"><strong>SYNTHETIC TEST · no station session</strong></p>}
      <div className="report sunken-panel"><dl>
        <dt>Session</dt><dd>{session.sessionId}</dd>
        <dt>Report source</dt><dd>{session.source}</dd>
        <dt>Captured at (UTC)</dt><dd>{session.capturedAt}</dd>
        <dt>Journal through</dt><dd>{session.journalSequence}</dd>
        <dt>Core invalidation</dt><dd>{session.invalidated ? 'INVALIDATED' : 'Not reported'}</dd>
      </dl></div>
      {section === 'inspection' && <>
        <div className="sunken-panel session-table"><table aria-label="Reported inspection stages"><thead><tr><th>Stage</th><th>Reported state</th><th>Historical success</th><th>Last transition</th><th>Last ACK</th></tr></thead><tbody>{session.stages.map(stage => <tr key={stage.id}><td>{stage.id}</td><td>{stage.state}</td><td>{stage.historicalSuccess ? 'Recorded' : 'Not recorded'}</td><td>{stage.lastTransitionSequence ?? '—'}</td><td>{stage.lastAckSequence ?? '—'}</td></tr>)}</tbody></table></div>
        <p className="fine-print">Historical success remains a historical fact when Core blocks a stage. ACK confirms receipt; it does not complete a stage.</p>
      </>}
      {section === 'events' && events && <>
        <p>Journal page after {events.afterSequence}, pinned through {events.throughSequence}. {events.nextAfterSequence === null ? 'End of this report.' : 'More events are available.'}</p>
        <div className="sunken-panel session-table"><table aria-label="Reported session events"><thead><tr><th>Sequence</th><th>Time (UTC)</th><th>Stage</th><th>Event</th><th>Reported state</th></tr></thead><tbody>{events.events.map(event => <tr key={event.sequence}><td>{event.sequence}</td><td>{event.timestamp}</td><td>{event.stageId ?? 'Session'}</td><td>{event.kind}</td><td>{event.state ?? '—'}</td></tr>)}</tbody></table>{events.events.length === 0 && <p>No events in this report.</p>}</div>
        <p className="fine-print">One bounded page is kept in this browser. Refresh session returns to the first page of a new report.</p>
      </>}
    </>}
    <p className="fine-print">This is a saved read result, not a live readiness signal. Session control and decisions belong to Vision.</p>
  </section>;
}
