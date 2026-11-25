import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { createClient } from '../src/api/client';
import { isBootStatus } from '../src/api/statusContract';
import { realAdapter, statusTimeoutMs } from '../src/api/realAdapter';

const fixtures = JSON.parse(readFileSync(new URL('../../contracts/vision-api/v1/status-fixtures.json', import.meta.url), 'utf8'));
const origin = 'http://127.0.0.1:4173';
const statusUrl = origin + '/api/v1/status';
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

function secure() {
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('location', new URL(origin));
}
function response(value: unknown, options: {status?: number; url?: string; type?: string; raw?: string} = {}) {
  const r = new Response(options.raw ?? JSON.stringify(value), {
    status: options.status ?? 200, headers: {'Content-Type': options.type ?? 'application/json; charset=utf-8'},
  });
  Object.defineProperty(r, 'url', {value: options.url ?? statusUrl});
  return r;
}
it('demo reads have no network and never report readiness', async () => {
  secure();
  const network = vi.fn(() => { throw Error('Network forbidden'); });
  vi.stubGlobal('fetch', network); vi.stubGlobal('WebSocket', network); vi.stubGlobal('XMLHttpRequest', network);
  const client = await createClient('demo');
  const a = await client.readSnapshot();
  expect(a).toEqual(await client.readSnapshot());
  expect(a.source).toBe('demo'); expect(a.readiness).toBe('UNKNOWN'); expect(a.observedAt).toBeNull();
  expect(Object.keys(client).sort()).toEqual(['mode','readSnapshot']);
  expect(network).not.toHaveBeenCalled();
});
it('invalid modes and insecure context fail closed without network or demo fallback', async () => {
  secure();
  const network = vi.fn();
  vi.stubGlobal('fetch', network);
  for (const mode of ['invalid', '', 'REAL']) {
    const s = await (await createClient(mode)).readSnapshot();
    expect(s).toMatchObject({source:'real',connection:'UNAVAILABLE',readiness:'UNKNOWN',reportTime:null,components:[]});
  }
  vi.stubGlobal('isSecureContext', false);
  expect((await realAdapter.readSnapshot()).connection).toBe('UNAVAILABLE');
  expect(network).not.toHaveBeenCalled();
});
it('shared fixtures validate narrowly', () => {
  expect(isBootStatus(fixtures.valid)).toBe(true);
  for (const testCase of fixtures.invalid) expect(isBootStatus(testCase.value), testCase.name).toBe(false);
});
it('real GET is same-origin, bounded, credential-free and API-only', async () => {
  secure();
  const network = vi.fn().mockResolvedValue(response(fixtures.valid));
  vi.stubGlobal('fetch', network);
  const s = await (await createClient('real')).readSnapshot();
  expect(s).toMatchObject({source:'real',connection:'API_AVAILABLE',readiness:'UNKNOWN',reportTime:fixtures.valid.reportTime,observedAt:null,components:[]});
  expect(network).toHaveBeenCalledTimes(1);
  const [url, init] = network.mock.calls[0];
  expect(String(url)).toBe(statusUrl);
  expect(init).toMatchObject({method:'GET',mode:'same-origin',credentials:'omit',cache:'no-store',redirect:'error'});
});
it('rejects malformed, oversized, bad content-type, other URL and HTTP error', async () => {
  secure();
  for (const r of [
    ...fixtures.invalid.map((c: {value:unknown}) => response(c.value)),
    response(fixtures.valid, {status:503}),
    response(fixtures.valid, {url:'https://untrusted.test/api/v1/status'}),
    response(fixtures.valid, {type:'text/html'}),
    response(null, {raw:'not json'}),
    response(null, {raw:'x'.repeat(4097)}),
  ]) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(r));
    const s = await realAdapter.readSnapshot();
    expect(s).toMatchObject({source:'real',connection:'UNAVAILABLE',readiness:'UNKNOWN',reportTime:null,components:[]});
  }
});
it('timeout returns an unavailable report with sanitized error', async () => {
  secure();
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_url: URL, init: RequestInit) => new Promise<Response>((_resolve,reject) => {
    init.signal!.addEventListener('abort', () => reject(Error('private detail')), {once:true});
  })));
  const pending = realAdapter.readSnapshot();
  await vi.advanceTimersByTimeAsync(statusTimeoutMs);
  const s = await pending;
  expect(s.connection).toBe('UNAVAILABLE');
  expect(s.reason).not.toContain('private detail');
});
it('each new read can recover; a failed read cannot retain an old successful report', async () => {
  secure();
  const network = vi.fn().mockResolvedValueOnce(response(fixtures.valid)).mockRejectedValueOnce(Error('private error')).mockResolvedValueOnce(response(fixtures.valid));
  vi.stubGlobal('fetch', network);
  expect((await realAdapter.readSnapshot()).connection).toBe('API_AVAILABLE');
  expect(await realAdapter.readSnapshot()).toMatchObject({connection:'UNAVAILABLE',reportTime:null});
  expect((await realAdapter.readSnapshot()).connection).toBe('API_AVAILABLE');
  expect(network).toHaveBeenCalledTimes(3);
});

it('cancels a rejected response before reading its body', async () => {
  secure();
  for (const kind of ['status', 'type', 'length', 'url']) {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({cancel});
    const r = new Response(stream, {
      status: kind === 'status' ? 503 : 200,
      headers: {
        'Content-Type': kind === 'type' ? 'text/plain' : 'application/json; charset=utf-8',
        ...(kind === 'length' ? {'Content-Length':'4097'} : {}),
      },
    });
    Object.defineProperty(r, 'url', {value: kind === 'url' ? 'https://untrusted.test/api/v1/status' : statusUrl});
    const network = vi.fn<(url: URL, init: RequestInit) => Promise<Response>>().mockResolvedValue(r);
    vi.stubGlobal('fetch', network);
    const s = await realAdapter.readSnapshot();
    expect(s).toMatchObject({connection:'UNAVAILABLE',readiness:'UNKNOWN',reportTime:null});
    expect(network.mock.calls[0][1].signal?.aborted).toBe(true);
    expect(cancel, kind).toHaveBeenCalledTimes(1);
  }
});

it('rejects an oversized streamed body with no declared content length', async () => {
  secure();
  const cancel = vi.fn();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) { controller.enqueue(new Uint8Array(4097)); },
    cancel,
  });
  const r = new Response(stream, {headers:{'Content-Type':'application/json; charset=utf-8'}});
  Object.defineProperty(r, 'url', {value:statusUrl});
  const network = vi.fn<(url: URL, init: RequestInit) => Promise<Response>>().mockResolvedValue(r);
  vi.stubGlobal('fetch', network);
  expect(await realAdapter.readSnapshot()).toMatchObject({connection:'UNAVAILABLE',reportTime:null});
  expect(cancel).toHaveBeenCalledTimes(1);
  expect(network.mock.calls[0][1].signal?.aborted).toBe(true);
});

it('keeps the timeout active after headers while awaiting the body', async () => {
  secure();
  vi.useFakeTimers();
  const network = vi.fn((_url: URL, init: RequestInit) => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        init.signal!.addEventListener('abort', () => controller.error(new Error('private detail')), {once:true});
      },
    });
    const r = new Response(stream, {headers:{'Content-Type':'application/json; charset=utf-8'}});
    Object.defineProperty(r, 'url', {value:statusUrl});
    return Promise.resolve(r);
  });
  vi.stubGlobal('fetch', network);
  const pending = realAdapter.readSnapshot();
  await vi.advanceTimersByTimeAsync(statusTimeoutMs);
  const s = await pending;
  expect(s).toMatchObject({connection:'UNAVAILABLE',readiness:'UNKNOWN',reportTime:null});
  expect(s.reason).not.toContain('private detail');
  expect(network.mock.calls[0][1].signal?.aborted).toBe(true);
});
