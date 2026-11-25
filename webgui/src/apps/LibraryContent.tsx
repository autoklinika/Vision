import { useState } from 'react';
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
  if (detail.catalog) return <>
    <p className="library-not-ready"><strong>NOT_READY · Catalog record only.</strong> This is not an approved reference profile.</p>
    <div className="library-detail-scroll sunken-panel">
      <table aria-label="Catalog connectors"><thead><tr><th>Connector</th><th>Reported color</th></tr></thead><tbody>{detail.catalog.connectors.map(connector => <tr key={connector.id}><td>{connector.id}</td><td>{connector.color}</td></tr>)}</tbody></table>
      <p>{detail.catalog.connectors.length === 0 ? 'No connector records. ' : ''}{detail.catalog.fieldNoteCount} field notes · unverified. Envelope record: {detail.catalog.envelopePresent ? 'present' : 'absent'}.</p>
    </div>
  </>;
  if (!detail.profile) return null;
  return <>
    <p className="library-not-ready"><strong>NOT_READY · Unsigned draft.</strong> Operational readiness has not been evaluated.</p>
    <div className="library-detail-scroll sunken-panel">
      <h3>Physical states ({detail.profile.physicalStates.length})</h3>
      {detail.profile.physicalStates.length ? <table aria-label="Draft physical states"><thead><tr><th>State</th><th>Name</th><th>Verified declaration in draft</th></tr></thead><tbody>{detail.profile.physicalStates.map(state => <tr key={state.id}><td>{state.id}</td><td>{state.displayName}</td><td>{state.declaredVerified ? 'Yes · not an approval' : 'No'}</td></tr>)}</tbody></table> : <p>No physical states declared.</p>}
      <h3>Inspection workflows ({detail.profile.workflows.length})</h3>
      {detail.profile.workflows.length ? <table aria-label="Draft inspection workflows"><thead><tr><th>Recipe</th><th>State</th><th>Scope</th></tr></thead><tbody>{detail.profile.workflows.map(workflow => <tr key={workflow.id}><td>{workflow.id}</td><td>{workflow.stateId}</td><td>{workflow.scope}</td></tr>)}</tbody></table> : <p>No inspection workflows declared.</p>}
    </div>
  </>;
}

type DetailTab = 'overview' | 'sections' | 'history';
function Detail({controls, tab, setTab}: {controls: LibraryControls; tab: DetailTab; setTab: (tab: DetailTab) => void}) {
  const {detail, history} = controls.view;
  if (!detail) return null;
  return <section className="library-detail" aria-label="Library entry details">
    <div className="library-detail-title"><h3>{detail.entry.displayName}</h3><strong>{detail.entry.status}</strong></div>
    <p className="library-detail-key">{detail.entry.profileId} · {detail.entry.family} / {detail.entry.variant} · revision {detail.entry.revision}</p>
    <div className="library-tabs" role="tablist" aria-label="Reference information" onKeyDown={event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
      const current = tabs.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next]?.focus(); tabs[next]?.click();
    }}>
      <button role="tab" id="library-tab-overview" tabIndex={tab === 'overview' ? 0 : -1} aria-selected={tab === 'overview'} aria-controls="library-panel" onClick={() => setTab('overview')}>Overview</button>
      {detail.profile && <><button role="tab" id="library-tab-sections" tabIndex={tab === 'sections' ? 0 : -1} aria-selected={tab === 'sections'} aria-controls="library-panel" onClick={() => setTab('sections')}>15 sections</button><button role="tab" id="library-tab-history" tabIndex={tab === 'history' ? 0 : -1} aria-selected={tab === 'history'} aria-controls="library-panel" onClick={() => setTab('history')}>Revision history ({detail.profile.historyCount})</button></>}
    </div>
    <div id="library-panel" role="tabpanel" aria-labelledby={`library-tab-${tab}`}>
      {tab === 'overview' && <Overview detail={detail}/>}
      {tab === 'sections' && detail.profile && <><p className="fine-print">Structural row counts only. Every section is NOT_EVALUATED; counts do not indicate completeness or approval.</p><div className="library-detail-scroll sunken-panel"><table aria-label="Reference profile sections"><thead><tr><th>Section</th><th>Rows</th><th>Evaluation</th></tr></thead><tbody>{detail.profile.sections.map((section, i) => <tr key={section.name}><td>{String(i + 1).padStart(2, '0')} · {labels[section.name]}</td><td>{section.rowCount ?? '—'}</td><td>{section.status}</td></tr>)}</tbody></table></div></>}
      {tab === 'history' && history && <><p className="fine-print">Saved draft generations, oldest first. Revision labels and ETags come from Vision.</p><div className="library-detail-scroll sunken-panel"><table aria-label="Reference revision history"><thead><tr><th>Generation</th><th>Revision</th><th>Snapshot / ETag</th></tr></thead><tbody>{history.items.map((item, i) => <tr key={item.snapshotId}><td>{history.after + i + 1}{item.etag === history.etag ? ' · current' : ''}</td><td>{item.revision}</td><td><code>{item.snapshotId}</code><br/><code>{item.etag}</code></td></tr>)}</tbody></table></div><div className="library-pagination"><span>{history.after + 1}–{history.after + history.items.length} of {history.totalCount} generations</span><button onClick={() => controls.historyPage('previous')} disabled={history.after === 0 || controls.view.refreshing}>Previous history page</button><button onClick={() => controls.historyPage('next')} disabled={history.nextAfter === null || controls.view.refreshing}>Next history page</button></div></>}
    </div>
  </section>;
}

export function LibraryContent({controls,station}: {controls: LibraryControls; station?: StationPresentation}) {
  const [editorEntry,setEditorEntry] = useState<LibraryEntry|"new"|null>(null);
  const [tab, setTab] = useState<DetailTab>('overview');
  const {view, refreshLibrary, browseEntry, libraryPage} = controls;
  const {library, detail} = view;
  const editorAvailable = station?.identity.role === "operator" && station.report.coreConnection === "CONNECTED" && !station.accountBusy && view.status === "AVAILABLE";
  return <div className="library-content">
    <div className="library-heading"><div><h2>ECU Library</h2><span>Catalog records & reference drafts</span></div><div className="library-tools"><button onClick={refreshLibrary} disabled={view.status === 'LOADING' || view.status === 'DISABLED' || view.refreshing}>Refresh library</button><button disabled={!editorAvailable || editorEntry!==null} onClick={()=>setEditorEntry("new")}>New profile</button><button disabled={!editorAvailable || !detail || editorEntry!==null} onClick={()=>{if(detail)setEditorEntry(detail.entry);}}>Open reference editor</button></div></div>
    <p className="fine-print library-purpose">Reference profiles describe ECU types. Browsing does not select an ECU or create a specimen inspection.</p>
    {station && station.identity.role === "reader" && <p className="fine-print">Reference editing requires operator permission.</p>}
    {editorEntry && station?.identity.role === "operator" && station.report.coreConnection === "CONNECTED" && <DraftEditorContent key={station.report.instanceId+":"+(editorEntry==="new"?"new":editorEntry.entryId)} entry={editorEntry} station={station} onClose={()=>setEditorEntry(null)} refreshLibrary={refreshLibrary}/>}
    {view.status !== 'AVAILABLE' && <p role="status" className="protected-read-status">{messages[view.status]}</p>}
    {library && !editorEntry && <>
      {library.source === 'SYNTHETIC_TEST' && <p className="synthetic-label">SYNTHETIC TEST · no station library</p>}
      <div className="library-report-meta"><span>{library.libraryId}</span><span>Last report: {library.capturedAt}</span></div>
      <div className="library-list sunken-panel"><table aria-label="ECU library entries"><thead><tr><th>Name / family</th><th>Variant / revision</th><th>Record</th><th>Readiness</th></tr></thead><tbody>{library.entries.map(entry => <tr key={entry.entryId} className={detail?.entry.entryId === entry.entryId ? 'library-selected' : ''}><td><button className="library-entry-link" disabled={view.refreshing} aria-label={`Browse ${entry.displayName} ${entry.revision}`} onClick={() => { setTab('overview'); browseEntry(entry); }}>{entry.displayName}</button><small>{entry.family}</small></td><td>{entry.variant}<small>{entry.revision}</small></td><td>{entry.kind === 'CATALOG_RECORD' ? 'Catalog' : 'Reference draft'}<small>{entry.status}</small></td><td>{entry.readiness}</td></tr>)}</tbody></table>{library.totalCount === 0 && <p className="library-empty">No catalog records or reference drafts are available.</p>}</div>
      <div className="library-pagination"><span>{library.totalCount === 0 ? '0 entries' : `${library.after + 1}–${library.after + library.entries.length} of ${library.totalCount} entries`}</span><button onClick={() => libraryPage('previous')} disabled={library.after === 0 || view.refreshing}>Previous entries</button><button onClick={() => libraryPage('next')} disabled={library.nextAfter === null || view.refreshing}>Next entries</button></div>
      {detail ? <Detail controls={controls} tab={tab} setTab={setTab}/> : <p className="library-empty">Browse an entry to inspect its reference information.</p>}
      <p className="fine-print">{controls.autoRefresh ? 'Library information refreshes automatically.' : 'Last requested view · no live updates.'} Approval and operational decisions belong to Vision.</p>
    </>}
  </div>;
}
