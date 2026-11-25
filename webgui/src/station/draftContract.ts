import {librarySections} from '../api/libraryContract';
import {record} from './contract';

export type DraftAction = 'open' | 'create' | 'save' | 'clone' | 'validate';
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

export type DraftParts = Record<typeof librarySections[number],string>;
export function draftParts(document: DraftDocument): DraftParts {
  return Object.fromEntries(librarySections.map(k => [k,JSON.stringify(document[k],null,2)])) as DraftParts;
}
/** Syntax check each section without normalizing its raw text. Duplicate keys
 * are still visible to the server's strict JSON parser. */
export function draftText(parts: DraftParts): string {
  for (const key of librarySections) {
    try { JSON.parse(parts[key]); } catch { throw new Error('Invalid JSON in section: ' + key); }
  }
  const text = '{' + librarySections.map(key => JSON.stringify(key)+':'+parts[key]).join(',') + '}';
  if (new TextEncoder().encode(text).length > 65536) throw new Error('Editor document exceeds 64 KiB.');
  return text;
}
