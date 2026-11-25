import { isIdentityReport, isLogoutReport, isStationReport, usernameValid } from './contract';
import type { IdentityReport, LogoutReport, StationReport } from './contract';

export type StationResult<T> = Readonly<{status: 'AVAILABLE'; report: T}> | Readonly<{status: 'ACCESS_DENIED' | 'RATE_LIMITED' | 'UNAVAILABLE'; report: null}>;
export const stationTimeoutMs = 5000;
const maxBytes = 4096;
const unavailable = {status: 'UNAVAILABLE', report: null} as const;

async function request<T>(path: string, validate: (value: unknown) => value is T, body?: string): Promise<StationResult<T>> {
  if (!globalThis.isSecureContext) return unavailable;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), stationTimeoutMs);
  let response: Response | undefined;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const url = new URL(path, location.origin);
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST', mode: 'same-origin', credentials: 'same-origin',
      redirect: 'error', cache: 'no-store', signal: controller.signal,
      headers: body === undefined ? {Accept: 'application/json'} : {Accept: 'application/json', 'Content-Type': 'application/json', 'X-Vision-Client': 'webgui'},
      ...(body === undefined ? {} : {body}),
    });
    if (response.redirected || response.url !== url.href) return unavailable;
    if (response.status === 401 || response.status === 403) return {status: 'ACCESS_DENIED', report: null};
    if (response.status === 429) return {status: 'RATE_LIMITED', report: null};
    if (response.status !== 200 || !/^application\/json\s*;\s*charset=utf-8$/i.test(response.headers.get('Content-Type') ?? '') || !response.body) return unavailable;
    const length = response.headers.get('Content-Length');
    if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > maxBytes)) return unavailable;
    reader = response.body.getReader();
    const chunks: Uint8Array[] = []; let count = 0;
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > maxBytes) return unavailable;
      chunks.push(value);
    }
    if (length !== null && Number(length) !== count) return unavailable;
    const bytes = new Uint8Array(count); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const value: unknown = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    controller.signal.throwIfAborted();
    return validate(value) ? {status: 'AVAILABLE', report: value} : unavailable;
  } catch { return unavailable; }
  finally {
    controller.abort(); clearTimeout(timer);
    if (reader) { void reader.cancel().catch(() => {}); reader.releaseLock(); }
    if (response?.body && !response.body.locked && !response.bodyUsed) void response.body.cancel().catch(() => {});
  }
}
export function readIdentity(): Promise<StationResult<IdentityReport>> { return request('/api/v1/auth/session', isIdentityReport); }
export function readStation(): Promise<StationResult<StationReport>> { return request('/api/v1/station', isStationReport); }
export function signOut(): Promise<StationResult<LogoutReport>> { return request('/api/v1/auth/logout', isLogoutReport, '{}'); }
export function signIn(username: string, password: string): Promise<StationResult<IdentityReport>> {
  if (!usernameValid(username) || typeof password !== 'string' || password.length === 0 || new TextEncoder().encode(password).length > 1024) return Promise.resolve({status: 'ACCESS_DENIED', report: null});
  return request('/api/v1/auth/login', isIdentityReport, JSON.stringify({username, password}));
}
