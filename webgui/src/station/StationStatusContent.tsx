import type { StationPresentation } from './client';
import type { SessionControls } from '../api/useSessionView';
import { SessionContent } from '../apps/SessionContent';

export function StationStatusContent({station, session}: {station: StationPresentation; session: SessionControls}) {
  const {report, identity} = station;
  return <>
    <div className="app-heading"><span className="status-mark">i</span><div><h2>VENTUNO workstation</h2><p>Connected · read-only access</p></div></div>
    <div className="report sunken-panel"><dl>
      <dt>Signed in as</dt><dd>{identity.username}</dd>
      <dt>Vision Core</dt><dd>{report.coreConnection === 'CONNECTED' ? 'Connected' : 'Not connected'}</dd>
      <dt>Inspection session</dt><dd>{report.state === 'SESSION_ACTIVE' ? report.sessionId : 'No active session connected'}</dd>
      <dt>System readiness</dt><dd>Unknown</dd>
      <dt>Last update (UTC)</dt><dd>{report.capturedAt}</dd>
    </dl></div>
    <p>{report.coreConnection === 'NOT_CONNECTED' ? 'Vision Core is not connected. Inspection and device reports are unavailable.' : 'The current session report comes from Vision Core.'}</p>
    <p><button onClick={station.refresh}>Refresh station</button></p>
    <p className="fine-print">Station information refreshes automatically. Closing this desktop leaves Vision running.</p>
    <SessionContent section="summary" controls={session}/>
  </>;
}
