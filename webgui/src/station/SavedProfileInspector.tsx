import {Button,Input,Select,Table,TableHeader,TableHeaderCell,TableBody,TableRow,TableCell} from '@fluentui/react-components';
import {useRef,useState} from 'react';
import {useTranslation} from '../i18n/LanguageProvider';
import type {LibraryDetail,LibraryHistory,LibrarySectionName} from '../api/libraryContract';
import {librarySections} from '../api/libraryContract';
import type {StationPresentation} from './client';
import type {DraftReport} from './draftContract';
import {identifier} from './draftContract';
import {editDraft} from './transport';
import {editorSections,hydrateDocument,row} from './editorFields';
import {FieldControl} from './EditorForm';
import {compareProfiles} from './profileComparison';

export function SavedProfileInspector({station,detail,history,onHistoryPage}:{station:StationPresentation;detail:LibraryDetail;history:LibraryHistory|null;onHistoryPage:(direction:'next'|'previous')=>void}){
  const {t}=useTranslation();
  const [snapshot,setSnapshot]=useState('');
  const [otherKey,setOtherKey]=useState('');
  const [section,setSection]=useState<LibrarySectionName>('metadata');
  const [before,setBefore]=useState<DraftReport|null>(null);
  const [after,setAfter]=useState<DraftReport|null>(null);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const running=useRef(false);
  const key=detail.entry.profileId, etag=detail.entry.etag!;
  const instanceId=station.report.instanceId;
  const allowed=station.identity.role==='operator'&&station.report.coreConnection==='CONNECTED'&&!station.accountBusy;
  const selected=history?.items.find(item=>item.snapshotId===snapshot);
  const valid=allowed&&!busy&&(!snapshot||!!selected);
  async function read(compare=false){
    if(!valid||running.current||compare&&otherKey!==''&&!identifier(otherKey))return;
    running.current=true;setBusy(true);setMessage('');setBefore(null);setAfter(null);
    try{
      const result=selected?await editDraft('open_generation',{instanceId,key,etag,snapshotId:selected.snapshotId}):
        await editDraft('open',{instanceId,key});
      if(result.status!=='AVAILABLE'||result.report.etag!==(selected?.etag??etag)){
        setMessage('The saved view changed or could not be read. Refresh the library.');return;
      }
      const a=result.report;
      hydrateDocument(a.document);
      if(!compare){setBefore(a);return;}
      const target=otherKey.trim()||key;
      const second=await editDraft('open',{instanceId,key:target});
      if(second.status!=='AVAILABLE'||(target===key&&second.report.etag!==etag)){
        setMessage('The comparison profile could not be read. Refresh the library.');return;
      }
      const m=row(a.document.metadata), n=row(second.report.document.metadata);
      if(m.family_id!==n.family_id||m.variant_id!==n.variant_id){
        setMessage('Compare only revisions of the same family and variant.');return;
      }
      hydrateDocument(second.report.document);
      setBefore(a);setAfter(second.report);
    }catch{setMessage('Stored document has an unsupported form structure. Reopen it with a compatible editor.');}
    finally{running.current=false;setBusy(false);}
  }
  const doc=before?hydrateDocument(before.document):null;
  const comparison=before&&after?compareProfiles(before.document,after.document):null;
  return <section className="saved-profile-inspector" aria-label={t('Saved profile viewer')}>
    <h3>{t('Saved profile viewer')}</h3>
    <div className="library-review-controls">
      <label htmlFor="library-generation-select">{t('Saved generation')}</label>
      <Select id="library-generation-select" value={snapshot} disabled={!allowed||busy} onChange={e=>{setSnapshot(e.target.value);setBefore(null);setAfter(null);setMessage('');}}>
        <option value="">{t('Current saved generation')}</option>
        {history?.items.map((item,i)=><option key={item.snapshotId} value={item.snapshotId}>{t('Generation')} {history.after+i+1} · {item.etag.slice(1,13)}</option>)}
      </Select>
      {history&&<><Button disabled={busy||history.after===0} onClick={()=>{setSnapshot('');setBefore(null);setAfter(null);onHistoryPage('previous');}}>{t('Previous history page')}</Button><Button disabled={busy||history.nextAfter===null} onClick={()=>{setSnapshot('');setBefore(null);setAfter(null);onHistoryPage('next');}}>{t('Next history page')}</Button></>}
      <Button appearance="primary" disabled={!valid} onClick={()=>{void read();}}>{t('Preview saved profile')}</Button>
    </div>
    <div className="library-review-controls">
      <label htmlFor="library-compare-key">{t('Compare with profile ID (optional)')}</label>
      <Input id="library-compare-key" maxLength={64} value={otherKey} placeholder={t('Current revision if empty')} disabled={!allowed||busy} onChange={(_,data)=>setOtherKey(data.value)}/>
      <Button disabled={!valid||!!otherKey&&!identifier(otherKey)} onClick={()=>{void read(true);}}>{t('Compare saved versions')}</Button>
    </div>
    {message&&<p role="status">{t(message)}</p>}
    {before&&doc&&<div className="saved-profile-preview">
      <p className="library-detail-key">{before.key} · {String(row(before.document.metadata).profile_revision)} · ETag {before.etag}</p>
      {comparison&&after?<><h3>{t('Version differences')}</h3><p className="library-detail-key">{t('Compared with')} {after.key} · {String(row(after.document.metadata).profile_revision)} · ETag {after.etag}</p>
        {comparison.differences.length===0?<p>{t('No document differences.')}</p>:<div className="library-detail-scroll"><Table aria-label={t('Version differences')}><TableHeader><TableRow><TableHeaderCell>{t('Field')}</TableHeaderCell><TableHeaderCell>{t('Before')}</TableHeaderCell><TableHeaderCell>{t('After')}</TableHeaderCell></TableRow></TableHeader><TableBody>
          {comparison.differences.map((diff,i)=><TableRow key={i}><TableCell>{t(editorSections[diff.section].title)}<small>{diff.path}</small></TableCell><TableCell>{diff.before}</TableCell><TableCell>{diff.after}</TableCell></TableRow>)}
        </TableBody></Table></div>}
        {comparison.truncated&&<p role="status">{t('Comparison limited to the first 256 differences.')}</p>}
      </>:<>
        <label htmlFor="library-preview-section">{t('Section')}</label><Select id="library-preview-section" value={section} onChange={e=>setSection(e.target.value as LibrarySectionName)}>
          {librarySections.map((name,i)=><option value={name} key={name}>{i+1}. {t(editorSections[name].title)}</option>)}
        </Select>
        <FieldControl field={editorSections[section].field} value={doc[section]} doc={doc} disabled onChange={()=>{}}/>
      </>}
    </div>}
  </section>;
}
