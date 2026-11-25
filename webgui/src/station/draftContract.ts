import {librarySections} from '../api/libraryContract';
import {record} from './contract';

export type DraftAction = 'open' | 'create' | 'create_empty' | 'save' | 'clone' | 'validate' | 'validate_structure' | 'asset_import' | 'asset_preview';
export type DraftDocument = Record<typeof librarySections[number], unknown>;
export type DraftReport = Readonly<{
  schema: 'vision.api.ecu-draft.v1'; source: 'STATION'; instanceId: string;
  key: string; etag: string; document: DraftDocument;
}>;
export type DraftValidation = Readonly<{
  schema: 'vision.api.ecu-draft-validation.v1'; source: 'STATION'; instanceId: string;
  key: string; valid: boolean; status: 'NOT_READY' | 'INVALID_DOCUMENT'; errors: readonly string[]; blockers: readonly string[];
}>;
export function identifier(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(value) && !/[^A-Za-z0-9_-]/.test(value);
}
function hex32(value: unknown): value is string {
  return typeof value === 'string' && value.length === 32 && !/[^a-f0-9]/.test(value);
}
export function isDraftReport(value: unknown): value is DraftReport {
  if (!record(value, ['schema','source','instanceId','key','etag','document']) ||
      value.schema !== 'vision.api.ecu-draft.v1' || value.source !== 'STATION' ||
      !hex32(value.instanceId) || !identifier(value.key) ||
      typeof value.etag !== 'string' || value.etag.length !== 66 || !/^"[a-f0-9]{64}"$/.test(value.etag) ||
      !record(value.document, librarySections)) return false;
  const document = value.document;
  const meta = document.metadata;
  const provenance = document.provenance_release;
  return record(meta,['kind','schema_version','template_only','profile_id','family_id','variant_id','profile_revision','display_name','status','approval_scopes','content_sha256']) &&
    meta.kind === 'ecu_reference_profile' && meta.schema_version === '1' && meta.template_only === false && meta.profile_id === value.key &&
    identifier(meta.family_id) && identifier(meta.variant_id) && identifier(meta.profile_revision) &&
    typeof meta.display_name === 'string' && meta.status === 'DRAFT' && meta.content_sha256 === null &&
    Array.isArray(meta.approval_scopes) && meta.approval_scopes.length === 0 &&
    record(provenance,['measurement_sources','calibration_dependencies','asset_hashes','release_approval','released_snapshot_sha256','supersedes']) &&
    provenance.release_approval === null && provenance.released_snapshot_sha256 === null &&
    librarySections.every(k => k === 'physical_states' ? Array.isArray(document[k]) :
      typeof document[k] === 'object' && document[k] !== null && !Array.isArray(document[k]));
}
function messages(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 64 && value.every(x => typeof x === 'string' && x.length <= 512);
}
export function isDraftValidation(value: unknown): value is DraftValidation {
  return record(value,['schema','source','instanceId','key','valid','status','errors','blockers']) &&
    value.schema === 'vision.api.ecu-draft-validation.v1' && value.source === 'STATION' &&
    hex32(value.instanceId) && identifier(value.key) && typeof value.valid === 'boolean' &&
    value.status === (value.valid ? 'NOT_READY' : 'INVALID_DOCUMENT') && messages(value.errors) && messages(value.blockers);
}


export const maxEditorImageBytes=2*1024*1024;
export type DraftAssetReport=Readonly<{
  schema:'vision.api.ecu-draft-asset.v1';source:'STATION';instanceId:string;key:string;
  sha256:string;relativePath:string;bytes:number;mime:'image/png'|'image/jpeg';status:'UNVERIFIED';
}>;
export type DraftAssetPreview=DraftAssetReport&Readonly<{assetId:string;data:string}>;
function assetReport(value:unknown,preview:boolean):value is DraftAssetReport|DraftAssetPreview {
  if(!record(value,['schema','source','instanceId','key','sha256','relativePath','bytes','mime','status',...(preview?['assetId','data']:[])]))return false;
  if(value.schema!=='vision.api.ecu-draft-asset.v1'||value.source!=='STATION'||!hex32(value.instanceId)||!identifier(value.key)
    ||typeof value.sha256!=='string'||value.sha256.length!==64||/[^a-f0-9]/.test(value.sha256)
    ||value.relativePath!=='assets/'+value.sha256||typeof value.bytes!=='number'||!Number.isSafeInteger(value.bytes)||value.bytes<1||value.bytes>maxEditorImageBytes
    ||(value.mime!=='image/png'&&value.mime!=='image/jpeg')||value.status!=='UNVERIFIED')return false;
  if(preview){
    if(!identifier(value.assetId)||typeof value.data!=='string'||value.data.length!==4*Math.ceil(value.bytes/3)||!/^[A-Za-z0-9+/]+={0,2}$/.test(value.data))return false;
    const padding=value.data.endsWith('==')?2:value.data.endsWith('=')?1:0;
    if(value.data.length/4*3-padding!==value.bytes)return false;
  }
  return true;
}
export function isDraftAssetReport(value:unknown):value is DraftAssetReport{return assetReport(value,false);}
export function isDraftAssetPreview(value:unknown):value is DraftAssetPreview{return assetReport(value,true);}
