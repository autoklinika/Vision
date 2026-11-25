import {useRef,useState} from 'react';
import type {DraftReport,DraftAssetPreview} from './draftContract';
import {identifier,maxEditorImageBytes} from './draftContract';
import type {FormDocument} from './editorFields';
import {row,array,referenceOptions} from './editorFields';
import {importDraftAsset,previewDraftAsset} from './transport';

type Props={report:DraftReport;document:FormDocument;disabled:boolean;readable:boolean;
  onAttach:(asset:Record<string,unknown>)=>void;onBusy:(busy:boolean)=>void;onConflict:()=>void};
const failures:Record<string,string>={
  BAD_REQUEST:'Core rejected the file or request. Use a valid JPEG or PNG within the limits.',
  DRAFT_CONFLICT:'Draft changed, station is busy, or the asset store is at capacity. Reload the latest draft.',
  DRAFT_NOT_FOUND:'The referenced draft or stored image was not found.',
  OPERATOR_REQUIRED:'Operator permission is required.',ACCESS_DENIED:'Authentication expired.',
  RATE_LIMITED:'Request rate limited.',UNAVAILABLE:'Import/preview outcome not confirmed. Do not retry automatically.',
};
async function fileBase64(file:File){
  const bytes=new Uint8Array(await file.arrayBuffer());
  if(bytes.length>maxEditorImageBytes||bytes.length===0)throw new Error('Image must be between 1 byte and 2 MiB.');
  let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
  return btoa(binary);
}
export function EditorAssets({report,document,disabled,readable,onAttach,onBusy,onConflict}:Props){
  const [file,setFile]=useState<File|null>(null);
  const [assetId,setAssetId]=useState('');
  const [kind,setKind]=useState('photo');
  const [stateId,setStateId]=useState('');
  const [sourceId,setSourceId]=useState('');
  const [message,setMessage]=useState('');
  const [previewId,setPreviewId]=useState('');
  const [preview,setPreview]=useState<DraftAssetPreview|null>(null);
  const running=useRef(false);
  const fileInput=useRef<HTMLInputElement|null>(null);
  const current=array(row(document.reference_assets).assets).map(row);
  const manifest=array(row(document.provenance_release).asset_hashes).map(row);
  const duplicate=current.some(x=>x.asset_id===assetId)||manifest.some(x=>x.asset_id===assetId);
  const states=referenceOptions(document,'state');
  const sources=referenceOptions(document,'source');
  const saved=array(row(report.document.reference_assets).assets).map(row)
    .filter(x=>typeof x.relative_path==='string'&&typeof x.sha256==='string'&&x.relative_path==='assets/'+x.sha256.toLowerCase()
      &&(x.mime==='image/png'||x.mime==='image/jpeg')&&typeof x.bytes==='number'&&x.bytes<=maxEditorImageBytes&&identifier(x.asset_id));
  async function doImport(){
    if(running.current||disabled||!file||!identifier(assetId)||duplicate||!states.some(x=>x.value===stateId)||!sources.some(x=>x.value===sourceId))return;
    if(file.size<1||file.size>maxEditorImageBytes){setMessage('Select a JPEG or PNG up to 2 MiB.');return;}
    running.current=true;onBusy(true);setMessage('');
    try{
      const result=await importDraftAsset({instanceId:report.instanceId,key:report.key,etag:report.etag,data:await fileBase64(file)});
      if(result.status==='AVAILABLE'){
        const image=result.report;
        // Only actual metadata from Core is inserted. The new row is not
        // verified and the operator must explicitly save the working draft.
        onAttach({asset_id:assetId,kind,relative_path:image.relativePath,sha256:image.sha256,bytes:String(image.bytes),
          mime:image.mime,physical_state_id:stateId,source_id:sourceId,verified:false,privacy_class:'private'});
        setMessage('Image imported as UNVERIFIED. Save the working draft to attach it.');setFile(null);setAssetId('');
        if(fileInput.current)fileInput.current.value='';
      }else{
        setMessage(failures[result.status]);
        if(result.status==='DRAFT_CONFLICT'||result.status==='UNAVAILABLE'||result.status==='DRAFT_NOT_FOUND')onConflict();
      }
    }catch(error){setMessage(error instanceof Error?error.message:'Image import unavailable.');}
    finally{running.current=false;onBusy(false);}
  }
  async function showPreview(){
    if(running.current||!readable||!saved.some(x=>x.asset_id===previewId))return;
    running.current=true;onBusy(true);setPreview(null);setMessage('');
    try{
      const result=await previewDraftAsset({instanceId:report.instanceId,key:report.key,etag:report.etag,assetId:previewId});
      if(result.status==='AVAILABLE'){setPreview(result.report);setMessage('Stored image bytes checked by Core. This is not evidence approval.');}
      else {setMessage(failures[result.status]);if(result.status==='DRAFT_CONFLICT')onConflict();}
    }finally{running.current=false;onBusy(false);}
  }
  return <fieldset className="editor-asset-box"><legend>Managed reference images</legend>
    <p className="fine-print">Import JPEG/PNG up to 2 MiB and 8 megapixels. Core validates the image and stores it privately by SHA-256. No image is marked verified automatically.</p>
    <div className="draft-fields">
      <label htmlFor="asset-file">Image file</label><input id="asset-file" ref={fileInput} type="file" accept="image/jpeg,image/png,.jpg,.jpeg,.png" disabled={disabled} onChange={e=>{setFile(e.target.files?.[0]??null);setMessage('');}}/>
      <label htmlFor="asset-id">Imported asset ID</label><input id="asset-id" value={assetId} maxLength={64} disabled={disabled} onChange={e=>setAssetId(e.target.value)}/>
      <label htmlFor="asset-kind">Image kind</label><select id="asset-kind" value={kind} disabled={disabled} onChange={e=>setKind(e.target.value)}><option value="photo">Photo</option><option value="image">Image</option></select>
      <label htmlFor="asset-state">Image physical state</label><select id="asset-state" value={stateId} disabled={disabled} onChange={e=>setStateId(e.target.value)}><option value="">Select state…</option>{states.map(x=><option key={x.value} value={x.value}>{x.label}</option>)}</select>
      <label htmlFor="asset-source">Image source</label><select id="asset-source" value={sourceId} disabled={disabled} onChange={e=>setSourceId(e.target.value)}><option value="">Select source…</option>{sources.map(x=><option key={x.value} value={x.value}>{x.label}</option>)}</select>
    </div>
    {duplicate&&<p className="editor-warning">Asset ID already used in the working draft or its manifest.</p>}
    <button disabled={disabled||!file||!identifier(assetId)||duplicate||!states.some(x=>x.value===stateId)||!sources.some(x=>x.value===sourceId)} onClick={()=>{void doImport();}}>Import reference image</button>
    <p className="fine-print">An imported file is stored before the draft is saved; closing without saving can leave an unattached private asset. No automatic deletion.</p>
    <div className="draft-fields">
      <label htmlFor="asset-preview">Saved image preview</label><select id="asset-preview" value={previewId} disabled={!readable||running.current} onChange={e=>{setPreviewId(e.target.value);setPreview(null);}}><option value="">Select saved image…</option>{saved.map((x,i)=><option key={i} value={String(x.asset_id)}>{String(x.asset_id)}</option>)}</select>
    </div>
    <button disabled={!readable||running.current||!previewId||!saved.some(x=>x.asset_id===previewId)} onClick={()=>{void showPreview();}}>Preview saved image</button>
    {preview&&<div className="editor-asset-preview"><img src={'data:'+preview.mime+';base64,'+preview.data} alt={'Stored reference image '+preview.assetId}/><p className="fine-print">{preview.mime} · {preview.bytes} bytes · SHA-256 {preview.sha256}</p><button onClick={()=>setPreview(null)}>Close preview</button></div>}
    {message&&<p role="status">{message}</p>}
  </fieldset>;
}
