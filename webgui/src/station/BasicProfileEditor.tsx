import {Button,Input,Textarea,Select,Checkbox,MessageBar,MessageBarBody,Badge} from '@fluentui/react-components';
import {SaveRegular,AddRegular,ArrowClockwiseRegular,ImageRegular} from '@fluentui/react-icons';
import {useEffect,useRef,useState} from 'react';
import type {LibraryEntry} from '../api/libraryContract';
import type {StationPresentation} from './client';
import type {DraftReport,DraftAssetPreview} from './draftContract';
import {editDraft,importDraftAsset,previewDraftAsset} from './transport';
import type {DraftResult} from './transport';
import {fileBase64} from './EditorAssets';
import {useTranslation} from '../i18n/LanguageProvider';
import {basicStates,basicStateLabels,photoRoles,photoRoleLabels,emptyDeclaration,validIdentityLabel,basicMaxPhotos} from './basicContract';
import type {BasicDeclaration,BasicStateId,PhotoRole,BasicPhoto,BasicPayload,InspectionPreference} from './basicContract';
import {row} from './editorFields';

type BasicForm={
  family:string;variant:string;manufacturer:string;displayName:string;partNumbers:string;oemNumbers:string;aliases:string;
  states:{stateId:BasicStateId;dimensions:[string,string,string]}[];
  photos:BasicPhoto[];inspection:InspectionPreference;
};
const newId=()=> 'ecu-'+crypto.randomUUID();
const strings=(value:unknown)=>Array.isArray(value)?value.map(String).join('\n'):'';
const lines=(value:string)=>[...new Set(value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean))];
const statusMessage:Record<string,string>={
  DRAFT_CONFLICT:'Profile changed, already exists, or the station is not idle. Reload before continuing.',
  BAD_REQUEST:'Core rejected the profile data. Check the entered values.',
  DRAFT_NOT_FOUND:'The requested profile or photo is unavailable.',
  ACCESS_DENIED:'Authentication expired. Sign in again.',
  OPERATOR_REQUIRED:'Operator permission is required.',
  RATE_LIMITED:'Request rate limited.',
  UNAVAILABLE:'Outcome not confirmed. Check the saved profile before retrying.',
};
function initial(entry:LibraryEntry|'new'):BasicForm{
  return {family:entry==='new'?'':entry.family,variant:entry==='new'?'':entry.variant,
    manufacturer:'',displayName:entry==='new'?'':entry.displayName,partNumbers:'',oemNumbers:'',aliases:'',
    states:[],photos:[],inspection:emptyDeclaration().inspection};
}
function fromReport(report:DraftReport):BasicForm{
  const m=row(report.document.metadata),i=row(report.document.identity),d=report.declaration;
  return {family:d?.familyLabel??String(m.family_id),variant:d?.variantLabel??String(m.variant_id),
    manufacturer:i.manufacturer===null?'':String(i.manufacturer),displayName:String(m.display_name),
    partNumbers:strings(i.manufacturer_part_numbers),oemNumbers:strings(i.oem_part_numbers),aliases:strings(i.aliases),
    states:(d?.states??[]).map(s=>({stateId:s.stateId,dimensions:s.dimensionsMm.map(x=>x===null?'':String(x)) as [string,string,string]})),
    photos:d?.photos??[],inspection:d?.inspection??emptyDeclaration().inspection};
}
function parseDimension(value:string):number|null|undefined{
  if(!value.trim())return null;
  if(!/^\d+(?:[.,]\d+)?$/.test(value.trim()))return undefined;
  const n=Number(value.trim().replace(',','.'));
  return Number.isFinite(n)&&n>0&&n<=1000000?n:undefined;
}
function makePayload(form:BasicForm):BasicPayload|null{
  if(!validIdentityLabel(form.family)||!validIdentityLabel(form.variant))return null;
  const stateRows:BasicDeclaration['states']=[];
  for(const s of form.states){
    const dims=s.dimensions.map(parseDimension);
    if(dims.some(x=>x===undefined))return null;
    stateRows.push({stateId:s.stateId,dimensionsMm:dims as [number|null,number|null,number|null]});
  }
  const identity={manufacturer:form.manufacturer.trim()||null,displayName:form.displayName.trim()||[form.family.trim(),form.variant.trim()].join(' '),
    manufacturer_part_numbers:lines(form.partNumbers),oem_part_numbers:lines(form.oemNumbers),aliases:lines(form.aliases)};
  if(identity.displayName.length>160||/[/\\\p{C}]/u.test(identity.displayName)||
      [identity.manufacturer_part_numbers,identity.oem_part_numbers,identity.aliases].some(a=>a.length>64||a.some(v=>v.length>160||/\p{C}/u.test(v)))||
      (identity.manufacturer!==null&&/\p{C}/u.test(identity.manufacturer))||/\p{C}/u.test(form.inspection.notes.replace(/\n/g,"")))return null;
  return {identity,declaration:{schema:'vision.ecu-declaration.v2',familyLabel:form.family.trim(),variantLabel:form.variant.trim(),
    states:stateRows,photos:form.photos,inspection:form.inspection}};
}
type Props={entry:LibraryEntry|'new';station:StationPresentation;onClose:()=>void;onAdvanced:()=>void;refreshLibrary:()=>void};
export function BasicProfileEditor({entry,station,onClose,onAdvanced,refreshLibrary}:Props){
  const {t}=useTranslation();
  const existing=entry!=='new'&&entry.kind==='REFERENCE_DRAFT';
  const [form,setForm]=useState<BasicForm>(()=>initial(entry));
  const [key,setKey]=useState(()=>existing?entry.profileId:newId());
  const [report,setReport]=useState<DraftReport|null>(null);
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const [message,setMessage]=useState('');
  const [nextState,setNextState]=useState<BasicStateId|''>('');
  const [photoState,setPhotoState]=useState<BasicStateId|''>('');
  const [photoRole,setPhotoRole]=useState<PhotoRole>('label');
  const [file,setFile]=useState<File|null>(null);
  const [preview,setPreview]=useState<DraftAssetPreview|null>(null);
  const running=useRef(false), started=useRef(false), fileRef=useRef<HTMLInputElement>(null);
  const instanceId=station.report.instanceId;
  const readable=station.identity.role==='operator'&&station.report.coreConnection==='CONNECTED'&&!station.accountBusy;
  const idle=station.report.state==='NO_ACTIVE_SESSION';
  const legacy=!!report&&!report.declaration&&!report.basicEligible;
  const lifecycle=report?.lifecycle??'ACTIVE';
  const canManage=readable&&idle&&!busy&&!uncertain;
  const writable=canManage&&lifecycle==='ACTIVE'&&!legacy&&(!existing||!!report);
  const payload=makePayload(form);
  const confirmDiscard=()=>!dirty||window.confirm(t('Discard unsaved draft changes?'));

  useEffect(()=>{
    if(!dirty&&!busy)return;
    const listener=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    window.addEventListener('beforeunload',listener);
    return()=>window.removeEventListener('beforeunload',listener);
  },[dirty,busy]);

  function load(next:DraftReport){
    setReport(next);setForm(fromReport(next));setKey(next.key);setDirty(false);setUncertain(false);
    setFile(null);setPreview(null);setNextState('');setPhotoState('');if(fileRef.current)fileRef.current.value='';
  }
  // A single initial read of a selected saved profile. No polling or automatic
  // mutation; a failed read can be explicitly retried.
  useEffect(()=>{
    if(!existing||report||started.current||!readable)return;
    started.current=true;running.current=true;
    let cancelled=false;
    void editDraft('open',{instanceId,key}).then(result=>{
      if(cancelled)return;
      if(result.status==='AVAILABLE'){load(result.report);setMessage('Draft loaded from Core.');}
      else setMessage(statusMessage[result.status]);
    }).catch(()=>{if(!cancelled)setMessage(statusMessage.UNAVAILABLE);}).finally(()=>{if(!cancelled)running.current=false;});
    return()=>{cancelled=true;started.current=false;running.current=false;};
  },[existing,readable,instanceId,key,report]);

  function change<K extends keyof BasicForm>(k:K,v:BasicForm[K]){
    setForm(old=>({...old,[k]:v}));setDirty(true);setMessage('');
  }
  function preference<K extends keyof InspectionPreference>(k:K,v:InspectionPreference[K]){
    change('inspection',{...form.inspection,[k]:v});
  }
  function error(result:DraftResult<unknown>,mutation=true){
    setMessage(statusMessage[result.status]??statusMessage.UNAVAILABLE);
    if(mutation&&['DRAFT_CONFLICT','UNAVAILABLE','DRAFT_NOT_FOUND'].includes(result.status)){
      setUncertain(true);refreshLibrary();
    }
  }
  async function action(name:'open'|'save'|'archive'|'restore'|'clone'){
    if(running.current||!readable)return;
    if(name==='open'&&!confirmDiscard())return;
    if(name==='save'&&(!writable||!payload))return;
    if(['archive','restore','clone'].includes(name)&&(!canManage||!report?.declaration||dirty))return;
    if((name==='archive'||name==='restore')&&!window.confirm(t('Change the saved profile lifecycle? The document and its history will be retained.')))return;
    running.current=true;setBusy(true);setMessage('');
    let requested=key;
    try{
      let result:DraftResult<DraftReport>;
      if(name==='open')result=await editDraft('open',{instanceId,key});
      else if(name==='save'&&payload){
        result=report?await editDraft('save_basic',{instanceId,key:report.key,etag:report.etag},JSON.stringify(payload)):
          await editDraft('create_basic',{instanceId,key},JSON.stringify(payload));
      }else if(name==='clone'&&report){
        requested=newId();
        result=await editDraft('clone_basic',{instanceId,key:report.key,etag:report.etag,newKey:requested});
      }else if((name==='archive'||name==='restore')&&report)result=await editDraft(name,{instanceId,key:report.key,etag:report.etag});
      else return;
      if(result.status==='AVAILABLE'){
        load(result.report);setMessage(name==='open'?'Draft loaded from Core.':name==='clone'?'New draft revision created.':'Profile saved in Core.');
        if(name!=='open')refreshLibrary();
      }else{
        error(result,name!=='open');
        if(name==='clone'&&['UNAVAILABLE','DRAFT_CONFLICT'].includes(result.status))setKey(requested);
        if(name==='open'&&result.status==='DRAFT_NOT_FOUND'&&uncertain){
          // No automatic retry of the prior mutation. A missing requested new
          // identity can be checked by returning to the previous saved copy.
          if(report)setKey(report.key);
          setUncertain(false);
        }
      }
    }catch{setMessage(statusMessage.UNAVAILABLE);if(name!=='open'){setUncertain(true);setKey(requested);refreshLibrary();}}
    finally{running.current=false;setBusy(false);}
  }
  function addState(){
    if(!nextState||form.states.some(s=>s.stateId===nextState))return;
    change('states',[...form.states,{stateId:nextState,dimensions:['','','']}]);setNextState('');
    if(!photoState)setPhotoState(nextState);
  }
  function removeState(state:BasicStateId){
    if(form.photos.some(p=>p.stateId===state)){setMessage('Remove photo associations for this state first.');return;}
    if(!window.confirm(t('Remove this declared physical state?')))return;
    change('states',form.states.filter(s=>s.stateId!==state));
    if(photoState===state)setPhotoState('');
  }
  async function attach(){
    if(running.current||!writable||!report?.declaration||!file||!photoState||!form.states.some(s=>s.stateId===photoState)||form.photos.length>=basicMaxPhotos)return;
    running.current=true;setBusy(true);setMessage('');
    try{
      const result=await importDraftAsset({instanceId,key:report.key,etag:report.etag,data:await fileBase64(file)});
      if(result.status==='AVAILABLE'){
        const p=result.report;
        if(form.photos.some(x=>x.sha256===p.sha256)){setMessage('This image is already attached.');return;}
        change('photos',[...form.photos,{sha256:p.sha256,mime:p.mime,bytes:p.bytes,stateId:photoState,role:photoRole}]);
        setFile(null);if(fileRef.current)fileRef.current.value='';
        setMessage('Photo imported. Save the profile to retain its association.');
      }else error(result);
    }catch{setMessage('Select a JPEG or PNG up to 2 MiB.');}
    finally{running.current=false;setBusy(false);}
  }
  async function showPhoto(photo:BasicPhoto){
    if(!report||running.current||!readable||!report.declaration?.photos.some(p=>p.sha256===photo.sha256))return;
    running.current=true;setBusy(true);setPreview(null);setMessage('');
    try{
      const result=await previewDraftAsset({instanceId,key:report.key,etag:report.etag,assetId:photo.sha256});
      if(result.status==='AVAILABLE')setPreview(result.report);else error(result,false);
    }finally{running.current=false;setBusy(false);}
  }
  const familyInvalid=!!form.family&&!validIdentityLabel(form.family);
  const variantInvalid=!!form.variant&&!validIdentityLabel(form.variant);
  const availableStates=basicStates.filter(s=>!form.states.some(x=>x.stateId===s));
  const canAdvanced=!(entry!=='new'&&entry.simplified)&&!report?.declaration;
  const textField=(name:string,value:string,onChange:(v:string)=>void,disabled=false,invalid=false,maxLength=160)=>
    <label className="basic-field"><span>{t(name)}</span><Input value={value} maxLength={maxLength} disabled={!writable||disabled} aria-invalid={invalid} onChange={(_,data)=>onChange(data.value)}/></label>;
  return <section className="draft-editor basic-profile-editor" aria-label={t('ECU reference editor')} data-editor-dirty={dirty?'true':'false'} data-editor-busy={busy?'true':'false'}>
    <div className="editor-heading">
      <div><h3>{t('ECU profile')}</h3><span>{t('Simplified four-section editor')}</span></div>
      <div className="basic-editor-actions">
        {canAdvanced&&<Button appearance="subtle" disabled={busy} onClick={()=>{if(confirmDiscard())onAdvanced();}}>{t('Advanced editor')}</Button>}
        <Button disabled={busy} onClick={()=>{if(confirmDiscard())onClose();}}>{t('Close editor')}</Button>
      </div>
    </div>
    {report&&<div className="editor-summary"><strong>{form.displayName||report.key}</strong><span>{report.key} · {t('revision')} {String(row(report.document.metadata).profile_revision)}</span><Badge appearance="tint" color={dirty?'warning':'informative'}>{t(dirty?'Unsaved changes':'Saved generation')}</Badge><Badge appearance="tint">{t(lifecycle==='ARCHIVED'?'Archived profile':lifecycle==='REVIEW_READY'?'Submitted for review':lifecycle==='RELEASED'?'Released reference record':'Active draft')}</Badge></div>}
    {!readable&&<MessageBar intent="warning"><MessageBarBody>{t('Core connection is unavailable. Your unsaved form remains in this tab; editing resumes after reconnection.')}</MessageBarBody></MessageBar>}
    {readable&&!idle&&<MessageBar intent="warning"><MessageBarBody>{t('Core has an active session. Editing is read-only until the session closes.')}</MessageBarBody></MessageBar>}
    {legacy?<p>{t('This profile contains V1 technical data. Use the advanced editor; conversion would lose information.')}</p>:
      <>
        {report?.basicEligible&&<p className="fine-print">{t('Saving adopts the simplified model. Existing identity and history are retained.')}</p>}
        <div className="basic-profile-grid">
          <section className="basic-card" aria-label={t('ECU identification')}>
            <h3><span>01</span> {t('ECU identification')}</h3>
            {textField('Manufacturer',form.manufacturer,v=>change('manufacturer',v))}
            {textField('ECU family',form.family,v=>change('family',v),!!report,familyInvalid,64)}
            {familyInvalid&&<small className="editor-warning">{t('Use letters, digits, spaces, _ or -; start with a letter or digit.')}</small>}
            {textField('Variant',form.variant,v=>change('variant',v),!!report,variantInvalid,64)}
            {variantInvalid&&<small className="editor-warning">{t('Use letters, digits, spaces, _ or -; start with a letter or digit.')}</small>}
            {textField('Display name (optional)',form.displayName,v=>change('displayName',v))}
            <label className="basic-field"><span>{t('Manufacturer part numbers')}</span><Textarea value={form.partNumbers} rows={2} maxLength={4096} disabled={!writable} placeholder={t('One part number per line')} onChange={(_,d)=>change('partNumbers',d.value)}/></label>
            <label className="basic-field"><span>{t('OEM part numbers')}</span><Textarea value={form.oemNumbers} rows={2} maxLength={4096} disabled={!writable} placeholder={t('One part number per line')} onChange={(_,d)=>change('oemNumbers',d.value)}/></label>
            <details><summary>{t('Aliases')}</summary><label className="basic-field"><span>{t('Aliases')}</span><Textarea value={form.aliases} rows={2} maxLength={4096} disabled={!writable} onChange={(_,d)=>change('aliases',d.value)}/></label></details>
          </section>
          <section className="basic-card" aria-label={t('ECU geometry')}>
            <h3><span>02</span> {t('ECU geometry')}</h3>
            <svg className="basic-geometry-diagram" viewBox="0 0 310 150" role="img" aria-label={t('Maximum ECU dimensions XYZ')}>
              <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"><path d="M45 72L206 106 269 48 108 14Z" fill="#e5e8eb"/><path d="M45 72V97L206 131V106" fill="#bfc7cf"/><path d="M206 131L269 73V48" fill="#d4dbe2"/><path d="M64 93L225 127M41 106L202 140M276 48V73M205 141L282 71"/><path d="M47 103L41 106 45 113M196 133L202 140 196 143M272 54L276 48 280 54M272 67L276 73 280 67"/></g>
              <text x="112" y="139" fontSize="12" fill="currentColor">X</text><text x="250" y="119" fontSize="12" fill="currentColor">Y</text><text x="283" y="64" fontSize="12" fill="currentColor">Z</text>
            </svg>
            <p className="fine-print">{t('Enter measured maximum dimensions including protrusions. Leave unknown values blank.')}</p>
            {form.states.map(s=><fieldset className="basic-state" key={s.stateId}><legend>{t(basicStateLabels[s.stateId])}</legend>
              <div className="basic-dimensions">{(['X','Y','Z'] as const).map((axis,i)=><label key={axis} className="basic-field"><span>{t(i===0?'Length X (mm)':i===1?'Width Y (mm)':'Height Z (mm)')}</span><Input inputMode="decimal" value={s.dimensions[i]} maxLength={20} aria-invalid={parseDimension(s.dimensions[i])===undefined} disabled={!writable}
                onChange={(_,d)=>change('states',form.states.map(x=>x.stateId===s.stateId?{...x,dimensions:x.dimensions.map((v,j)=>i===j?d.value:v) as [string,string,string]}:x))}/></label>)}</div>
              {s.dimensions.some(v=>parseDimension(v)===undefined)&&<small className="editor-warning">{t('Dimensions must be positive numbers in millimetres.')}</small>}
              <Button appearance="subtle" disabled={!writable} onClick={()=>removeState(s.stateId)}>{t('Remove state')}</Button>
            </fieldset>)}
            {availableStates.length>0&&<div className="basic-inline"><label className="basic-field"><span>{t('Physical state')}</span><Select value={nextState} disabled={!writable} onChange={e=>setNextState(e.target.value as BasicStateId|'')}><option value="">{t('Select state…')}</option>{availableStates.map(s=><option key={s} value={s}>{t(basicStateLabels[s])}</option>)}</Select></label>
              <Button icon={<AddRegular/>} disabled={!writable||!nextState} onClick={addState}>{t('Add state')}</Button></div>}
          </section>
          <section className="basic-card" aria-label={t('Reference photographs')}>
            <h3><span>03</span> {t('Reference photographs')}</h3>
            {!report?.declaration&&<p className="fine-print">{t('Save the profile first to import photographs.')}</p>}
            <div className="basic-photo-inputs">
              <label className="basic-field"><span>{t('Photo category')}</span><Select value={photoRole} disabled={!writable||!report?.declaration} onChange={e=>setPhotoRole(e.target.value as PhotoRole)}>{photoRoles.map(r=><option key={r} value={r}>{t(photoRoleLabels[r])}</option>)}</Select></label>
              <label className="basic-field"><span>{t('Photo physical state')}</span><Select value={photoState} disabled={!writable||!report?.declaration} onChange={e=>setPhotoState(e.target.value as BasicStateId|'')}><option value="">{t('Select state…')}</option>{form.states.map(s=><option key={s.stateId} value={s.stateId}>{t(basicStateLabels[s.stateId])}</option>)}</Select></label>
            </div>
            <label className="basic-field"><span>{t('Image file')}</span><input type="file" ref={fileRef} accept="image/jpeg,image/png,.jpg,.jpeg,.png" disabled={!writable||!report?.declaration} onChange={e=>setFile(e.target.files?.[0]??null)}/></label>
            <Button icon={<ImageRegular/>} disabled={!writable||!report?.declaration||!file||!photoState||form.photos.length>=basicMaxPhotos} onClick={()=>{void attach();}}>{t('Add photograph')}</Button>
            <p className="fine-print">{t('JPEG/PNG up to 2 MiB and 8 megapixels. The system manages file metadata.')}</p>
            <div className="basic-photo-list">{form.photos.map(p=><div key={p.sha256} className="basic-photo-row"><div><strong>{t(photoRoleLabels[p.role])}</strong><small>{t(basicStateLabels[p.stateId])} · {Math.ceil(p.bytes/1024)} KB</small></div>
              <Button size="small" disabled={!readable||busy||!report?.declaration?.photos.some(x=>x.sha256===p.sha256)} onClick={()=>{void showPhoto(p);}}>{t('Preview')}</Button>
              <Button size="small" disabled={!writable} onClick={()=>{if(window.confirm(t('Remove this photo association? The stored file is retained.'))){change('photos',form.photos.filter(x=>x.sha256!==p.sha256));setPreview(null);}}}>{t('Remove')}</Button>
            </div>)}</div>
            {preview&&<div className="editor-asset-preview"><img src={'data:'+preview.mime+';base64,'+preview.data} alt={t('Reference photograph')}/><Button onClick={()=>setPreview(null)}>{t('Close preview')}</Button></div>}
          </section>
          <section className="basic-card" aria-label={t('Inspection preferences')}>
            <h3><span>04</span> {t('Inspection preferences')}</h3>
            <label className="basic-field"><span>{t('Inspection template')}</span><Select value={form.inspection.template??''} disabled={!writable} onChange={e=>preference('template',e.target.value==='standard_pcb'?'standard_pcb':null)}><option value="">{t('Not selected')}</option><option value="standard_pcb">{t('Standard PCB inspection (planned)')}</option></Select></label>
            <div className="basic-checks">{([['overview','Whole PCB photograph'],['oblique','Oblique views'],['details','Detailed photographs'],['customRoi','Individual regions of interest']] as const).map(([k,label])=><Checkbox key={k} label={t(label)} checked={form.inspection[k]} disabled={!writable} onChange={(_,d)=>preference(k,d.checked===true)}/>)}</div>
            <label className="basic-field"><span>{t('Special requirements (optional)')}</span><Textarea value={form.inspection.notes} rows={3} maxLength={1024} disabled={!writable} onChange={(_,d)=>preference('notes',d.value)}/></label>
            <p className="fine-print">{t('Preferences only. Inspection templates and automatic camera pose generation will be integrated later.')}</p>
          </section>
        </div>
      </>}
    <div className="basic-editor-footer">
      {!legacy&&<Button appearance="primary" icon={<SaveRegular/>} disabled={!writable||!payload||!!report&&!dirty&&!report.basicEligible} onClick={()=>{void action('save');}}>{t('Save ECU profile')}</Button>}
      {(existing||report||uncertain)&&<Button icon={<ArrowClockwiseRegular/>} disabled={!readable||busy} onClick={()=>{void action('open');}}>{t(uncertain?'Check requested draft':'Reload latest')}</Button>}
      {report?.declaration&&lifecycle==='ACTIVE'&&<Button disabled={!canManage||dirty} onClick={()=>{void action('archive');}}>{t('Archive profile')}</Button>}
      {report?.declaration&&lifecycle==='ARCHIVED'&&<Button disabled={!canManage} onClick={()=>{void action('restore');}}>{t('Restore profile')}</Button>}
      {report?.declaration&&<Button disabled={!canManage||dirty} onClick={()=>{void action('clone');}}>{t('Create next revision')}</Button>}
      {!legacy&&<span className="fine-print">{t('Declared data · NOT_READY')}</span>}
    </div>
    {message&&<p role="status" className="editor-feedback">{t(message)}</p>}
    {!payload&&writable&&!!form.family&&!!form.variant&&!familyInvalid&&!variantInvalid&&<p role="status" className="editor-warning">{t('Check invalid values before saving.')}</p>}
  </section>;
}
