import { useTranslation } from '../i18n/LanguageProvider';
import type { StationPresentation } from './client';
import type { SessionControls } from '../api/useSessionView';
import { SessionContent } from '../apps/SessionContent';
import { InspectionContent } from './InspectionContent';

export function StationStatusContent({station, session}: {station: StationPresentation; session: SessionControls}) {
  const {t}=useTranslation();
  const {report, identity} = station;
  return <>
    <div className="app-heading"><span className="status-mark">i</span><div><h2>{t("VENTUNO workstation")}</h2><p>{t("Connected · {role}",{role:t(identity.role==='operator'?'inspection operator':'read-only access')})}</p></div></div>
    <div className="report sunken-panel"><dl>
      <dt>{t("Signed in as")}</dt><dd>{identity.username}</dd>
      <dt>Vision Core</dt><dd>{report.coreConnection === 'CONNECTED' ? t("Connected") : t("Not connected")}</dd>
      <dt>{t("Inspection session")}</dt><dd>{report.coreConnection === 'NOT_CONNECTED' ? t("Unavailable") : report.state === 'SESSION_ACTIVE' ? report.sessionId : t("No active inspection session")}</dd>
      <dt>{t("System readiness")}</dt><dd>{t("Unknown until verified — see inspection readiness below")}</dd>
      <dt>{t("Last update (UTC)")}</dt><dd>{report.capturedAt}</dd>
    </dl></div>
    <p>{report.coreConnection === 'NOT_CONNECTED' ? t("Vision Core is not connected. Inspection and library reports are unavailable.") :
      report.state === 'NO_ACTIVE_SESSION' ? t("Vision Core is connected. No inspection session is active.") : t("The current session report comes from Vision Core.")}</p>
    <p><button onClick={station.refresh}>{t("Refresh station")}</button></p>
    <p className="fine-print">{t("Station information refreshes automatically. Closing this desktop leaves Vision running.")}</p>
    <InspectionContent key={[report.instanceId,report.coreConnection,report.sessionId,report.sessionViewId,station.accountBusy].join(':')} station={station}/>
    <SessionContent section="summary" controls={session}/>
  </>;
}
