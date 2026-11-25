import { isEventsReport, isSessionReport, matchesSession } from './sessionContract';
import type { EventsReport, SessionReport } from './sessionContract';

export type ProtectedResult<T> = Readonly<{ status: 'AVAILABLE'; report: T }> |
  Readonly<{ status: 'ACCESS_DENIED' | 'UNAVAILABLE'; report: null }>;
export const maxProtectedBytes = 131072;
export const protectedTimeoutMs = 3000;

export async function requestProtected<T>(path: string, validate: (value: unknown) => value is T, timeoutMs = protectedTimeoutMs): Promise<ProtectedResult<T>> {
  if (!globalThis.isSecureContext) return {status: 'UNAVAILABLE', report: null};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response | undefined;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const url = new URL(path, location.origin);
    response = await fetch(url, {
      method: 'GET', mode: 'same-origin', credentials: 'same-origin', cache: 'no-store',
      redirect: 'error', signal: controller.signal, headers: {Accept: 'application/json'},
    });
    if (response.redirected || response.url !== url.href) throw new Error('unexpected URL');
    if (response.status === 401 || response.status === 403) return {status: 'ACCESS_DENIED', report: null};
    if (response.status !== 200 || !/^application\/json\s*;\s*charset=utf-8$/i.test(response.headers.get('Content-Type') ?? '') || !response.body) throw new Error('invalid response');
    const length = response.headers.get('Content-Length');
    if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > maxProtectedBytes)) throw new Error('invalid size');
    reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxProtectedBytes) throw new Error('response too large');
      chunks.push(value);
    }
    if (length !== null && Number(length) !== total) throw new Error('length mismatch');
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const value: unknown = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    controller.signal.throwIfAborted();
    if (!validate(value)) throw new Error('invalid report');
    return {status: 'AVAILABLE', report: value};
  } catch {
    return {status: 'UNAVAILABLE', report: null};
  } finally {
    controller.abort();
    if (reader) { void reader.cancel().catch(() => {}); reader.releaseLock(); }
    if (response?.body && !response.body.locked && !response.bodyUsed) void response.body.cancel().catch(() => {});
    clearTimeout(timer);
  }
}

export async function readSession(): Promise<ProtectedResult<SessionReport>> {
  return requestProtected('/api/v1/session', isSessionReport);
}
export async function readEvents(session: SessionReport, after: number): Promise<ProtectedResult<EventsReport>> {
  if (!isSessionReport(session) || !Number.isSafeInteger(after) || after < 0 || after > session.journalSequence) return {status: 'UNAVAILABLE', report: null};
  const path = `/api/v1/events?view=${session.viewId}&after=${after}&through=${session.journalSequence}`;
  return requestProtected(path, (value): value is EventsReport => isEventsReport(value) && matchesSession(value, session, after));
}
