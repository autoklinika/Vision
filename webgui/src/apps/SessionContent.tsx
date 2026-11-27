import { useTranslation } from '../i18n/LanguageProvider';
import { Button } from '@fluentui/react-components';
import { ArrowClockwiseRegular } from '@fluentui/react-icons';
import type { SessionControls } from '../api/useSessionView';

const messages = {
  NOT_REQUESTED: 'No session report requested. Use Refresh session to read the authorized Core report.',
  LOADING: 'Reading a protected point-in-time report…',
  AVAILABLE: 'Point-in-time report from Core / Runtime. Refresh to request a new report.',
  ACCESS_DENIED: 'Access denied. A server-authorized session is required; no protected report is retained.',
  UNAVAILABLE: 'Session report unavailable. The provider, connection or response could not be verified. No protected report is retained.',
  DISABLED: 'Protected session reads are disabled for this client mode. No session request is sent.',
  NO_ACTIVE_SESSION: 'No active inspection session is connected.',
} as const;

export function SessionContent({section, controls, fluent = false}: {section: 'summary' | 'inspection' | 'events'; controls: SessionControls; fluent?: boolean}) {
  const {t}=useTranslation();
  const {view, refreshSession, nextEvents} = controls;
  const {session, events} = view;
  const summary = section === 'summary';
  const message = summary && view.status === 'DISABLED' ? 'Protected reports are disabled in this client mode.' :
    summary && view.status === 'NOT_REQUESTED' ? 'No report loaded. Refresh session reads the authorized Core report.' :
    controls.autoRefresh && view.status === 'AVAILABLE' ? 'Session information refreshes automatically from Vision.' : messages[view.status];
  const refreshDisabled = view.status === 'DISABLED' || view.status === 'LOADING' || view.status === 'NO_ACTIVE_SESSION' || view.refreshing;
  const refresh = fluent?<Button icon={<ArrowClockwiseRegular/>} onClick={refreshSession} disabled={refreshDisabled}>{t("Refresh session")}</Button>:<button onClick={refreshSession} disabled={refreshDisabled}>{t("Refresh session")}</button>;
  return <section className={`session-report${summary ? ' session-summary' : ''}`} aria-label={t("Protected Core report")}>
    <div className="session-heading"><h2>{summary ? t("Core / Runtime session") : section === 'inspection' ? t("Inspection session report") : t("Session event journal")}</h2>{summary && refresh}</div>
    <p className="protected-read-status" role="status">{t(message)}</p>
    {!summary && <div className="app-actions">{refresh}{section === 'events' && <button onClick={nextEvents} disabled={!events || events.nextAfterSequence === null || view.status !== 'AVAILABLE' || view.refreshing}>{t("Load more events")}</button>}</div>}
    {session && <>
      {session.source === 'SYNTHETIC_TEST' && <p className="synthetic-label"><strong>{t("SYNTHETIC TEST · no station session")}</strong></p>}
      <div className="report sunken-panel"><dl>
        <dt>{t("Session")}</dt><dd>{session.sessionId}</dd>
        <dt>{t("Report source")}</dt><dd>{session.source}</dd>
        <dt>{t("Captured at (UTC)")}</dt><dd>{session.capturedAt}</dd>
        <dt>{t("Journal through")}</dt><dd>{session.journalSequence}</dd>
        <dt>{t("Core invalidation")}</dt><dd>{session.invalidated ? 'INVALIDATED' : t("Not reported")}</dd>
      </dl></div>
      {section === 'inspection' && <>
        <div className="sunken-panel session-table"><table aria-label={t("Reported inspection stages")}><thead><tr><th>{t("Stage")}</th><th>{t("Reported state")}</th><th>{t("Historical success")}</th><th>{t("Last transition")}</th><th>{t("Last ACK")}</th></tr></thead><tbody>{session.stages.map(stage => <tr key={stage.id}><td>{stage.id}</td><td>{stage.state}</td><td>{stage.historicalSuccess ? t("Recorded") : t("Not recorded")}</td><td>{stage.lastTransitionSequence ?? '—'}</td><td>{stage.lastAckSequence ?? '—'}</td></tr>)}</tbody></table></div>
        <p className="fine-print">{t("Historical success remains a historical fact when Core blocks a stage. ACK confirms receipt; it does not complete a stage.")}</p>
      </>}
      {section === 'events' && events && <>
        <p>{t("Journal page after {after}, pinned through {through}.",{after:events.afterSequence,through:events.throughSequence})} {events.nextAfterSequence === null ? t("End of this report.") : t("More events are available.")}</p>
        <div className="sunken-panel session-table"><table aria-label={t("Reported session events")}><thead><tr><th>{t("Sequence")}</th><th>{t("Time (UTC)")}</th><th>{t("Stage")}</th><th>{t("Event")}</th><th>{t("Reported state")}</th></tr></thead><tbody>{events.events.map(event => <tr key={event.sequence}><td>{event.sequence}</td><td>{event.timestamp}</td><td>{event.stageId ?? t("Session")}</td><td>{event.kind}</td><td>{event.state ?? '—'}</td></tr>)}</tbody></table>{events.events.length === 0 && <p>{t("No events in this report.")}</p>}</div>
        <p className="fine-print">{t("One bounded page is kept in this browser. Refresh session returns to the first page of a new report.")}</p>
      </>}
    </>}
    {session && <p className="fine-print">{t("This is a saved read result, not a live readiness signal. Session control and decisions belong to Vision.")}</p>}
  </section>;
}
