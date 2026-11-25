import {useEffect,useRef,useState} from 'react';
import type {LibraryEntry,LibrarySectionName} from '../api/libraryContract';
import {librarySections,libraryScopes} from '../api/libraryContract';
import type {StationPresentation} from './client';
import type {DraftReport,DraftValidation} from './draftContract';
import {identifier} from './draftContract';
import {editorSections,hydrateDocument,serializeDocument,referenceOptions,row,array} from './editorFields';
import type {FormDocument} from './editorFields';
import {FieldControl} from './EditorForm';
import {EditorAssets} from './EditorAssets';
import {editDraft,validateDraft,validateDraftStructure} from './transport';
import type {DraftResult} from './transport';

const statuses:Record<string,string>={
  ACCESS_DENIED:'Authentication expired. Sign in again.',
  OPERATOR_REQUIRED:'An explicitly provisioned operator account is required.',
  DRAFT_CONFLICT:'Core rejected this change: stale version, duplicate revision, or non-idle station. Reopen the latest draft before making another change.',
  DRAFT_NOT_FOUND:'The selected draft or catalog record no longer exists.',
  BAD_REQUEST:'The draft or request is invalid. Validate the document in Core and correct the reported fields.',
  RATE_LIMITED:'Request rate limited. Try again later.',
  UNAVAILABLE:'Outcome not confirmed. Do not repeat automatically. Refresh the library and reopen the draft.',
};
type Intent='open'|'create'|'create_empty'|'save'|'clone'|'validate'|'validate_structure';
type EditorEntry=LibraryEntry|'new';
type ValidationTarget={stateId:string;recipeId:string;scope:string};

export function DraftEditorContent({entry,station,onClose,refreshLibrary}:{
  entry:EditorEntry;station:StationPresentation;onClose:()=>void;refreshLibrary:()=>void;
}) {
  const fromCatalog=entry!=='new'&&entry.kind==='CATALOG_RECORD';
  const newProfile=entry==='new'||fromCatalog;
  const [report,setReport]=useState<DraftReport|null>(null);
  const [document,setDocument]=useState<FormDocument|null>(null);
  const [section,setSection]=useState<LibrarySectionName>('metadata');
  const [newKey,setNewKey]=useState(fromCatalog?entry.profileId.slice(0,54)+'-draft':'');
  const [family,setFamily]=useState(entry==='new'?'':entry.family);
  const [variant,setVariant]=useState(entry==='new'?'':entry.variant);
  const [revision,setRevision]=useState('r1');
  const [displayName,setDisplayName]=useState(entry==='new'?'':entry.displayName);
  const [target,setTarget]=useState<ValidationTarget>({stateId:'',recipeId:'',scope:''});
  const [diagnostic,setDiagnostic]=useState<DraftValidation|null>(null);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const [uncertainKey,setUncertainKey]=useState('');
  const [dirty,setDirty]=useState(false);
  const [changedSections,setChangedSections]=useState<LibrarySectionName[]>([]);
  const running=useRef(false);
  const instanceId=station.report.instanceId;
  const editable=station.report.coreConnection==='CONNECTED'&&station.identity.role==='operator'&&!station.accountBusy;
  const idle=station.report.state==='NO_ACTIVE_SESSION';
  const writable=editable&&idle&&!busy&&!uncertain;
  const confirmDiscard=()=>!dirty||window.confirm('Discard unsaved draft changes?');

  useEffect(()=>{
    if(!dirty&&!busy)return;
    const beforeUnload=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};
    window.addEventListener('beforeunload',beforeUnload);
    return()=>window.removeEventListener('beforeunload',beforeUnload);
  },[dirty,busy]);

  function load(next:DraftReport) {
    const hydrated=hydrateDocument(next.document);
    setReport(next);setDocument(hydrated);setDirty(false);setChangedSections([]);setDiagnostic(null);
    setUncertain(false);setUncertainKey('');
    // The document never chooses a workflow or physical state automatically.
    setTarget({stateId:'',recipeId:'',scope:''});
  }
  function changeSection(name:LibrarySectionName,value:unknown) {
    setDocument(old=>old?{...old,[name]:value}:old);
    setDirty(true);setDiagnostic(null);
    setChangedSections(old=>old.includes(name)?old:[...old,name]);
    // Do not let a changed/deleted recipe keep a stale diagnostic.
    setTarget({stateId:'',recipeId:'',scope:''});
  }
  async function execute(action:Intent) {
    if(running.current||!editable)return;
    if(['create','create_empty','save','clone'].includes(action)&&!writable)return;
    if(action==='open'&&!confirmDiscard())return;
    if(action==='clone'&&dirty){setMessage('Save or discard unsaved changes before cloning a revision.');return;}
    let serialized:string|undefined;
    try {
      if(action==='save'||action==='validate'||action==='validate_structure'){
        if(!report||!document)return;
        serialized=serializeDocument(document);
      }
    }catch(error){
      const message=error instanceof Error?error.message:'Incomplete form.';
      setMessage(message);
      const invalid=librarySections.find(k=>message.startsWith(editorSections[k].title+':')||message.startsWith(editorSections[k].title+' /'));
      if(invalid)setSection(invalid);
      return;
    }
    running.current=true;setBusy(true);setMessage('');setDiagnostic(null);
    try {
      if((action==='validate'||action==='validate_structure')&&report&&serialized!==undefined){
        if(action==='validate'&&(!target.stateId||!target.recipeId||!target.scope)){setMessage('Choose a declared state, recipe and scope.');return;}
        const result=action==='validate_structure'?await validateDraftStructure({instanceId,key:report.key},serialized)
          :await validateDraft({instanceId,key:report.key,...target},serialized);
        if(result.status==='AVAILABLE'){setDiagnostic(result.report);setMessage('Core validation complete.');}
        else setMessage(statuses[result.status]);
        return;
      }
      let result:DraftResult<DraftReport>;
      if(action==='open')result=await editDraft('open',{instanceId,key:uncertainKey||report?.key||(newProfile?newKey:entry.profileId)});
      else if(action==='create'&&fromCatalog)result=await editDraft('create',{instanceId,family:entry.family,variant:entry.variant,catalogRevision:entry.revision,key:newKey,revision,displayName});
      else if(action==='create_empty'&&entry==='new')result=await editDraft('create_empty',{instanceId,family,variant,key:newKey,revision,displayName});
      else if(action==='save'&&report&&serialized!==undefined)result=await editDraft('save',{instanceId,key:report.key,etag:report.etag},serialized);
      else if(action==='clone'&&report)result=await editDraft('clone',{instanceId,key:report.key,etag:report.etag,newKey,newRevision:revision});
      else return;
      if(result.status==='AVAILABLE'){
        try{load(result.report);}
        catch{setMessage('Stored document has an unsupported form structure. Reopen it with a compatible editor.');setUncertain(true);setUncertainKey(result.report.key);return;}
        if(action==='open')setMessage('Draft loaded from Core.');
        else{setMessage(action==='clone'?'New draft revision created.':'Draft saved in Core.');refreshLibrary();}
        if(action==='create'||action==='create_empty'||action==='clone'){setNewKey('');setRevision('');}
      }else{
        setMessage(statuses[result.status]);
        if(action!=='open'&&['UNAVAILABLE','DRAFT_CONFLICT','DRAFT_NOT_FOUND'].includes(result.status)){
          setUncertain(true);
          setUncertainKey(action==='create'||action==='create_empty'||action==='clone'?newKey:report?.key??'');
          refreshLibrary();
        }else if(action==='open'&&uncertainKey&&result.status==='DRAFT_NOT_FOUND'){
          setMessage('Requested draft was not published. Confirm the current library before trying again.');
          // Do not automatically retry a mutation. Allow an explicit fresh
          // operation after the authoritative not-found response.
          setUncertain(false);setUncertainKey('');
        }
      }
    }finally{running.current=false;setBusy(false);}
  }
  const states=document?referenceOptions(document,'state'):[];
  const workflows=document?array(row(document.inspection_workflows).recipes).map(row):[];
  const recipes=workflows.filter(w=>w.state_id===target.stateId&&typeof w.recipe_id==='string'&&w.recipe_id!==''&&typeof w.approval_scope==='string');
  const canCreate=identifier(newKey)&&identifier(revision)&&displayName.trim().length>0&&identifier(family)&&identifier(variant);

  return <section className="draft-editor sunken-panel" aria-label="ECU reference editor" data-editor-dirty={dirty?'true':'false'} data-editor-busy={busy?'true':'false'}>
    <div className="editor-heading"><div><h3>ECU reference editor</h3><span>Universal V1 profile forms</span></div>
      <button disabled={busy} onClick={()=>{if(confirmDiscard())onClose();}}>Close editor</button></div>
    <p className="library-not-ready"><strong>DRAFT / NOT_READY</strong> · Reference definitions only. Approval and release are separate.</p>
    {station.report.coreConnection!=='CONNECTED'?<p>Core connection is unavailable. Your unsaved form remains in this tab; editing resumes after reconnection.</p>:!idle&&<p>Core has an active session. Editing is read-only until the session closes.</p>}
    {!report&&(newProfile?<fieldset>
      <legend>{fromCatalog?'Create from catalog — '+entry.family+' / '+entry.variant+' / '+entry.revision:'Create a new unsigned reference profile'}</legend>
      <div className="draft-fields">
        <label htmlFor="draft-family">ECU family</label><input id="draft-family" value={family} maxLength={64} onChange={e=>{setFamily(e.target.value);setDirty(true);}} disabled={!writable||fromCatalog}/>
        <label htmlFor="draft-variant">Variant ID</label><input id="draft-variant" value={variant} maxLength={64} onChange={e=>{setVariant(e.target.value);setDirty(true);}} disabled={!writable||fromCatalog}/>
        <label htmlFor="draft-key">New profile ID</label><input id="draft-key" value={newKey} maxLength={64} onChange={e=>{setNewKey(e.target.value);setDirty(true);}} disabled={!writable}/>
        <label htmlFor="draft-revision">Revision</label><input id="draft-revision" value={revision} maxLength={64} onChange={e=>{setRevision(e.target.value);setDirty(true);}} disabled={!writable}/>
        <label htmlFor="draft-name">Display name</label><input id="draft-name" value={displayName} maxLength={160} onChange={e=>{setDisplayName(e.target.value);setDirty(true);}} disabled={!writable}/>
      </div>
      <p className="fine-print">A new reference is not a registered or approved ECU catalog record. No measurements are prefilled.</p>
      <button className="button-primary" disabled={!writable||!canCreate} onClick={()=>{void execute(fromCatalog?'create':'create_empty');}}>Create draft</button>
      {uncertain&&<button disabled={!editable||busy||!uncertainKey} onClick={()=>{void execute('open');}}>Check requested draft</button>}
    </fieldset>:<p><button disabled={!editable||busy} onClick={()=>{void execute('open');}}>Load draft {entry.profileId}</button></p>)}
    {report&&document&&<>
      <div className="editor-summary"><strong>{String(row(document.metadata).display_name||report.key)}</strong><span>{report.key} · revision {String(row(document.metadata).profile_revision)} · ETag {report.etag.slice(1,13)}…</span><span role="status">{dirty?'Unsaved changes ('+changedSections.length+' sections)':'Saved generation'}</span></div>
      <p className="fine-print">Save complete rows in any order. Sections can remain empty until their measurements are available. An unfinished required field must be completed or its row removed before saving.</p>
      <div className="editor-toolbar">
        <button className="button-primary" disabled={!writable||!dirty} onClick={()=>{void execute('save');}}>Save draft generation</button>
        <button disabled={!editable||busy} onClick={()=>{void execute('validate_structure');}}>Check structure</button>
        <button disabled={!editable||busy} onClick={()=>{void execute('open');}}>{uncertainKey&&uncertainKey!==report.key?'Check requested revision':'Reload latest'}</button>
      </div>
      {message&&<p role="status" className="editor-feedback">{message}</p>}
      <div className="editor-section-nav"><label htmlFor="draft-section">Section</label>
        <select id="draft-section" value={section} onChange={e=>setSection(e.target.value as LibrarySectionName)} disabled={busy}>
          {librarySections.map((key,i)=><option key={key} value={key}>{i+1}. {editorSections[key].title}{changedSections.includes(key)?' *':''}</option>)}
        </select>
        <button disabled={busy||section===librarySections[0]} onClick={()=>setSection(librarySections[librarySections.indexOf(section)-1])}>Previous</button>
        <button disabled={busy||section===librarySections[librarySections.length-1]} onClick={()=>setSection(librarySections[librarySections.indexOf(section)+1])}>Next</button>
      </div>
      <div className="editor-section-layout">
        <nav className="editor-section-list" aria-label="Profile sections">
          {librarySections.map((key,i)=><button key={key} type="button" className={section===key?'editor-section-current':''} aria-current={section===key?'true':undefined} disabled={busy} onClick={()=>setSection(key)}>{String(i+1).padStart(2,'0')}. {editorSections[key].title}{changedSections.includes(key)?' *':''}</button>)}
        </nav>
        <div className="editor-section-form" key={section}>
          <h3>{editorSections[section].title}</h3><p className="fine-print">{editorSections[section].description}</p>
          {section==='reference_assets'&&<EditorAssets key={report.key+':'+report.etag} report={report} document={document}
            disabled={!writable} readable={editable&&!busy} onBusy={value=>{running.current=value;setBusy(value);}}
            onConflict={()=>{setUncertain(true);setUncertainKey(report.key);refreshLibrary();}}
            onAttach={asset=>{
              setDocument(old=>old?{...old,
                reference_assets:{...row(old.reference_assets),assets:[...array(row(old.reference_assets).assets),asset]},
                provenance_release:{...row(old.provenance_release),asset_hashes:[...array(row(old.provenance_release).asset_hashes),{asset_id:asset.asset_id,sha256:asset.sha256}]}
              }:old);
              setDirty(true);setDiagnostic(null);setChangedSections(old=>[...new Set<LibrarySectionName>([...old,'reference_assets','provenance_release'])]);
              setTarget({stateId:'',recipeId:'',scope:''});
            }}/>}
          <FieldControl field={editorSections[section].field} value={document[section]} onChange={v=>changeSection(section,v)} doc={document} disabled={!writable}/>
        </div>
      </div>
      {diagnostic&&<div className="draft-diagnostic" role="status">
        <strong>{diagnostic.valid?'Valid structure · NOT_READY':'INVALID_DOCUMENT'}</strong>
        {diagnostic.errors.length>0&&<ul>{diagnostic.errors.map((x,i)=><li key={i}>{x}</li>)}</ul>}
        {diagnostic.blockers.length>0&&<ul>{diagnostic.blockers.map((x,i)=><li key={i}>{x}</li>)}</ul>}
        <p className="fine-print">Diagnostic only: no approval, verified assets or physical readiness asserted.</p>
      </div>}
      <details className="editor-diagnostics">
        <summary>Core validation — selected inspection scope</summary>
        <p className="fine-print">Choose an existing physical state and workflow. Core validates the entire document. Structural validity does not mean readiness.</p>
        <div className="draft-fields">
          <label htmlFor="draft-state">Physical state</label><select id="draft-state" value={target.stateId} disabled={busy} onChange={e=>{setTarget({stateId:e.target.value,recipeId:'',scope:''});setDiagnostic(null);}}><option value="">Select state…</option>{states.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}</select>
          <label htmlFor="draft-recipe">Inspection recipe</label><select id="draft-recipe" value={target.recipeId} disabled={busy||!target.stateId} onChange={e=>{const found=recipes.find(r=>r.recipe_id===e.target.value);setTarget({...target,recipeId:e.target.value,scope:found?String(found.approval_scope):''});setDiagnostic(null);}}><option value="">Select recipe…</option>{recipes.map((r,i)=><option key={i} value={String(r.recipe_id)}>{String(r.recipe_id)}</option>)}</select>
          <label htmlFor="draft-scope">Requested scope</label><output id="draft-scope">{target.scope&&libraryScopes.some(x=>x===target.scope)?target.scope:'Not selected'}</output>
        </div>
        <button disabled={!editable||busy||!target.stateId||!target.recipeId||!target.scope} onClick={()=>{void execute('validate');}}>Validate document</button>
      </details>
      <details className="editor-diagnostics"><summary>Clone saved draft to a new revision</summary><div className="draft-fields">
        <label htmlFor="draft-clone-key">New profile ID</label><input id="draft-clone-key" value={newKey} maxLength={64} onChange={e=>setNewKey(e.target.value)} disabled={!writable}/>
        <label htmlFor="draft-clone-revision">New revision</label><input id="draft-clone-revision" value={revision} maxLength={64} onChange={e=>setRevision(e.target.value)} disabled={!writable}/>
      </div><button disabled={!writable||dirty||!identifier(newKey)||!identifier(revision)} onClick={()=>{void execute('clone');}}>Clone saved revision</button></details>
    </>}
    {!report&&message&&<p role="status" className="editor-feedback">{message}</p>}
  </section>;
}
