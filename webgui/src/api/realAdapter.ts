import type { ReadOnlyVisionClient, Snapshot } from './types';
import { isBootStatus } from './statusContract';

export const statusPath = '/api/v1/status';
export const maxStatusBytes = 4096;
export const statusTimeoutMs = 3000;

function unavailable(reason: string): Snapshot {
  return {
    schema: 'client-view-v1', source: 'real', connection: 'UNAVAILABLE',
    readiness: 'UNKNOWN', observedAt: null, reportTime: null,
    reason: 'Real adapter unavailable: ' + reason, components: [],
  };
}

async function readBounded(response: Response): Promise<unknown> {
  if (response.status !== 200 || !/^application\/json\s*;\s*charset=utf-8$/i.test(response.headers.get('Content-Type') ?? '') ||
      !response.body) throw new Error('invalid response');
  const length = response.headers.get('Content-Length');
  if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > maxStatusBytes)) {
    throw new Error('invalid response size');
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxStatusBytes) throw new Error('response too large');
      chunks.push(value);
    }
    if (length !== null && Number(length) !== total) throw new Error('length mismatch');
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function readSnapshot(): Promise<Snapshot> {
  if (!globalThis.isSecureContext) return unavailable('secure context required. Use HTTPS or loopback.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), statusTimeoutMs);
  let response: Response | undefined;
  try {
    const url = new URL(statusPath, location.origin);
    response = await fetch(url, {
      method: 'GET', mode: 'same-origin', credentials: 'omit', cache: 'no-store',
      redirect: 'error', signal: controller.signal, headers: {Accept: 'application/json'},
    });
    if (response.redirected || response.url !== url.href) throw new Error('unexpected response URL');
    const wire = await readBounded(response);
    controller.signal.throwIfAborted();
    if (!isBootStatus(wire)) throw new Error('invalid API-01 schema');
    return {
      schema: 'client-view-v1', source: 'real', connection: 'API_AVAILABLE',
      readiness: wire.coreReadiness, observedAt: wire.observedAt, reportTime: wire.reportTime,
      reason: 'CORE_REPORT_NOT_CONNECTED · API-only last report; no trusted Core or device report.',
      components: wire.components,
    };
  } catch {
    return unavailable('status request failed or response invalid. System state is UNKNOWN.');
  } finally {
    // Stop the underlying fetch even when headers or final URL fail validation
    // before we acquire a reader. Never leave an invalid body downloading.
    controller.abort();
    if (response?.body && !response.body.locked && !response.bodyUsed) {
      void response.body.cancel().catch(() => {});
    }
    clearTimeout(timer);
  }
}

export const realAdapter: ReadOnlyVisionClient = Object.freeze({
  mode: 'real', canRefresh: true, readSnapshot,
});
