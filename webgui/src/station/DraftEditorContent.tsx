import {useRef, useState} from 'react';
import type {LibraryEntry, LibrarySectionName} from '../api/libraryContract';
import {librarySections, libraryScopes} from '../api/libraryContract';
import type {StationPresentation} from './client';
import type {DraftParts, DraftReport, DraftValidation} from './draftContract';
import {draftParts, draftText} from './draftContract';
import {editDraft, validateDraft} from './transport';
import type {DraftResult} from './transport';

const sectionLabels: Record<LibrarySectionName,string> = {
  metadata:'Profile metadata', identity:'Declared identity', physical_states:'Physical states',
  coordinate_systems:'Coordinate systems', geometry:'Geometry', connectors_landmarks:'Connectors & landmarks',
  reference_assets:'Reference assets', recognition_rules:'Identity verification rules', localization_rules:'Localization rules',
  pcb_definition:'PCB definition', photography_recipes:'Photography recipes', thermal_recipes:'Thermal recipes',
  inspection_workflows:'Inspection workflows', validation_policies:'Validation policies', provenance_release:'Provenance & release',
};
const statuses: Record<string,string> = {
  ACCESS_DENIED:'Authentication expired. Sign in again.',
  OPERATOR_REQUIRED:'An explicitly provisioned operator account is required.',
  DRAFT_CONFLICT:'Core rejected this change: stale version, duplicate revision, or non-idle station. Reopen the latest draft before making another change.',
  DRAFT_NOT_FOUND:'The selected draft or catalog record no longer exists.',
  BAD_REQUEST:'The draft or request is invalid. Check the document and validate it in Core.',
  RATE_LIMITED:'Request rate limited. Try again later.',
  UNAVAILABLE:'Outcome not confirmed. Do not repeat automatically. Refresh the library and reopen the draft.',
};

export function DraftEditorContent({entry,station,onClose,refreshLibrary}: {
  entry:LibraryEntry; station:StationPresentation; onClose:()=>void; refreshLibrary:()=>void;
}) {
  const [report,setReport] = useState<DraftReport|null>(null);
  const [parts,setParts] = useState<DraftParts|null>(null);
  const [section,setSection] = useState<LibrarySectionName>('metadata');
  const [newKey,setNewKey] = useState(entry.kind==='CATALOG_RECORD' ? entry.profileId.slice(0,54)+'-draft' : '');
  const [revision,setRevision] = useState('r1');
  const [displayName,setDisplayName] = useState(entry.displayName);
  const [stateId,setStateId] = useState('pcb_exposed_top');
  const [recipeId,setRecipeId] = useState('photo');
  const [scope,setScope] = useState('photo_inspection');
  const [diagnostic,setDiagnostic] = useState<DraftValidation|null>(null);
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  const [uncertain,setUncertain] = useState(false);
  const [dirty,setDirty] = useState(false);
  const running = useRef(false);
  const instanceId = station.report.instanceId;
  const editable = station.report.coreConnection==='CONNECTED' && station.identity.role==='operator' && !station.accountBusy;
  const idle = station.report.state==='NO_ACTIVE_SESSION';
  const writable = editable && idle && !busy && !uncertain;
  const confirmDiscard = () => !dirty || window.confirm('Discard unsaved draft changes?');

  function load(next: DraftReport) {
    setReport(next); setParts(draftParts(next.document)); setDirty(false);
    setDiagnostic(null); setUncertain(false);
  }
  function changePart(name:LibrarySectionName,text:string) {
    setParts(old => old ? {...old,[name]:text} : old);
    setDirty(true); setDiagnostic(null);
  }
  async function execute(action:'open'|'create'|'save'|'clone'|'validate') {
    if (running.current || !editable) return;
    if (['create','save','clone'].includes(action) && !writable) return;
    if (action==='open' && !confirmDiscard()) return;
    if (action==='clone' && dirty) {setMessage('Save or discard unsaved changes before cloning a revision.'); return;}
    let document:string|undefined;
    try {
      if (action==='save' || action==='validate') {
        if (!report || !parts) return;
        document=draftText(parts);
      }
    } catch (error) {setMessage(error instanceof Error ? error.message : 'Invalid JSON'); return;}
    running.current=true; setBusy(true); setMessage(''); setDiagnostic(null);
    try {
      if (action==='validate' && report && document!==undefined) {
        const result=await validateDraft({instanceId,key:report.key,stateId,recipeId,scope},document);
        if (result.status==='AVAILABLE') {setDiagnostic(result.report); setMessage('Core validation complete.');}
        else setMessage(statuses[result.status]);
        return;
      }
      let result:DraftResult<DraftReport>;
      if (action==='open') result=await editDraft('open',{instanceId,key:report?.key ?? (entry.kind==='CATALOG_RECORD' ? newKey : entry.profileId)});
      else if (action==='create') result=await editDraft('create',{instanceId,family:entry.family,variant:entry.variant,catalogRevision:entry.revision,key:newKey,revision,displayName});
      else if (action==='save' && report && document!==undefined) result=await editDraft('save',{instanceId,key:report.key,etag:report.etag},document);
      else if (action==='clone' && report) result=await editDraft('clone',{instanceId,key:report.key,etag:report.etag,newKey,newRevision:revision});
      else return;
      if (result.status==='AVAILABLE') {
        load(result.report);
        if (action==='open') setMessage('Draft loaded from Core.');
        else {setMessage(action==='clone'?'New draft revision created.':'Draft saved in Core.'); refreshLibrary();}
        if (action==='create'||action==='clone') {setNewKey('');setRevision('');}
      } else {
        setMessage(statuses[result.status]);
        if (action!=='open' && ['UNAVAILABLE','DRAFT_CONFLICT','DRAFT_NOT_FOUND'].includes(result.status)) {setUncertain(true);refreshLibrary();}
      }
    } finally {running.current=false;setBusy(false);}
  }

  return <section className="draft-editor sunken-panel" aria-label="ECU reference editor">
    <div className="library-detail-title"><h3>ECU reference editor</h3><button disabled={busy} onClick={()=>{if(confirmDiscard())onClose();}}>Close editor</button></div>
    <p className="library-not-ready"><strong>DRAFT / NOT_READY</strong> · Reference definitions only, not a specimen inspection. Approval and release are separate.</p>
    {!idle && <p>Core has an active session. Editing is read-only until the session closes.</p>}
    {!report && (entry.kind==='CATALOG_RECORD' ? <fieldset>
      <legend>Create from catalog — {entry.family} / {entry.variant} / {entry.revision}</legend>
      <div className="draft-fields">
        <label htmlFor="draft-key">New profile ID</label><input id="draft-key" value={newKey} maxLength={64} onChange={e=>setNewKey(e.target.value)} disabled={busy}/>
        <label htmlFor="draft-revision">Revision</label><input id="draft-revision" value={revision} maxLength={64} onChange={e=>setRevision(e.target.value)} disabled={busy}/>
        <label htmlFor="draft-name">Display name</label><input id="draft-name" value={displayName} maxLength={160} onChange={e=>setDisplayName(e.target.value)} disabled={busy}/>
      </div>
      <button disabled={!writable||!newKey||!revision||!displayName} onClick={()=>{void execute('create');}}>Create draft</button>
      {uncertain&&<button disabled={!editable||busy||!newKey} onClick={()=>{void execute('open');}}>Check requested draft</button>}
    </fieldset> : <p><button disabled={!editable||busy} onClick={()=>{void execute('open');}}>Load draft {entry.profileId}</button></p>)}
    {report && parts && <>
      <p className="library-detail-key"><strong>{report.key}</strong> · ETag {report.etag.slice(1,13)}… {dirty?'· Unsaved changes':''}</p>
      <div className="draft-tools">
        <label htmlFor="draft-section">Section</label>
        <select id="draft-section" value={section} onChange={e=>setSection(e.target.value as LibrarySectionName)} disabled={busy}>
          {librarySections.map((key,i)=><option key={key} value={key}>{i+1}. {sectionLabels[key]}</option>)}
        </select>
        <button disabled={!editable||busy} onClick={()=>{void execute('open');}}>Reload latest</button>
      </div>
      <p className="fine-print">Technical section editor. Enter JSON values using the V1 schema; Core checks cross-references and field types. No draft is persisted in browser storage.</p>
      <label htmlFor="draft-json">{sectionLabels[section]} (JSON)</label>
      <textarea id="draft-json" spellCheck={false} value={parts[section]} onChange={e=>changePart(section,e.target.value)} readOnly={!writable} rows={11}/>
      <p><button disabled={!writable||!dirty} onClick={()=>{void execute('save');}}>Save draft generation</button></p>
      <fieldset><legend>Validate unsaved or saved document in Core</legend>
        <div className="draft-fields">
          <label htmlFor="draft-state">Physical state ID</label><input id="draft-state" value={stateId} maxLength={64} onChange={e=>{setStateId(e.target.value);setDiagnostic(null);}} disabled={busy}/>
          <label htmlFor="draft-recipe">Recipe ID</label><input id="draft-recipe" value={recipeId} maxLength={64} onChange={e=>{setRecipeId(e.target.value);setDiagnostic(null);}} disabled={busy}/>
          <label htmlFor="draft-scope">Scope</label><select id="draft-scope" value={scope} onChange={e=>{setScope(e.target.value);setDiagnostic(null);}} disabled={busy}>{libraryScopes.map(x=><option key={x}>{x}</option>)}</select>
        </div>
        <button disabled={!editable||busy||!stateId||!recipeId} onClick={()=>{void execute('validate');}}>Validate document</button>
        {diagnostic && <div className="draft-diagnostic" role="status">
          <strong>{diagnostic.valid?'Valid structure · NOT_READY':'INVALID_DOCUMENT'}</strong>
          {diagnostic.errors.length>0&&<ul>{diagnostic.errors.map((x,i)=><li key={i}>{x}</li>)}</ul>}
          {diagnostic.blockers.length>0&&<ul>{diagnostic.blockers.map((x,i)=><li key={i}>{x}</li>)}</ul>}
          <p className="fine-print">Diagnostic only: no approval, verified assets or physical readiness asserted.</p>
        </div>}
      </fieldset>
      <fieldset><legend>Clone saved draft to a new revision</legend>
        <div className="draft-fields">
          <label htmlFor="draft-clone-key">New profile ID</label><input id="draft-clone-key" value={newKey} maxLength={64} onChange={e=>setNewKey(e.target.value)} disabled={busy}/>
          <label htmlFor="draft-clone-revision">New revision</label><input id="draft-clone-revision" value={revision} maxLength={64} onChange={e=>setRevision(e.target.value)} disabled={busy}/>
        </div>
        <button disabled={!writable||dirty||!newKey||!revision} onClick={()=>{void execute('clone');}}>Clone saved revision</button>
      </fieldset>
    </>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
