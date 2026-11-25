import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { createClient } from '../src/api/client';
import { readEvents, readSession, maxProtectedBytes, protectedTimeoutMs } from '../src/api/protectedAdapter';
import { isEventsReport, isSessionReport, matchesSession } from '../src/api/sessionContract';
import { eventsFixture, sessionFixture } from './fixtures/session';

const origin = 'http://127.0.0.1:4173';
const sessionUrl = origin + '/api/v1/session';
const type = 'application/json; charset=utf-8';
const eventsUrl = origin + '/api/v1/events?view=' + 'a'.repeat(32) + '&after=0&through=70';
function secure() { vi.stubGlobal('isSecureContext', true); vi.stubGlobal('location', new URL(origin)); }
function response(value: unknown, options: {status?: number; url?: string; type?: string; raw?: string; length?: string} = {}) {
  const r = new Response(options.raw ?? JSON.stringify(value), {
    status: options.status ?? 200,
    headers: {'Content-Type': options.type ?? type, ...(options.length !== undefined ? {'Content-Length': options.length} : {})},
  });
  Object.defineProperty(r, 'url', {value: options.url ?? sessionUrl});
  return r;
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('accepts the shared backend contract fixtures', () => {
  const shared = JSON.parse(readFileSync(new URL('../../contracts/vision-api/v1/session-fixtures.json', import.meta.url), 'utf8'));
  expect(isSessionReport(shared.session)).toBe(true);
  expect(isEventsReport(shared.events)).toBe(true);
  expect(matchesSession(shared.events, shared.session, 0)).toBe(true);
});

it('closed session schema accepts extra scenario stages and separate historical success', () => {
  const session = sessionFixture();
  expect(isSessionReport(session)).toBe(true);
  expect(isSessionReport({...session, invalidated: true, stages: session.stages.map(stage => ({...stage, state: 'BLOCKED'}))})).toBe(true);
  expect(isSessionReport({...session, stages: [...session.stages, {...session.stages[2], id: 'T01'}]})).toBe(true);
  for (const value of [
    {...session, readiness: 'READY'}, {...session, source: 'DEMO'}, {...session, capturedAt: '2026-02-30T01:02:03Z'},
    {...session, journalSequence: Number.MAX_SAFE_INTEGER + 1}, {...session, journalSequence: -1},
    {...session, invalidated: true},
    {...session, sessionId: '/private/path'}, {...session, viewId: 'A'.repeat(32)},
    {...session, stages: session.stages.slice(1)}, {...session, stages: [...session.stages, session.stages[0]]},
    {...session, stages: [{...session.stages[0], state: 'ACK'}, ...session.stages.slice(1)]},
    {...session, stages: [{...session.stages[0], historicalSuccess: false}, ...session.stages.slice(1)]},
    {...session, stages: [{...session.stages[0], lastAckSequence: 71}, ...session.stages.slice(1)]},
    {...session, stages: [{...session.stages[0], private: 'not allowed'}, ...session.stages.slice(1)]},
  ]) expect(isSessionReport(value)).toBe(false);
});

it('closed event schema enforces bounds, ordering, completion and owner correlation', () => {
  const session = sessionFixture();
  const page = eventsFixture();
  expect(isEventsReport(page)).toBe(true);
  expect(isEventsReport(eventsFixture(session, 50))).toBe(true);
  expect(matchesSession(page, session, 0)).toBe(true);
  for (const value of [
    {...page, nextAfterSequence: null}, {...page, nextAfterSequence: 49}, {...page, events: [...page.events, page.events[0]]},
    {...page, events: [{...page.events[0], data: {private: true}}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], kind: 'secret event detail'}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], sequence: 0}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], state: 'ACK'}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], state: 'SUCCEEDED'}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], kind: 'transition', state: null}, ...page.events.slice(1)]},
    {...page, events: [{...page.events[0], kind: 'localization_accepted', state: 'RUNNING'}, ...page.events.slice(1)]},
  ]) expect(isEventsReport(value)).toBe(false);
  expect(matchesSession({...page, viewId: 'b'.repeat(32)}, session, 0)).toBe(false);
  expect(matchesSession({...page, sessionId: 'another-session'}, session, 0)).toBe(false);
  expect(matchesSession({...page, source: 'STATION'}, session, 0)).toBe(false);
  expect(matchesSession({...page, throughSequence: 71}, session, 0)).toBe(false);
  expect(matchesSession(page, session, 1)).toBe(false);
});

it('protected reads use fixed same-origin GET and server cookies without JS credentials', async () => {
  secure();
  const network = vi.fn().mockResolvedValueOnce(response(sessionFixture())).mockResolvedValueOnce(response(eventsFixture(), {url: eventsUrl}));
  vi.stubGlobal('fetch', network);
  const session = await readSession();
  expect(session.status).toBe('AVAILABLE');
  expect((await readEvents(sessionFixture(), 0)).status).toBe('AVAILABLE');
  expect(network.mock.calls.map(call => String(call[0]))).toEqual([sessionUrl, eventsUrl]);
  for (const [, init] of network.mock.calls) expect(init).toMatchObject({
    method: 'GET', mode: 'same-origin', credentials: 'same-origin', redirect: 'error', cache: 'no-store',
    headers: {Accept: 'application/json'},
  });
});

it('demo and invalid clients expose no protected read capability and insecure context sends nothing', async () => {
  secure();
  const network = vi.fn(); vi.stubGlobal('fetch', network);
  for (const mode of ['demo', 'invalid', '', 'REAL']) {
    const client = await createClient(mode);
    expect(client.readSession).toBeUndefined(); expect(client.readEvents).toBeUndefined();
  }
  vi.stubGlobal('isSecureContext', false);
  expect(await readSession()).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network).not.toHaveBeenCalled();
});

it('denial, transport errors and invalid reports retain no protected result', async () => {
  secure();
  for (const code of [401, 403]) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({private: 'secret'}, {status: code})));
    expect(await readSession()).toEqual({status: 'ACCESS_DENIED', report: null});
  }
  for (const r of [
    response(sessionFixture(), {status: 503}), response({...sessionFixture(), source: 'DEMO'}),
    response(null, {raw: 'not json'}), response(sessionFixture(), {type: 'text/html'}),
    response(sessionFixture(), {url: 'https://invalid.test/api/v1/session'}),
    response(sessionFixture(), {length: '1'}), response(sessionFixture(), {length: String(maxProtectedBytes + 1)}),
  ]) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(r));
    expect(await readSession()).toEqual({status: 'UNAVAILABLE', report: null});
  }
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private transport detail')));
  expect(await readSession()).toEqual({status: 'UNAVAILABLE', report: null});
});

it('a stale page from another provider or cursor is rejected and invalid cursors send nothing', async () => {
  secure();
  const network = vi.fn().mockResolvedValue(response({...eventsFixture(), viewId: 'b'.repeat(32)}, {url: eventsUrl}));
  vi.stubGlobal('fetch', network);
  expect(await readEvents(sessionFixture(), 0)).toEqual({status: 'UNAVAILABLE', report: null});
  for (const after of [-1, 71, 1.2, NaN, Number.MAX_SAFE_INTEGER + 1]) expect(await readEvents(sessionFixture(), after)).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network).toHaveBeenCalledTimes(1);
});

it('cancels early rejected bodies and streamed oversized data', async () => {
  secure();
  for (const status of [401, 200]) {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({start(controller) { if (status === 200) controller.enqueue(new Uint8Array(maxProtectedBytes + 1)); }, cancel});
    const r = new Response(stream, {status, headers: {'Content-Type': type}});
    Object.defineProperty(r, 'url', {value: sessionUrl});
    const network = vi.fn<(url: URL, init: RequestInit) => Promise<Response>>().mockResolvedValue(r);
    vi.stubGlobal('fetch', network);
    expect((await readSession()).status).toBe(status === 401 ? 'ACCESS_DENIED' : 'UNAVAILABLE');
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(network.mock.calls[0][1].signal?.aborted).toBe(true);
  }
});

it('keeps a three-second deadline while a protected body stalls', async () => {
  secure(); vi.useFakeTimers();
  const network = vi.fn((_url: URL, init: RequestInit) => {
    const stream = new ReadableStream<Uint8Array>({start(controller) { init.signal!.addEventListener('abort', () => controller.error(Error('private')), {once: true}); }});
    const r = new Response(stream, {headers: {'Content-Type': type}});
    Object.defineProperty(r, 'url', {value: sessionUrl});
    return Promise.resolve(r);
  });
  vi.stubGlobal('fetch', network);
  const pending = readSession();
  await vi.advanceTimersByTimeAsync(protectedTimeoutMs);
  expect(await pending).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network.mock.calls[0][1].signal?.aborted).toBe(true);
});
