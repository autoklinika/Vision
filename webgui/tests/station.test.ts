import { afterEach, expect, it, vi } from 'vitest';
import { isIdentityReport, isLogoutReport, isStationReport } from '../src/station/contract';
import { readIdentity, readStation, signIn, signOut, stationTimeoutMs } from '../src/station/transport';
import { identityFixture, stationFixture } from './fixtures/station';

const origin = 'http://127.0.0.1:18491';
function secure() { vi.stubGlobal('isSecureContext', true); vi.stubGlobal('location', new URL(origin)); }
function response(value: unknown, path: string, status = 200) {
  const result = new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json; charset=utf-8'}});
  Object.defineProperty(result, 'url', {value: origin + path}); return result;
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it('station and identity contracts are closed and do not turn missing Core into readiness', () => {
  expect(isIdentityReport(identityFixture())).toBe(true);
  expect(isStationReport(stationFixture())).toBe(true);
  expect(isStationReport(stationFixture(true))).toBe(true);
  expect(isStationReport({...stationFixture(), coreConnection: 'CONNECTED'})).toBe(false);
  expect(isLogoutReport({schema: 'vision.api.logout.v1', loggedOut: true})).toBe(true);
  for (const value of [
    {...identityFixture(), role: 'admin'}, {...identityFixture(), authenticated: false}, {...identityFixture(), token: 'private'},
    {...identityFixture(), username: 'operator\n'}, {...identityFixture(), username: 'name@example'}, {...identityFixture(), expiresAt: '2026-02-30T01:02:03Z'},
  ]) expect(isIdentityReport(value)).toBe(false);
  for (const value of [
    {...stationFixture(), source: 'SYNTHETIC_TEST'}, {...stationFixture(), coreReadiness: 'READY'}, {...stationFixture(), state: 'SESSION_ACTIVE'},
    {...stationFixture(true), coreConnection: 'NOT_CONNECTED'}, {...stationFixture(), sessionId: 'old'}, {...stationFixture(), extra: true},
    {...stationFixture(), instanceId: 'a'.repeat(31) + '\n'}, {...stationFixture(), coreConnection: ['CONNECTED']},
    {...stationFixture(true), sessionId: 'session\n'}, {...stationFixture(), libraryId: 'another-library'},
  ]) expect(isStationReport(value)).toBe(false);
  expect(isLogoutReport({schema: 'vision.api.logout.v1', loggedOut: true, token: 'private'})).toBe(false);
});

it('real login and logout use same-origin cookies and explicit JSON client headers', async () => {
  secure();
  const network = vi.fn().mockResolvedValueOnce(response(identityFixture(), '/api/v1/auth/login'))
    .mockResolvedValueOnce(response({schema: 'vision.api.logout.v1', loggedOut: true}, '/api/v1/auth/logout'));
  vi.stubGlobal('fetch', network);
  expect((await signIn('operator', 'test-only-password')).status).toBe('AVAILABLE');
  expect((await signOut()).status).toBe('AVAILABLE');
  expect(network.mock.calls.map(call => String(call[0]))).toEqual([origin + '/api/v1/auth/login', origin + '/api/v1/auth/logout']);
  for (const [, options] of network.mock.calls) expect(options).toMatchObject({method: 'POST', mode: 'same-origin', credentials: 'same-origin', redirect: 'error', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Vision-Client': 'webgui'}});
  expect(JSON.parse(network.mock.calls[0][1].body)).toEqual({username: 'operator', password: 'test-only-password'});
  expect(network.mock.calls[1][1].body).toBe('{}');
});

it('session resume and station reads accept only bounded validated same-origin reports', async () => {
  secure();
  const network = vi.fn().mockResolvedValueOnce(response(identityFixture(), '/api/v1/auth/session')).mockResolvedValueOnce(response(stationFixture(), '/api/v1/station'));
  vi.stubGlobal('fetch', network);
  expect((await readIdentity()).status).toBe('AVAILABLE'); expect((await readStation()).status).toBe('AVAILABLE');
  for (const [, options] of network.mock.calls) expect(options).toMatchObject({method: 'GET', credentials: 'same-origin', redirect: 'error'});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({...stationFixture(), coreReadiness: 'READY'}, '/api/v1/station')));
  expect(await readStation()).toEqual({status: 'UNAVAILABLE', report: null});
});

it('denials, rate limits and offline errors contain no reports or credential details', async () => {
  secure();
  for (const [status, expected] of [[401,'ACCESS_DENIED'], [403,'ACCESS_DENIED'], [429,'RATE_LIMITED'], [503,'UNAVAILABLE']] as const) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({private: 'never expose'}, '/api/v1/auth/login', status)));
    expect(await signIn('operator', 'test-only-password')).toEqual({status: expected, report: null});
  }
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private transport detail')));
  expect(await readIdentity()).toEqual({status: 'UNAVAILABLE', report: null});
});

it('insecure connections and invalid or oversized credentials send no request', async () => {
  secure(); const network = vi.fn(); vi.stubGlobal('fetch', network);
  for (const [username, password] of [['operator\n','test-only-password'], ['user@example','test-only-password'], ['operator',''], ['operator','😀'.repeat(257)]]) {
    expect((await signIn(username, password)).status).toBe('ACCESS_DENIED');
  }
  vi.stubGlobal('isSecureContext', false);
  expect((await signIn('operator','test-only-password')).status).toBe('UNAVAILABLE');
  expect((await readIdentity()).status).toBe('UNAVAILABLE'); expect((await readStation()).status).toBe('UNAVAILABLE'); expect((await signOut()).status).toBe('UNAVAILABLE');
  expect(network).not.toHaveBeenCalled();
});

it('authentication body reads keep a deadline and an aggregate byte bound', async () => {
  secure();
  const cancel = vi.fn();
  const oversized = new Response(new ReadableStream<Uint8Array>({start(controller) { controller.enqueue(new Uint8Array(4097)); }, cancel}), {headers: {'Content-Type': 'application/json; charset=utf-8'}});
  Object.defineProperty(oversized, 'url', {value: origin + '/api/v1/auth/session'});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(oversized));
  expect((await readIdentity()).status).toBe('UNAVAILABLE'); expect(cancel).toHaveBeenCalled();
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_url: URL, options: RequestInit) => {
    const result = new Response(new ReadableStream<Uint8Array>({start(controller) { options.signal!.addEventListener('abort', () => controller.error(new Error('private')), {once: true}); }}), {headers: {'Content-Type': 'application/json; charset=utf-8'}});
    Object.defineProperty(result, 'url', {value: origin + '/api/v1/auth/session'}); return Promise.resolve(result);
  }));
  const pending = readIdentity(); await vi.advanceTimersByTimeAsync(stationTimeoutMs);
  expect(await pending).toEqual({status: 'UNAVAILABLE', report: null});
});
