import { useTranslation } from '../i18n/LanguageProvider';
import { useState } from 'react';
import { Button, FluentProvider, webLightTheme, TabList, Tab, Table, TableHeader, TableHeaderCell, TableBody, TableRow, TableCell, Badge } from '@fluentui/react-components';
import { AddRegular, ArrowClockwiseRegular, EditRegular } from '@fluentui/react-icons';
import '../fluent/bridge.css';
import type { LibraryControls, LibraryView } from '../api/useLibraryView';
import type { LibraryDetail, LibrarySectionName, LibraryEntry } from '../api/libraryContract';
import type {StationPresentation} from '../station/client';
import {DraftEditorContent} from '../station/DraftEditorContent';

const labels: Record<LibrarySectionName, string> = {
  metadata: 'Profile metadata', identity: 'Declared identity', physical_states: 'Physical states',
  coordinate_systems: 'Coordinate systems', geometry: 'Geometry', connectors_landmarks: 'Connectors & landmarks',
  reference_assets: 'Reference assets', recognition_rules: 'Identity verification rules', localization_rules: 'Localization rules',
  pcb_definition: 'PCB definition', photography_recipes: 'Photography recipes', thermal_recipes: 'Thermal recipes',
  inspection_workflows: 'Inspection workflows', validation_policies: 'Validation policies', provenance_release: 'Provenance & release',
};
const messages: Record<LibraryView['status'], string> = {
  NOT_REQUESTED: 'No protected library report requested. Refresh to browse the catalog and reference drafts.',
  LOADING: 'Reading a consistent library view…', AVAILABLE: '',
  ACCESS_DENIED: 'Access denied. Library access requires a server-side library grant.',
  UNAVAILABLE: 'Library report unavailable or changed. Refresh to request a new consistent view.',
  DISABLED: 'Library reads are disabled in this client mode.',
};

function Overview({detail}: {detail: LibraryDetail}) {
  const {t}=useTranslation();
  if (detail.catalog) return <>
    <p className="library-not-ready"><strong>{t("NOT_READY · Catalog record only.")}</strong>{" "+t("This is not an approved reference profile.")}</p>
    <div className="library-detail-scroll sunken-panel">
      <Table aria-label={t("Catalog connectors")}><TableHeader><TableRow><TableHeaderCell>{t("Connector")}</TableHeaderCell><TableHeaderCell>{t("Reported color")}</TableHeaderCell></TableRow></TableHeader><TableBody>{detail.catalog.connectors.map(connector => <TableRow key={connector.id}><TableCell>{connector.id}</TableCell><TableCell>{connector.color}</TableCell></TableRow>)}</TableBody></Table>
      <p>{detail.catalog.connectors.length === 0 ? t("No connector records.")+" " : ""}{t("{count} field notes · unverified. Envelope record: {envelope}.",{count:detail.catalog.fieldNoteCount,envelope:t(detail.catalog.envelopePresent?"present":"absent")})}</p>
    </div>
  </>;
  if (!detail.profile) return null;
  return <>
    <p className="library-not-ready"><strong>{t("NOT_READY · Unsigned draft.")}</strong>{" "+t("Operational readiness has not been evaluated.")}</p>
    <div className="library-detail-scroll sunken-panel">
      <h3>{t("Physical states ({count})",{count:detail.profile.physicalStates.length})}</h3>
      {detail.profile.physicalStates.length ? <Table aria-label={t("Draft physical states")}><TableHeader><TableRow><TableHeaderCell>{t("State")}</TableHeaderCell><TableHeaderCell>{t("Name")}</TableHeaderCell><TableHeaderCell>{t("Verified declaration in draft")}</TableHeaderCell></TableRow></TableHeader><TableBody>{detail.profile.physicalStates.map(state => <TableRow key={state.id}><TableCell>{state.id}</TableCell><TableCell>{state.displayName}</TableCell><TableCell>{state.declaredVerified ? t("Yes · not an approval") : t("No")}</TableCell></TableRow>)}</TableBody></Table> : <p>{t("No physical states declared.")}</p>}
      <h3>{t("Inspection workflows ({count})",{count:detail.profile.workflows.length})}</h3>
      {detail.profile.workflows.length ? <Table aria-label={t("Draft inspection workflows")}><TableHeader><TableRow><TableHeaderCell>{t("Recipe")}</TableHeaderCell><TableHeaderCell>{t("State")}</TableHeaderCell><TableHeaderCell>{t("Scope")}</TableHeaderCell></TableRow></TableHeader><TableBody>{detail.profile.workflows.map(workflow => <TableRow key={workflow.id}><TableCell>{workflow.id}</TableCell><TableCell>{workflow.stateId}</TableCell><TableCell>{workflow.scope}</TableCell></TableRow>)}</TableBody></Table> : <p>{t("No inspection workflows declared.")}</p>}
    </div>
  </>;
}

type DetailTab = 'overview' | 'sections' | 'history';
function Detail({controls, tab, setTab}: {controls: LibraryControls; tab: DetailTab; setTab: (tab: DetailTab) => void}) {
  const {t}=useTranslation();
  const {detail, history} = controls.view;
  if (!detail) return null;
  return <section className="library-detail" aria-label={t("Library entry details")}>
    <div className="library-detail-title"><h3>{detail.entry.displayName}</h3><strong>{detail.entry.status}</strong></div>
    <p className="library-detail-key">{detail.entry.profileId} · {detail.entry.family} / {detail.entry.variant} · {t("revision")} {detail.entry.revision}</p>
    <TabList className="library-tabs" aria-label={t("Reference information")} selectedValue={tab} onTabSelect={(_,data)=>setTab(data.value as DetailTab)}>
      <Tab value="overview" id="library-tab-overview" aria-controls="library-panel">{t("Overview")}</Tab>
      {detail.profile && <><Tab value="sections" id="library-tab-sections" aria-controls="library-panel">{t("15 sections")}</Tab><Tab value="history" id="library-tab-history" aria-controls="library-panel">{t("Revision history ({count})",{count:detail.profile.historyCount})}</Tab></>}
    </TabList>
    <div id="library-panel" role="tabpanel" aria-labelledby={`library-tab-${tab}`}>
      {tab === 'overview' && <Overview detail={detail}/>}
      {tab === 'sections' && detail.profile && <><p className="fine-print">{t("Structural row counts only. Every section is NOT_EVALUATED; counts do not indicate completeness or approval.")}</p><div className="library-detail-scroll sunken-panel"><Table aria-label={t("Reference profile sections")}><TableHeader><TableRow><TableHeaderCell>{t("Section")}</TableHeaderCell><TableHeaderCell>{t("Rows")}</TableHeaderCell><TableHeaderCell>{t("Evaluation")}</TableHeaderCell></TableRow></TableHeader><TableBody>{detail.profile.sections.map((section, i) => <TableRow key={section.name}><TableCell>{String(i + 1).padStart(2, '0')} · {t(labels[section.name])}</TableCell><TableCell>{section.rowCount ?? '—'}</TableCell><TableCell>{section.status}</TableCell></TableRow>)}</TableBody></Table></div></>}
      {tab === 'history' && history && <><p className="fine-print">{t("Saved draft generations, oldest first. Revision labels and ETags come from Vision.")}</p><div className="library-detail-scroll sunken-panel"><Table aria-label={t("Reference revision history")}><TableHeader><TableRow><TableHeaderCell>{t("Generation")}</TableHeaderCell><TableHeaderCell>{t("Revision")}</TableHeaderCell><TableHeaderCell>{t("Snapshot / ETag")}</TableHeaderCell></TableRow></TableHeader><TableBody>{history.items.map((item, i) => <TableRow key={item.snapshotId}><TableCell>{history.after + i + 1}{item.etag === history.etag ? t(" · current") : ''}</TableCell><TableCell>{item.revision}</TableCell><TableCell><code>{item.snapshotId}</code><br/><code>{item.etag}</code></TableCell></TableRow>)}</TableBody></Table></div><div className="library-pagination"><span>{t("{first}–{last} of {total} generations",{first:history.after+1,last:history.after+history.items.length,total:history.totalCount})}</span><Button onClick={() => controls.historyPage('previous')} disabled={history.after === 0 || controls.view.refreshing}>{t("Previous history page")}</Button><Button onClick={() => controls.historyPage('next')} disabled={history.nextAfter === null || controls.view.refreshing}>{t("Next history page")}</Button></div></>}
    </div>
  </section>;
}

export function LibraryContent({controls,station}: {controls: LibraryControls; station?: StationPresentation}) {
  const {t}=useTranslation();
  const [editorEntry,setEditorEntry] = useState<LibraryEntry|"new"|null>(null);
  const [tab, setTab] = useState<DetailTab>('overview');
  const {view, refreshLibrary, browseEntry, libraryPage} = controls;
  const {library, detail} = view;
  const editorAvailable = station?.identity.role === "operator" && station.report.coreConnection === "CONNECTED" && !station.accountBusy && view.status === "AVAILABLE";
  return <FluentProvider theme={webLightTheme} className="library-content">
    <div className="library-heading"><div><h2>{t("ECU Library")}</h2><span>{t("Catalog records & reference drafts")}</span></div><FluentProvider theme={webLightTheme} className="vision-fluent-scope library-tools"><Button icon={<ArrowClockwiseRegular/>} onClick={refreshLibrary} disabled={view.status === 'LOADING' || view.status === 'DISABLED' || view.refreshing}>{t("Refresh library")}</Button><Button appearance="primary" icon={<AddRegular/>} disabled={!editorAvailable || editorEntry!==null} onClick={()=>setEditorEntry("new")}>{t("New profile")}</Button><Button icon={<EditRegular/>} disabled={!editorAvailable || !detail || editorEntry!==null} onClick={()=>{if(detail)setEditorEntry(detail.entry);}}>{t("Open reference editor")}</Button></FluentProvider></div>
    <p className="fine-print library-purpose">{t("Reference profiles describe ECU types. Browsing does not select an ECU or create a specimen inspection.")}</p>
    {station && station.identity.role === "reader" && <p className="fine-print">{t("Reference editing requires operator permission.")}</p>}
    {editorEntry && station?.identity.role === "operator" && <DraftEditorContent key={editorEntry==="new"?"new":editorEntry.entryId} entry={editorEntry} station={station} onClose={()=>setEditorEntry(null)} refreshLibrary={refreshLibrary}/>}
    {view.status !== 'AVAILABLE' && <p role="status" className="protected-read-status">{t(messages[view.status])}</p>}
    {library && !editorEntry && <>
      {library.source === 'SYNTHETIC_TEST' && <p className="synthetic-label">{t("SYNTHETIC TEST · no station library")}</p>}
      <div className="library-report-meta"><span>{library.libraryId}</span><span>{t("Last report:")+" "}{library.capturedAt}</span></div>
      <div className="library-list sunken-panel"><Table aria-label={t("ECU library entries")}><TableHeader><TableRow><TableHeaderCell>{t("Name / family")}</TableHeaderCell><TableHeaderCell>{t("Variant / revision")}</TableHeaderCell><TableHeaderCell>{t("Record")}</TableHeaderCell><TableHeaderCell>{t("Readiness")}</TableHeaderCell></TableRow></TableHeader><TableBody>{library.entries.map(entry => <TableRow key={entry.entryId} className={detail?.entry.entryId === entry.entryId ? 'library-selected' : ''}><TableCell><Button appearance="transparent" className="library-entry-link" disabled={view.refreshing} aria-label={t("Browse {name} {revision}",{name:entry.displayName,revision:entry.revision})} onClick={() => { setTab('overview'); browseEntry(entry); }}>{entry.displayName}</Button><small>{entry.family}</small></TableCell><TableCell>{entry.variant}<small>{entry.revision}</small></TableCell><TableCell>{entry.kind === 'CATALOG_RECORD' ? t("Catalog") : t("Reference draft")}<small>{entry.status}</small></TableCell><TableCell><Badge appearance="tint" color="informative">{entry.readiness}</Badge></TableCell></TableRow>)}</TableBody></Table>{library.totalCount === 0 && <p className="library-empty">{t("No catalog records or reference drafts are available.")}</p>}</div>
      <div className="library-pagination"><span>{library.totalCount === 0 ? t("0 entries") : t("{first}–{last} of {total} entries",{first:library.after+1,last:library.after+library.entries.length,total:library.totalCount})}</span><Button onClick={() => libraryPage('previous')} disabled={library.after === 0 || view.refreshing}>{t("Previous entries")}</Button><Button onClick={() => libraryPage('next')} disabled={library.nextAfter === null || view.refreshing}>{t("Next entries")}</Button></div>
      {detail ? <Detail controls={controls} tab={tab} setTab={setTab}/> : <p className="library-empty">{t("Browse an entry to inspect its reference information.")}</p>}
      <p className="fine-print">{controls.autoRefresh ? t("Library information refreshes automatically.") : t("Last requested view · no live updates.")}{" "+t("Approval and operational decisions belong to Vision.")}</p>
    </>}
  </FluentProvider>;
}
