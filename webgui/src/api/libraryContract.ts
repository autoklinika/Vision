/** API-03 read projection. Only the backend owns profile validation and readiness. */
export const librarySections = ['metadata','identity','physical_states','coordinate_systems','geometry','connectors_landmarks','reference_assets','recognition_rules','localization_rules','pcb_definition','photography_recipes','thermal_recipes','inspection_workflows','validation_policies','provenance_release'] as const;
export type LibrarySectionName = typeof librarySections[number];
export const libraryScopes = ['browse_and_select','verify_identity','localize','photo_inspection','thermal_relative','thermal_radiometric'] as const;
export type LibraryScope = typeof libraryScopes[number];
type LibraryIdentity = Readonly<{
  scope: 'LIBRARY_READ_ONLY'; source: 'STATION' | 'SYNTHETIC_TEST';
  libraryId: string; viewId: string; capturedAt: string;
}>;
export const draftLifecycles = ['ACTIVE','ARCHIVED','REVIEW_READY','RELEASED'] as const;
export type DraftLifecycle = typeof draftLifecycles[number];
export function isDraftLifecycle(value:unknown):value is DraftLifecycle {
  return draftLifecycles.some(state=>state===value);
}
export type LibraryEntry = Readonly<{
  entryId: string; kind: 'CATALOG_RECORD' | 'REFERENCE_DRAFT'; profileId: string;
  family: string; variant: string; revision: string; displayName: string;
  status: 'DRAFT' | 'READY_FOR_REVIEW' | 'APPROVED'; readiness: 'NOT_READY';
  reasonCode: 'CATALOG_ONLY' | 'UNSIGNED_DRAFT'; etag: string | null;
  lifecycle?:DraftLifecycle; searchTerms?:string; searchComplete?:boolean; releaseDigest?:string; simplified?:true;
}>;
export type LibraryReport = LibraryIdentity & Readonly<{
  schema: 'vision.api.library.v1'; after: number; totalCount: number;
  nextAfter: number | null; entries: readonly LibraryEntry[];
}>;
export type LibrarySection = Readonly<{name: LibrarySectionName; rowCount: number | null; status: 'NOT_EVALUATED'}>;
export type LibraryProfile = Readonly<{
  sections: readonly LibrarySection[];
  physicalStates: readonly Readonly<{id: string; displayName: string; declaredVerified: boolean}>[];
  workflows: readonly Readonly<{id: string; stateId: string; scope: LibraryScope}>[];
  historyCount: number;
}>;
export type LibraryDetail = LibraryIdentity & Readonly<{
  schema: 'vision.api.library-entry.v1'; entry: LibraryEntry;
  catalog: Readonly<{
    connectors: readonly Readonly<{id: string; color: string}>[];
    fieldNoteCount: number; fieldNotesVerified: false; envelopePresent: boolean;
  }> | null;
  profile: LibraryProfile | null;
}>;
export type LibraryHistoryItem = Readonly<{snapshotId: string; etag: string; revision: string; lifecycle?:DraftLifecycle; releaseDigest?:string}>;
export type LibraryHistory = LibraryIdentity & Readonly<{
  schema: 'vision.api.library-history.v1'; entryId: string; profileId: string;
  revision: string; etag: string; after: number; totalCount: number;
  nextAfter: number | null; items: readonly LibraryHistoryItem[];
}>;

const identityKeys = ['schema','scope','source','libraryId','viewId','capturedAt'];
const entryKeys = ['entryId','kind','profileId','family','variant','revision','displayName','status','readiness','reasonCode','etag'];
function record(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function extendedRecord(value:unknown,required:readonly string[],optional:readonly string[]):value is Record<string,unknown>{
  if(typeof value!=='object'||value===null||Array.isArray(value))return false;
  return required.every(k=>Object.hasOwn(value,k))&&Object.keys(value).every(k=>required.includes(k)||optional.includes(k));
}
function integer(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= max;
}
function identifier(value: unknown): value is string { return typeof value === 'string' && value.length >= 1 && value.length <= 64 && /^[A-Za-z0-9]/.test(value) && !/[^A-Za-z0-9_-]/.test(value); }
function hex(value: unknown, size: number): value is string { return typeof value === 'string' && value.length === size && !/[^0-9a-f]/.test(value); }
function etag(value: unknown): value is string { return typeof value === 'string' && value.length === 66 && value[0] === '"' && value[65] === '"' && hex(value.slice(1, -1), 64); }
function label(value: unknown, max: number): value is string {
  return typeof value === 'string' && Array.from(value).length > 0 && Array.from(value).length <= max && value.trim().length > 0 &&
    !/\p{C}/u.test(value) && !value.includes('/') && !value.includes('\\');
}
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || value.length !== 20 || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value.slice(0, -1) + '.000Z';
}
function identity(value: Record<string, unknown>): boolean {
  return value.scope === 'LIBRARY_READ_ONLY' && (value.source === 'STATION' || value.source === 'SYNTHETIC_TEST') &&
    identifier(value.libraryId) && hex(value.viewId, 64) && utc(value.capturedAt);
}
function sameView(a: LibraryIdentity, b: LibraryIdentity): boolean {
  return a.libraryId === b.libraryId && a.viewId === b.viewId && a.source === b.source;
}
function page(after: unknown, total: unknown, next: unknown, count: number, maximum: number): boolean {
  if (!integer(after, maximum) || !integer(total, maximum) || after % 50 !== 0 || (after >= total && !(after === 0 && total === 0))) return false;
  const end = after + Math.min(50, total - after);
  return count === end - after && next === (end < total ? end : null);
}
export function isLibraryEntry(value: unknown): value is LibraryEntry {
  if (!extendedRecord(value,entryKeys,['lifecycle','searchTerms','searchComplete','releaseDigest','simplified']) || !hex(value.entryId, 32) || !identifier(value.profileId) ||
      !identifier(value.family) || !identifier(value.variant) || !identifier(value.revision) || !label(value.displayName, 160) || value.readiness !== 'NOT_READY') return false;
  if(value.kind==='CATALOG_RECORD'&&!record(value,entryKeys))return false;
  if(Object.hasOwn(value,'lifecycle')&&!isDraftLifecycle(value.lifecycle))return false;
  if(Object.hasOwn(value,'simplified')&&(value.simplified!==true||!['ACTIVE','ARCHIVED'].includes(String(value.lifecycle??'ACTIVE'))))return false;
  if((value.lifecycle==='RELEASED')!==Object.hasOwn(value,'releaseDigest')||
    (Object.hasOwn(value,'releaseDigest')&&!hex(value.releaseDigest,64)))return false;
  if(Object.hasOwn(value,'searchTerms')!==Object.hasOwn(value,'searchComplete'))return false;
  if(Object.hasOwn(value,'searchTerms')&&(typeof value.searchTerms!=='string'||value.searchTerms.length>1024||/\p{C}/u.test(value.searchTerms)||typeof value.searchComplete!=='boolean'))return false;
  return value.kind === 'CATALOG_RECORD'
    ? typeof value.status === 'string' && ['DRAFT','READY_FOR_REVIEW','APPROVED'].includes(value.status) && value.reasonCode === 'CATALOG_ONLY' && value.etag === null
    : value.kind === 'REFERENCE_DRAFT' && value.status === 'DRAFT' && value.reasonCode === 'UNSIGNED_DRAFT' && etag(value.etag);
}
export function isLibraryReport(value: unknown): value is LibraryReport {
  return record(value, [...identityKeys,'after','totalCount','nextAfter','entries']) && value.schema === 'vision.api.library.v1' && identity(value) &&
    Array.isArray(value.entries) && value.entries.every(isLibraryEntry) && new Set(value.entries.map(entry => entry.entryId)).size === value.entries.length &&
    page(value.after, value.totalCount, value.nextAfter, value.entries.length, 512);
}
export function isLibraryDetail(value: unknown): value is LibraryDetail {
  if (!record(value, [...identityKeys,'entry','catalog','profile']) || value.schema !== 'vision.api.library-entry.v1' || !identity(value) || !isLibraryEntry(value.entry)) return false;
  if (value.entry.kind === 'CATALOG_RECORD') {
    const catalog = value.catalog;
    return value.profile === null && record(catalog, ['connectors','fieldNoteCount','fieldNotesVerified','envelopePresent']) &&
      integer(catalog.fieldNoteCount, 1000000) && catalog.fieldNotesVerified === false && typeof catalog.envelopePresent === 'boolean' &&
      Array.isArray(catalog.connectors) && catalog.connectors.length <= 64 && catalog.connectors.every(connector => record(connector, ['id','color']) && identifier(connector.id) && typeof connector.color === 'string' && ['black','gray','other'].includes(connector.color)) &&
      new Set(catalog.connectors.map(connector => connector.id)).size === catalog.connectors.length;
  }
  const profile = value.profile;
  if (value.catalog !== null || !record(profile, ['sections','physicalStates','workflows','historyCount']) || !integer(profile.historyCount, 4096) || profile.historyCount === 0 ||
      !Array.isArray(profile.sections) || profile.sections.length !== librarySections.length || !profile.sections.every((section, index) =>
        record(section, ['name','rowCount','status']) && section.name === librarySections[index] && section.status === 'NOT_EVALUATED' && (section.rowCount === null || integer(section.rowCount, 1000000))) ||
      !Array.isArray(profile.physicalStates) || profile.physicalStates.length > 128 || !profile.physicalStates.every(state =>
        record(state, ['id','displayName','declaredVerified']) && identifier(state.id) && label(state.displayName, 160) && typeof state.declaredVerified === 'boolean') ||
      new Set(profile.physicalStates.map(state => state.id)).size !== profile.physicalStates.length ||
      !Array.isArray(profile.workflows) || profile.workflows.length > 128 || !profile.workflows.every(workflow =>
        record(workflow, ['id','stateId','scope']) && identifier(workflow.id) && identifier(workflow.stateId) && libraryScopes.some(scope => scope === workflow.scope)) ||
      new Set(profile.workflows.map(workflow => workflow.id)).size !== profile.workflows.length) return false;
  const states = new Set(profile.physicalStates.map(state => state.id));
  return profile.workflows.every(workflow => states.has(workflow.stateId));
}
export function isLibraryHistory(value: unknown): value is LibraryHistory {
  if (!record(value, [...identityKeys,'entryId','profileId','revision','etag','after','totalCount','nextAfter','items']) ||
      value.schema !== 'vision.api.library-history.v1' || !identity(value) || !hex(value.entryId, 32) || !identifier(value.profileId) ||
      !identifier(value.revision) || !etag(value.etag) || !Array.isArray(value.items) || value.totalCount === 0 ||
      !page(value.after, value.totalCount, value.nextAfter, value.items.length, 4096) || !value.items.every(item =>
        extendedRecord(item,['snapshotId','etag','revision'],['lifecycle','releaseDigest']) && (!Object.hasOwn(item,'lifecycle')||isDraftLifecycle(item.lifecycle)) && ((item.lifecycle==='RELEASED')===Object.hasOwn(item,'releaseDigest')) && (!Object.hasOwn(item,'releaseDigest')||hex(item.releaseDigest,64)) && hex(item.snapshotId, 32) && etag(item.etag) && item.revision === value.revision)) return false;
  if (new Set(value.items.map(item => item.snapshotId)).size !== value.items.length || new Set(value.items.map(item => item.etag)).size !== value.items.length) return false;
  return value.nextAfter === null ? value.items.at(-1)?.etag === value.etag : value.items.every(item => item.etag !== value.etag);
}
export function matchesLibrary(page: LibraryReport, prior: LibraryReport, after: number): boolean {
  return sameView(page, prior) && page.after === after && page.totalCount === prior.totalCount;
}
export function matchesLibraryDetail(detail: LibraryDetail, library: LibraryReport, entry: LibraryEntry): boolean {
  return sameView(detail, library) && [...entryKeys,'lifecycle','searchTerms','searchComplete','releaseDigest','simplified'].every(key => detail.entry[key as keyof LibraryEntry] === entry[key as keyof LibraryEntry]);
}
export function matchesLibraryHistory(history: LibraryHistory, detail: LibraryDetail, after: number): boolean {
  return sameView(history, detail) && detail.profile !== null && history.entryId === detail.entry.entryId && history.profileId === detail.entry.profileId &&
    history.revision === detail.entry.revision && history.etag === detail.entry.etag && history.totalCount === detail.profile.historyCount && history.after === after;
}
