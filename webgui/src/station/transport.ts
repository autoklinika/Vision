import {isNeroReport} from './neroContract';
import type {NeroReport} from './neroContract';
import {isLuxonisReport,isIRResult} from './luxonisContract';
import type {LuxonisReport,IRResult,IRChannel} from './luxonisContract';
import { isIdentityReport, isLogoutReport, isPasswordChangeReport, isStationReport, isInspectionReport, record, usernameValid } from './contract';
import {isDraftReport, isDraftValidation, isDraftAssetReport, isDraftAssetPreview} from './draftContract';
import type {DraftAction, DraftReport, DraftValidation, DraftAssetReport, DraftAssetPreview} from './draftContract';
import type { IdentityReport, LogoutReport, PasswordChangeReport, StationReport, InspectionReport } from './contract';

export type StationResult<T> = Readonly<{status: 'AVAILABLE'; report: T}> | Readonly<{status: 'ACCESS_DENIED' | 'RATE_LIMITED' | 'UNAVAILABLE'; report: null}>;
type PasswordError = 'CURRENT_PASSWORD_INVALID' | 'PASSWORD_REJECTED';
type InspectionError = 'OPERATOR_REQUIRED' | 'INSPECTION_REJECTED' | 'IR_REJECTED';
type DraftError = 'OPERATOR_REQUIRED' | 'DRAFT_CONFLICT' | 'DRAFT_NOT_FOUND' | 'BAD_REQUEST';
export type DraftResult<T> = StationResult<T> | Readonly<{status: DraftError; report: null}>;
export type InspectionCommandResult = StationResult<StationReport> | Readonly<{status: InspectionError; report: null}>;
export type PasswordChangeResult = StationResult<PasswordChangeReport> | Readonly<{status: PasswordError; report: null}>;
export const stationTimeoutMs = 5000;
export const editorTimeoutMs = 35000;
const maxBytes = 4096;
const unavailable = {status: 'UNAVAILABLE', report: null} as const;

async function request<T, E extends PasswordError | InspectionError | DraftError = never>(path: string, validate: (value: unknown) => value is T, body?: string, errorCodes?: Partial<Record<number, E>>, limit = maxBytes, timeoutMs = stationTimeoutMs): Promise<StationResult<T> | Readonly<{status: E; report: null}>> {
  if (!globalThis.isSecureContext) return unavailable;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response | undefined;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const url = new URL(path, location.origin);
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST', mode: 'same-origin', credentials: 'same-origin',
      // Firefox also applies no-referrer to Origin on same-origin POSTs.
      // Preserve the browser-generated Origin required by the API's CSRF check.
      referrerPolicy: 'same-origin',
      redirect: 'error', cache: 'no-store', signal: controller.signal,
      headers: body === undefined ? {Accept: 'application/json'} : {Accept: 'application/json', 'Content-Type': 'application/json', 'X-Vision-Client': 'webgui'},
      ...(body === undefined ? {} : {body}),
    });
    if (response.redirected || response.url !== url.href) return unavailable;
    if (response.status === 401) return {status: 'ACCESS_DENIED', report: null};
    if (response.status === 429) return {status: 'RATE_LIMITED', report: null};
    if (response.status !== 200 && !errorCodes?.[response.status] || !/^application\/json\s*;\s*charset=utf-8$/i.test(response.headers.get('Content-Type') ?? '') || !response.body) return unavailable;
    const length = response.headers.get('Content-Length');
    if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > limit)) return unavailable;
    reader = response.body.getReader();
    const chunks: Uint8Array[] = []; let count = 0;
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > limit) return unavailable;
      chunks.push(value);
    }
    if (length !== null && Number(length) !== count) return unavailable;
    const bytes = new Uint8Array(count); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const value: unknown = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    controller.signal.throwIfAborted();
    if (response.status !== 200) {
      const code = errorCodes?.[response.status];
      return code && record(value, ['schema','code']) && value.schema === 'vision.api.error.v1' && value.code === code ? {status: code, report: null} : unavailable;
    }
    return validate(value) ? {status: 'AVAILABLE', report: value} : unavailable;
  } catch { return unavailable; }
  finally {
    controller.abort(); clearTimeout(timer);
    if (reader) { void reader.cancel().catch(() => {}); reader.releaseLock(); }
    if (response?.body && !response.body.locked && !response.bodyUsed) void response.body.cancel().catch(() => {});
  }
}
export function readIdentity(): Promise<StationResult<IdentityReport>> { return request<IdentityReport, never>('/api/v1/auth/session', isIdentityReport); }
export function readStation(): Promise<StationResult<StationReport>> { return request<StationReport, never>('/api/v1/station', isStationReport); }
export function signOut(): Promise<StationResult<LogoutReport>> { return request<LogoutReport, never>('/api/v1/auth/logout', isLogoutReport, '{}'); }
export function signIn(username: string, password: string): Promise<StationResult<IdentityReport>> {
  if (!usernameValid(username) || typeof password !== 'string' || password.length === 0 || new TextEncoder().encode(password).length > 1024) return Promise.resolve({status: 'ACCESS_DENIED', report: null});
  return request<IdentityReport, never>('/api/v1/auth/login', isIdentityReport, JSON.stringify({username, password}));
}
export function changePassword(currentPassword: string, newPassword: string): Promise<PasswordChangeResult> {
  return request('/api/v1/auth/password', isPasswordChangeReport, JSON.stringify({currentPassword, newPassword}),
    {400: 'PASSWORD_REJECTED', 403: 'CURRENT_PASSWORD_INVALID'} as const);
}

export function readNero():Promise<StationResult<NeroReport>>{
  return request<NeroReport,never>('/api/v1/devices/nero',isNeroReport,undefined,undefined,16384);
}

export async function readLuxonis(preview:boolean):Promise<StationResult<LuxonisReport>>{
  const result=await request<LuxonisReport,never>('/api/v1/devices/luxonis'+(preview?'/preview':''),isLuxonisReport,undefined,undefined,131072);
  if(result.status==='AVAILABLE'&&!preview&&Object.values(result.report.frames).some(f=>f!==null))return unavailable;
  return result;
}
export async function setLuxonisIR(instanceId:string,channel:IRChannel,enabled:boolean){
  const result=await request('/api/v1/devices/luxonis/ir',isIRResult,JSON.stringify({instanceId,channel,enabled}),
      {403:'OPERATOR_REQUIRED',409:'IR_REJECTED'} as const,4096,15000);
  if(result.status==='AVAILABLE'&&(result.report.instanceId!==instanceId||result.report.channel!==channel||result.report.enabled!==enabled))return unavailable;
  return result satisfies StationResult<IRResult>|Readonly<{status:'OPERATOR_REQUIRED'|'IR_REJECTED';report:null}>;
}

export function readInspection(): Promise<StationResult<InspectionReport>> {
  return request<InspectionReport, never>('/api/v1/inspection', isInspectionReport, undefined, undefined, 16384);
}
export function startInspection(instanceId: string, selectionId: string, intentToken: string): Promise<InspectionCommandResult> {
  return request('/api/v1/inspection/start', isStationReport, JSON.stringify({instanceId, selectionId, intentToken}),
    {403: 'OPERATOR_REQUIRED', 409: 'INSPECTION_REJECTED'} as const);
}
export function closeInspection(instanceId: string, sessionId: string): Promise<InspectionCommandResult> {
  return request('/api/v1/inspection/close', isStationReport, JSON.stringify({instanceId, sessionId}),
    {403: 'OPERATOR_REQUIRED', 409: 'INSPECTION_REJECTED'} as const);
}

const draftErrors = {400: 'BAD_REQUEST', 403: 'OPERATOR_REQUIRED', 404: 'DRAFT_NOT_FOUND', 409: 'DRAFT_CONFLICT'} as const;
function editorBody(args: Record<string,string>, document?: string): string {
  const base = JSON.stringify(args);
  return document === undefined ? base : base.slice(0,-1)+',"document":'+document+'}';
}
async function editorRequest<T extends DraftReport | DraftValidation | DraftAssetReport | DraftAssetPreview>(action: DraftAction, args: Record<string,string>,
    validate: (value: unknown) => value is T, document?: string): Promise<DraftResult<T>> {
  const body = editorBody(args,document);
  const assetWire=3*1024*1024;
  if (new TextEncoder().encode(body).length > (action==='asset_import'?assetWire:131072)) return {status:'BAD_REQUEST',report:null};
  const result = await request('/api/v1/library/editor/'+action,validate,body,draftErrors,action==='asset_preview'?assetWire:131072,editorTimeoutMs);
  if(result.status==='AVAILABLE'&&action==='open_generation'&&(!('snapshotId' in result.report)||result.report.snapshotId!==args.snapshotId))return unavailable;
  if(result.status==='AVAILABLE'&&action!=='open_generation'&&'snapshotId' in result.report)return unavailable;
  if(result.status==='AVAILABLE'&&['create_basic','save_basic','clone_basic'].includes(action)&&!('declaration' in result.report))return unavailable;
  if(result.status==='AVAILABLE'&&action==='publish_review'&&(!('lifecycle' in result.report)||result.report.lifecycle!=='RELEASED'))return unavailable;
  if(result.status==='AVAILABLE'&&action==='asset_preview'&&(!('assetId' in result.report)||result.report.assetId!==args.assetId))return unavailable;
  if (result.status === 'AVAILABLE' && (result.report.instanceId !== args.instanceId ||
      result.report.key !== ((action === 'clone'||action==='clone_basic') ? args.newKey : args.key))) return unavailable;
  return result;
}
export function editDraft(action: Exclude<DraftAction,'validate'|'validate_structure'|'asset_import'|'asset_preview'>, args: Record<string,string>, document?: string): Promise<DraftResult<DraftReport>> {
  return editorRequest(action,args,isDraftReport,document);
}
export function validateDraft(args: Record<string,string>, document: string): Promise<DraftResult<DraftValidation>> {
  return editorRequest('validate',args,isDraftValidation,document);
}

export function validateDraftStructure(args:Record<string,string>, document:string):Promise<DraftResult<DraftValidation>> {
  return editorRequest('validate_structure',args,isDraftValidation,document);
}
export function importDraftAsset(args:Record<string,string>):Promise<DraftResult<DraftAssetReport>> {
  return editorRequest('asset_import',args,isDraftAssetReport);
}
export function previewDraftAsset(args:Record<string,string>):Promise<DraftResult<DraftAssetPreview>> {
  return editorRequest('asset_preview',args,isDraftAssetPreview);
}
