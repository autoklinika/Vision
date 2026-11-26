import { useTranslation } from '../i18n/LanguageProvider';
import type { Snapshot } from '../api/types';
import type { SessionControls } from '../api/useSessionView';
import { SessionContent } from './SessionContent';
import type { LibraryControls } from '../api/useLibraryView';
import { LibraryContent } from './LibraryContent';
import type { StationPresentation } from '../station/client';
import { StationStatusContent } from '../station/StationStatusContent';
import { connectionLabel } from '../api/presentation';
import type { AppId } from '../shell/model';
import { SettingsContent } from './SettingsContent';
const placeholders: Record<Exclude<AppId, 'status' | 'control' | 'inspection' | 'events' | 'ecu' | 'settings'>, { heading: string; columns: string[]; message: string; action: string }> = {
  luxonis: { heading: 'RGB-D observation', columns: ['RGB', 'Depth', 'Point cloud', 'Timestamp'], message: 'No sensor media available. Frames, geometry and measurements must come from the Vision interface.', action: 'Acquire frame' },
  nero: { heading: 'Motion & planning', columns: ['Robot report', 'Scene', 'Plan', 'Operation'], message: 'No robot or planner report available. No local kinematics, trajectory generation or motion execution.', action: 'Request motion' },
  sony: { heading: 'Camera acquisition', columns: ['Camera', 'Parameters', 'Capture', 'Transfer'], message: 'No acquisition report or photographs available. This client has no camera connection.', action: 'Capture photograph' },
  images: { heading: 'Image archive', columns: ['Asset', 'Source', 'Timestamp', 'Metadata'], message: 'No archive connected. Image browsing, A/B comparison and overlays are proposed for GUI-06.', action: 'Open image' },
};
export function AppContent({ id, snapshot, reset, persistence, refresh, sessionControls, libraryControls, station, onNavigate }: { id: AppId; snapshot: Snapshot | null; reset: () => void; persistence: string; refresh?: () => void; sessionControls?: SessionControls; libraryControls?: LibraryControls; station?: StationPresentation; onNavigate?: (id: AppId) => void }) {
  const {t}=useTranslation();
  if (id === 'settings') return <SettingsContent station={station}/>;
  if (id === 'status' && station && sessionControls) return <StationStatusContent station={station} session={sessionControls} openInspection={onNavigate?()=>onNavigate("inspection"):undefined}/>;
  if (id === 'ecu') return libraryControls ? <LibraryContent controls={libraryControls} station={station}/> : <p>{t("Protected library reads are unavailable in this view.")}</p>;
  if (id === 'inspection' || id === 'events') return sessionControls
    ? <SessionContent section={id} controls={sessionControls}/>
    : <p>{t("Protected session reads are unavailable in this view.")}</p>;
  if (id === 'status') return <><div className="app-heading"><span className="status-mark">i</span><div><h2>Vision system report</h2><p>Read-only client · presentation boundary v1</p></div></div><div className="report sunken-panel"><dl><dt>{t("Source")}</dt><dd>{snapshot?.source ?? 'Awaiting adapter'}</dd><dt>Connection</dt><dd>{connectionLabel(snapshot)}</dd><dt>{t("System readiness")}</dt><dd>{snapshot?.readiness ?? 'UNKNOWN'}</dd><dt>Observation time</dt><dd> {snapshot?.observedAt ?? 'Not available'}</dd>{snapshot?.source === 'real' && <><dt>API report time (UTC)</dt><dd>{snapshot.reportTime ?? 'Not available'}</dd></>}</dl></div><p>{snapshot?.reason ?? 'Reading the selected adapter. No system status has been received.'}</p><table className="component-table"><thead><tr><th>Component</th><th>Reported status</th></tr></thead><tbody>{snapshot?.components.map(c => <tr key={c.name}><td>{c.name}</td><td title={c.reason}>? {c.status} <small>— {c.reason}</small></td></tr>)}</tbody></table>{refresh && <p><button onClick={refresh} disabled={snapshot === null}>Refresh API report</button></p>}<p className="fine-print">Opening or closing this desktop never starts or stops Vision.</p>{sessionControls && <SessionContent section="summary" controls={sessionControls}/>}</>;
  if (id === 'control' && station) return <><h2>{t("Workspace preferences")}</h2><fieldset><legend>{t("Local to this browser")}</legend><p>{t("Open modules are remembered locally. No profiles, credentials, inspection sessions or system settings are stored.")}</p><p role="status">{persistence}</p><button onClick={reset}>{t("Reset workspace")}</button></fieldset><fieldset><legend>{t("Vision configuration")}</legend><p>{t("Station configuration requires an agreed backend contract. To change your account password, open Settings.")}</p><button disabled>{t("Station settings")}</button></fieldset></>;
  if (id === 'control') return <><h2>Desktop preferences</h2><fieldset><legend>{t("Local to this browser")}</legend><p>Window positions, sizes and visibility are saved locally. No profiles, credentials, inspection sessions or system settings are stored.</p><p role="status">{persistence}</p><button onClick={reset}>Reset window layout</button></fieldset><fieldset><legend>Vision configuration · unavailable</legend><p>{t("Station configuration requires an agreed backend contract. To change your account password, open Settings.")}</p><button disabled>{t("Station settings")}</button></fieldset><p>Keyboard: Tab to controls; arrow keys on a title bar move its window. Arrow keys on the resize handle change its size. Shift increases the step. Escape closes Start.</p></>;
  const app = placeholders[id];
  return <><div className="placeholder-label">{t("UNAVAILABLE · GUI-01 placeholder")}</div><h2>{t(app.heading)}</h2><div className="sunken-panel empty-table"><table><thead><tr>{app.columns.map(c => <th key={c}>{t(c)}</th>)}</tr></thead></table><p>{t("No data available")}</p></div><p>{t(app.message)}</p><div className="app-actions"><button disabled>{t(app.action)}</button><span>{t("Requires Vision API integration")}</span></div></>;
}
