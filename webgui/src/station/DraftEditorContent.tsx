import { useTranslation } from '../i18n/LanguageProvider';
import { Button, FluentProvider, Input, Select, Badge, MessageBar, MessageBarBody, MessageBarTitle, webLightTheme } from '@fluentui/react-components';
import { SaveRegular, CheckmarkCircleRegular, ArrowClockwiseRegular, AddRegular } from '@fluentui/react-icons';
import '../fluent/bridge.css';
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
type Intent='open'|'archive'|'restore'|'submit_review'|'withdraw_review'|'create'|'create_empty'|'save'|'clone'|'validate'|'validate_structure';
type EditorEntry=LibraryEntry|'new';
type ValidationTarget={stateId:string;recipeId:string;scope:string};

export function DraftEditorContent({entry,station,onClose,refreshLibrary}:{
  entry:EditorEntry;station:StationPresentation;onClose:()=>void;refreshLibrary:()=>void;
}) {
  const {t}=useTranslation();
  function displayMessage(message: string) {
    const translated=t(message);
    if(translated!==message)return translated;
    const separator=message.lastIndexOf(': ');
    return separator<0?message:message.slice(0,separator+2)+t(message.slice(separator+2));
  }
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
  const [reviewFile,setReviewFile]=useState<File|null>(null);
  const [changedSections,setChangedSections]=useState<LibrarySectionName[]>([]);
  const running=useRef(false);
  const instanceId=station.report.instanceId;
  const editable=station.report.coreConnection==='CONNECTED'&&station.identity.role==='operator'&&!station.accountBusy;
  const idle=station.report.state==='NO_ACTIVE_SESSION';
  const lifecycle=report?.lifecycle??'ACTIVE';
  const canManage=editable&&idle&&!busy&&!uncertain;
  const writable=canManage&&lifecycle==='ACTIVE';
  const confirmDiscard=()=>!dirty||window.confirm(t('Discard unsaved draft changes?'));

  useEffect(()=>{
    if(!dirty&&!busy)return;
    const beforeUnload=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};
    window.addEventListener('beforeunload',beforeUnload);
    return()=>window.removeEventListener('beforeunload',beforeUnload);
  },[dirty,busy]);

  function load(next:DraftReport) {
    const hydrated=hydrateDocument(next.document);
    setReport(next);setDocument(hydrated);setDirty(false);setChangedSections([]);setDiagnostic(null);
    setUncertain(false);setUncertainKey('');setReviewFile(null);
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
    if(['create','create_empty','save'].includes(action)&&!writable)return;
    if(action==='clone'&&!canManage)return;
    const management=['archive','restore','submit_review','withdraw_review'].includes(action);
    if(management&&(!report||!canManage||dirty||!window.confirm(t('Change the saved profile lifecycle? The document and its history will be retained.'))))return;
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
      else if((action==='archive'||action==='restore'||action==='submit_review'||action==='withdraw_review')&&report)
        result=await editDraft(action,{instanceId,key:report.key,etag:report.etag});
      else if(action==='clone'&&report)result=await editDraft('clone',{instanceId,key:report.key,etag:report.etag,newKey,newRevision:revision});
      else return;
      if(result.status==='AVAILABLE'){
        try{load(result.report);}
        catch{setMessage('Stored document has an unsupported form structure. Reopen it with a compatible editor.');setUncertain(true);setUncertainKey(result.report.key);return;}
        if(action==='open')setMessage('Draft loaded from Core.');
        else{setMessage(management?'Profile lifecycle updated.':action==='clone'?'New draft revision created.':'Draft saved in Core.');refreshLibrary();}
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
  function exportReview(){
    if(!report||report.lifecycle!=='REVIEW_READY'||dirty||busy||!editable)return;
    const data=JSON.stringify({schema:'vision.reference-review-request.v1',key:report.key,submittedEtag:report.etag,document:report.document},null,2);
    const url=URL.createObjectURL(new Blob([data],{type:'application/json'}));
    const anchor=window.document.createElement('a');
    anchor.href=url;anchor.download=report.key+'-review-request.json';
    window.document.body.appendChild(anchor);anchor.click();anchor.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function importReview(){
    if(!report||report.lifecycle!=='REVIEW_READY'||!report.reviewAvailable||!reviewFile||!canManage||dirty||running.current)return;
    if(reviewFile.size>131072){setMessage('Invalid or oversized reviewed package.');return;}
    if(!window.confirm(t('Publish independently reviewed release? Core verifies the exact submitted generation and proof.')))return;
    running.current=true;setBusy(true);setMessage('');setDiagnostic(null);
    try{
      let data:unknown;
      try{data=JSON.parse(await reviewFile.text());}catch{setMessage('Invalid or oversized reviewed package.');return;}
      const pkg=row(data);
      if(Object.keys(pkg).sort().join(',')!=='document,key,proof,schema,submittedEtag'||
        pkg.schema!=='vision.reference-reviewed.v1'||pkg.key!==report.key||pkg.submittedEtag!==report.etag||
        typeof pkg.proof!=='string'||pkg.proof.length>5464||typeof pkg.document!=='object'||pkg.document===null){
        setMessage('Invalid or oversized reviewed package.');return;
      }
      const result=await editDraft('publish_review',{instanceId,key:report.key,etag:report.etag,reviewProof:pkg.proof},JSON.stringify(pkg.document));
      if(result.status==='AVAILABLE'){
        load(result.report);setMessage('Independently reviewed reference published.');refreshLibrary();
      }else{
        setMessage(statuses[result.status]);
        if(['UNAVAILABLE','DRAFT_CONFLICT','DRAFT_NOT_FOUND'].includes(result.status)){
          setUncertain(true);setUncertainKey(report.key);refreshLibrary();
        }
      }
    }catch{setMessage('Invalid or oversized reviewed package.');}
    finally{running.current=false;setBusy(false);}
  }
  const states=document?referenceOptions(document,'state'):[];
  const workflows=document?array(row(document.inspection_workflows).recipes).map(row):[];
  const recipes=workflows.filter(w=>w.state_id===target.stateId&&typeof w.recipe_id==='string'&&w.recipe_id!==''&&typeof w.approval_scope==='string');
  const canCreate=identifier(newKey)&&identifier(revision)&&displayName.trim().length>0&&identifier(family)&&identifier(variant);

  return <section className="draft-editor sunken-panel" aria-label={t("ECU reference editor")} data-editor-dirty={dirty?'true':'false'} data-editor-busy={busy?'true':'false'}>
    <div className="editor-heading"><div><h3>{t("ECU reference editor")}</h3><span>{t("Universal V1 profile forms")}</span></div>
      <Button disabled={busy} onClick={()=>{if(confirmDiscard())onClose();}}>{t("Close editor")}</Button></div>
    <MessageBar intent="warning"><MessageBarBody><MessageBarTitle>{lifecycle==='ACTIVE'?t("DRAFT / NOT_READY"):t(lifecycle==='ARCHIVED'?'Archived profile':lifecycle==='REVIEW_READY'?'Submitted for review':'Released reference record')}</MessageBarTitle>{t("Reference definitions only. Approval and release are separate.")}</MessageBarBody></MessageBar>
    {station.report.coreConnection!=='CONNECTED'?<p>{t("Core connection is unavailable. Your unsaved form remains in this tab; editing resumes after reconnection.")}</p>:!idle&&<p>{t("Core has an active session. Editing is read-only until the session closes.")}</p>}
    {!report&&(newProfile?<FluentProvider theme={webLightTheme} className="vision-fluent-scope vision-fluent-form"><fieldset>
      <legend>{fromCatalog?t('Create from catalog — {family} / {variant} / {revision}',{family:entry.family,variant:entry.variant,revision:entry.revision}):t('Create a new unsigned reference profile')}</legend>
      <div className="draft-fields">
        <label htmlFor="draft-family">{t("ECU family")}</label><Input id="draft-family" value={family} maxLength={64} onChange={(_,data)=>{setFamily(data.value);setDirty(true);}} disabled={!writable||fromCatalog}/>
        <label htmlFor="draft-variant">{t("Variant ID")}</label><Input id="draft-variant" value={variant} maxLength={64} onChange={(_,data)=>{setVariant(data.value);setDirty(true);}} disabled={!writable||fromCatalog}/>
        <label htmlFor="draft-key">{t("New profile ID")}</label><Input id="draft-key" value={newKey} maxLength={64} onChange={(_,data)=>{setNewKey(data.value);setDirty(true);}} disabled={!writable}/>
        <label htmlFor="draft-revision">{t("Revision")}</label><Input id="draft-revision" value={revision} maxLength={64} onChange={(_,data)=>{setRevision(data.value);setDirty(true);}} disabled={!writable}/>
        <label htmlFor="draft-name">{t("Display name")}</label><Input id="draft-name" value={displayName} maxLength={160} onChange={(_,data)=>{setDisplayName(data.value);setDirty(true);}} disabled={!writable}/>
      </div>
      <p className="fine-print">{t("A new reference is not a registered or approved ECU catalog record. No measurements are prefilled.")}</p>
      <Button appearance="primary" icon={<AddRegular/>} disabled={!writable||!canCreate} onClick={()=>{void execute(fromCatalog?'create':'create_empty');}}>{t("Create draft")}</Button>
      {uncertain&&<Button disabled={!editable||busy||!uncertainKey} onClick={()=>{void execute('open');}}>{t("Check requested draft")}</Button>}
    </fieldset></FluentProvider>:<p><Button disabled={!editable||busy} onClick={()=>{void execute('open');}}>{t("Load draft {id}",{id:entry.profileId})}</Button></p>)}
    {report&&document&&<>
      <div className="editor-summary"><strong>{String(row(document.metadata).display_name||report.key)}</strong><span>{report.key} · {t("revision")} {String(row(document.metadata).profile_revision)} · ETag {report.etag.slice(1,13)}…</span><span role="status"><Badge appearance="tint" color={dirty?'warning':'informative'}>{dirty?t('Unsaved changes ({count} sections)',{count:changedSections.length}):t('Saved generation')}</Badge></span></div>
      {lifecycle!=='ACTIVE'&&<p className="fine-print">{t("This saved draft is locked. A submitted draft is not an approved release.")}</p>}
      <p className="fine-print">{t("Save complete rows in any order. Sections can remain empty until their measurements are available. An unfinished required field must be completed or its row removed before saving.")}</p>
      <FluentProvider theme={webLightTheme} className="vision-fluent-scope editor-toolbar">
        <Button appearance="primary" icon={<SaveRegular/>} disabled={!writable||!dirty} onClick={()=>{void execute('save');}}>{t("Save draft generation")}</Button>
        <Button icon={<CheckmarkCircleRegular/>} disabled={!editable||busy} onClick={()=>{void execute('validate_structure');}}>{t("Check structure")}</Button>
        <Button icon={<ArrowClockwiseRegular/>} disabled={!editable||busy} onClick={()=>{void execute('open');}}>{uncertainKey&&uncertainKey!==report.key?t("Check requested revision"):t("Reload latest")}</Button>
        {lifecycle==='ACTIVE'&&<>
          <Button disabled={!canManage||dirty} onClick={()=>{void execute('archive');}}>{t("Archive profile")}</Button>
          <Button disabled={!canManage||dirty||workflows.length===0} onClick={()=>{void execute('submit_review');}}>{t("Submit for review")}</Button>
        </>}
        {lifecycle==='ARCHIVED'&&<Button disabled={!canManage} onClick={()=>{void execute('restore');}}>{t("Restore profile")}</Button>}
        {lifecycle==='REVIEW_READY'&&<Button disabled={!canManage} onClick={()=>{void execute('withdraw_review');}}>{t("Withdraw from review")}</Button>}
      </FluentProvider>
      {lifecycle==='REVIEW_READY'&&<section className="editor-review-panel" aria-label={t("Independent review")}>
        <h3>{t("Independent review")}</h3>
        <Button disabled={!editable||busy} onClick={exportReview}>{t("Export review request")}</Button>
        {report.reviewAvailable?<div className="library-review-controls"><label htmlFor="review-package">{t("Reviewed release package")}</label>
          <input id="review-package" type="file" accept=".json,application/json" disabled={!canManage} onChange={event=>setReviewFile(event.target.files?.[0]??null)}/>
          <Button appearance="primary" disabled={!canManage||!reviewFile} onClick={()=>{void importReview();}}>{t("Publish reviewed release")}</Button>
        </div>:<p className="fine-print">{t("Independent review authority is not configured on this Core. Export is available; publication is disabled.")}</p>}
      </section>}
      {lifecycle==='RELEASED'&&report.releaseDigest&&<p className="library-detail-key">{t("Release digest")}: <code>{report.releaseDigest}</code></p>}
      {message&&<p role="status" className="editor-feedback">{displayMessage(message)}</p>}
      <div className="editor-section-nav"><label htmlFor="draft-section">{t("Section")}</label>
        <Select id="draft-section" value={section} onChange={e=>setSection(e.target.value as LibrarySectionName)} disabled={busy}>
          {librarySections.map((key,i)=><option key={key} value={key}>{i+1}. {t(editorSections[key].title)}{changedSections.includes(key)?' *':''}</option>)}
        </Select>
        <Button disabled={busy||section===librarySections[0]} onClick={()=>setSection(librarySections[librarySections.indexOf(section)-1])}>{t("Previous")}</Button>
        <Button disabled={busy||section===librarySections[librarySections.length-1]} onClick={()=>setSection(librarySections[librarySections.indexOf(section)+1])}>{t("Next")}</Button>
      </div>
      <div className="editor-section-layout">
        <nav className="editor-section-list" aria-label={t("Profile sections")}>
          {librarySections.map((key,i)=><Button appearance="subtle" key={key} type="button" className={section===key?'editor-section-current':''} aria-current={section===key?'true':undefined} disabled={busy} onClick={()=>setSection(key)}>{String(i+1).padStart(2,'0')}. {t(editorSections[key].title)}{changedSections.includes(key)?' *':''}</Button>)}
        </nav>
        <div className="editor-section-form" key={section}>
          <div className="editor-form-heading"><span>{t("Section {current} of {total}",{current:librarySections.indexOf(section)+1,total:librarySections.length})}</span><h3>{t(editorSections[section].title)}</h3></div><p className="fine-print">{t(editorSections[section].description)}</p>
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
        <strong>{diagnostic.valid?t("Valid structure · NOT_READY"):'INVALID_DOCUMENT'}</strong>
        {diagnostic.errors.length>0&&<ul>{diagnostic.errors.map((x,i)=><li key={i}>{x}</li>)}</ul>}
        {diagnostic.blockers.length>0&&<ul>{diagnostic.blockers.map((x,i)=><li key={i}>{x}</li>)}</ul>}
        <p className="fine-print">{t("Diagnostic only: no approval, verified assets or physical readiness asserted.")}</p>
      </div>}
      <details className="editor-diagnostics">
        <summary>{t("Core validation — selected inspection scope")}</summary>
        <p className="fine-print">{t("Choose an existing physical state and workflow. Core validates the entire document. Structural validity does not mean readiness.")}</p>
        <div className="draft-fields">
          <label htmlFor="draft-state">{t("Physical state")}</label><Select id="draft-state" value={target.stateId} disabled={busy} onChange={e=>{setTarget({stateId:e.target.value,recipeId:'',scope:''});setDiagnostic(null);}}><option value="">{t("Select state…")}</option>{states.map(s=><option key={s.value} value={s.value}>{s.label}</option>)}</Select>
          <label htmlFor="draft-recipe">{t("Inspection recipe")}</label><Select id="draft-recipe" value={target.recipeId} disabled={busy||!target.stateId} onChange={e=>{const found=recipes.find(r=>r.recipe_id===e.target.value);setTarget({...target,recipeId:e.target.value,scope:found?String(found.approval_scope):''});setDiagnostic(null);}}><option value="">{t("Select recipe…")}</option>{recipes.map((r,i)=><option key={i} value={String(r.recipe_id)}>{String(r.recipe_id)}</option>)}</Select>
          <label htmlFor="draft-scope">{t("Requested scope")}</label><output id="draft-scope">{target.scope&&libraryScopes.some(x=>x===target.scope)?target.scope:t("Not selected")}</output>
        </div>
        <Button disabled={!editable||busy||!target.stateId||!target.recipeId||!target.scope} onClick={()=>{void execute('validate');}}>{t("Validate document")}</Button>
      </details>
      <details className="editor-diagnostics"><summary>{t("Clone saved draft to a new revision")}</summary><div className="draft-fields">
        <label htmlFor="draft-clone-key">{t("New profile ID")}</label><Input id="draft-clone-key" value={newKey} maxLength={64} onChange={e=>setNewKey(e.target.value)} disabled={!canManage}/>
        <label htmlFor="draft-clone-revision">{t("New revision")}</label><Input id="draft-clone-revision" value={revision} maxLength={64} onChange={e=>setRevision(e.target.value)} disabled={!canManage}/>
      </div><Button disabled={!canManage||dirty||!identifier(newKey)||!identifier(revision)} onClick={()=>{void execute('clone');}}>{t("Clone saved revision")}</Button></details>
    </>}
    {!report&&message&&<p role="status" className="editor-feedback">{displayMessage(message)}</p>}
  </section>;
}
