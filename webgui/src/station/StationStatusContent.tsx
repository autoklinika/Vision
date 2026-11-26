import { Badge, MessageBar, MessageBarBody, MessageBarTitle, Toolbar, ToolbarButton } from '@fluentui/react-components';
import { ArrowClockwiseRegular, ArrowRightRegular, DesktopPulseRegular } from '@fluentui/react-icons';
import { useTranslation } from '../i18n/LanguageProvider';
import type { StationPresentation } from './client';
import type { SessionControls } from '../api/useSessionView';
import { SessionContent } from '../apps/SessionContent';
import { InspectionContent } from './InspectionContent';

export function StationStatusContent({station, session, openInspection}: {
  station: StationPresentation; session: SessionControls; openInspection?: () => void;
}) {
  const {t}=useTranslation();
  const {report, identity} = station;
  const connected=report.coreConnection==='CONNECTED';
  const active=connected&&report.state==='SESSION_ACTIVE';
  return <div className="vision-system-status">
    <section className="station-overview" aria-label={t("Station overview")}>
      <div className="station-overview-heading">
        <div className="station-overview-title"><span className="station-overview-icon" aria-hidden="true"><DesktopPulseRegular fontSize={24}/></span><div><h2>{t("VENTUNO workstation")}</h2><span>{t("Station overview")}</span></div></div>
        <Toolbar aria-label={t("Station actions")} className="station-status-toolbar">
          <ToolbarButton icon={<ArrowClockwiseRegular/>} onClick={station.refresh}>{t("Refresh station")}</ToolbarButton>
          {openInspection&&<ToolbarButton icon={<ArrowRightRegular/>} onClick={openInspection}>{t("Open inspection manager")}</ToolbarButton>}
        </Toolbar>
      </div>
      <dl className="station-overview-facts">
        <div><dt>Vision Core</dt><dd><Badge appearance="tint" color={connected?'success':'warning'}>{t(connected?"Connected":"Not connected")}</Badge></dd></div>
        <div><dt>{t("System readiness")}</dt><dd><Badge appearance="tint" color="informative">{t("Unknown")}</Badge></dd></div>
        <div><dt>{t("Inspection session")}</dt><dd>{!connected?t("Unavailable"):active?report.sessionId:t("No active inspection session")}</dd></div>
        <div><dt>{t("Signed in as")}</dt><dd>{identity.username}<small>{t(identity.role==='operator'?'inspection operator':'read-only access')}</small></dd></div>
      </dl>
      <div className="station-overview-meta"><span>{t("Last update (UTC)")} · <time dateTime={report.capturedAt}>{report.capturedAt}</time></span><span>{t("Automatic refresh")}</span></div>
    </section>
    {!connected && <MessageBar intent="warning" className="station-status-message">
      <MessageBarBody>
        <MessageBarTitle>{t("Core connection unavailable")}:</MessageBarTitle>{" "}
        {t("Vision Core is not connected. Inspection and library reports are unavailable.")}
      </MessageBarBody>
    </MessageBar>}
    <InspectionContent key={[report.instanceId,report.coreConnection,report.sessionId,report.sessionViewId,station.accountBusy].join(':')} station={station}/>
    <div className="station-session-area">
      <div className="station-session-title"><h2>{t("Inspection session")}</h2></div>
      <SessionContent section="summary" controls={session} fluent/>
    </div>
  </div>;
}
