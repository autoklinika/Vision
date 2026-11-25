import { afterEach, expect, it, vi } from 'vitest';
import { isIdentityReport, isLogoutReport, isPasswordChangeReport, isStationReport } from '../src/station/contract';
import { changePassword, readIdentity, readStation, signIn, signOut, stationTimeoutMs } from '../src/station/transport';
import { passwordChangeProblem } from '../src/station/password';
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
  expect(isStationReport(stationFixture(false, true))).toBe(true);
  expect(isStationReport(stationFixture(true))).toBe(true);
  expect(isLogoutReport({schema: 'vision.api.logout.v1', loggedOut: true})).toBe(true);
  for (const value of [
    {...identityFixture(), role: 'admin'}, {...identityFixture(), authenticated: false}, {...identityFixture(), token: 'private'},
    {...identityFixture(), username: 'operator\n'}, {...identityFixture(), username: 'name@example'}, {...identityFixture(), expiresAt: '2026-02-30T01:02:03Z'},
  ]) expect(isIdentityReport(value)).toBe(false);
  for (const value of [
    {...stationFixture(), source: 'SYNTHETIC_TEST'}, {...stationFixture(), coreReadiness: 'READY'}, {...stationFixture(), state: 'SESSION_ACTIVE'},
    {...stationFixture(false, true), sessionId: 'invented-session'}, {...stationFixture(false, true), sessionViewId: 'a'.repeat(32)},
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
  for (const [, options] of network.mock.calls) expect(options).toMatchObject({method: 'POST', mode: 'same-origin', credentials: 'same-origin', referrerPolicy: 'same-origin', redirect: 'error', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Vision-Client': 'webgui'}});
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
  for (const [status, expected] of [[401,'ACCESS_DENIED'], [403,'UNAVAILABLE'], [429,'RATE_LIMITED'], [503,'UNAVAILABLE']] as const) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({private: 'never expose'}, '/api/v1/auth/login', status)));
    expect(await signIn('operator', 'test-only-password')).toEqual({status: expected, report: null});
  }
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private transport detail')));
  expect(await readIdentity()).toEqual({status: 'UNAVAILABLE', report: null});
});

it('host and origin rejection never claim a wrong password or a confirmed sign-out', async () => {
  secure();
  for (const code of ['ORIGIN_REJECTED', 'HOST_REJECTED']) {
    const error = {schema: 'vision.api.error.v1', code};
    const network = vi.fn().mockResolvedValueOnce(response(error, '/api/v1/auth/login', 403))
      .mockResolvedValueOnce(response(error, '/api/v1/auth/logout', 403));
    vi.stubGlobal('fetch', network);
    expect((await signIn('operator', 'test-only-password')).status).toBe('UNAVAILABLE');
    expect((await signOut()).status).toBe('UNAVAILABLE');
  }
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

it('password changes send only the two secrets to the same-origin protected endpoint', async () => {
  secure();
  const report = {schema: 'vision.api.password-change.v1', changed: true};
  expect(isPasswordChangeReport(report)).toBe(true);
  for (const invalid of [{...report, changed: false}, {...report, username: 'operator'}, {...report, password: 'private'}]) expect(isPasswordChangeReport(invalid)).toBe(false);
  const network = vi.fn().mockResolvedValue(response(report, '/api/v1/auth/password'));
  vi.stubGlobal('fetch', network);
  expect(await changePassword('test-current-password', 'test-next-password')).toEqual({status: 'AVAILABLE', report});
  expect(String(network.mock.calls[0][0])).toBe(origin + '/api/v1/auth/password');
  expect(network.mock.calls[0][1]).toMatchObject({method: 'POST', mode: 'same-origin', credentials: 'same-origin', referrerPolicy: 'same-origin', redirect: 'error', cache: 'no-store', headers: {'Content-Type': 'application/json', 'X-Vision-Client': 'webgui'}});
  expect(JSON.parse(network.mock.calls[0][1].body)).toEqual({currentPassword: 'test-current-password', newPassword: 'test-next-password'});
});

it('only a closed, exact password error identifies the wrong current password', async () => {
  secure();
  for (const [status, code, expected] of [
    [403, 'CURRENT_PASSWORD_INVALID', 'CURRENT_PASSWORD_INVALID'], [400, 'PASSWORD_REJECTED', 'PASSWORD_REJECTED'],
    [403, 'ACCESS_DENIED', 'UNAVAILABLE'], [403, 'HOST_REJECTED', 'UNAVAILABLE'],
    [400, 'CURRENT_PASSWORD_INVALID', 'UNAVAILABLE'], [401, 'ACCESS_DENIED', 'ACCESS_DENIED'],
    [429, 'RATE_LIMITED', 'RATE_LIMITED'], [503, 'REPORT_UNAVAILABLE', 'UNAVAILABLE'],
  ] as const) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({schema: 'vision.api.error.v1', code}, '/api/v1/auth/password', status)));
    expect(await changePassword('test-current-password', 'test-next-password')).toEqual({status: expected, report: null});
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({schema: 'vision.api.error.v1', code: 'CURRENT_PASSWORD_INVALID', detail: 'private'}, '/api/v1/auth/password', 403)));
  expect(await changePassword('test-current-password', 'test-next-password')).toEqual({status: 'UNAVAILABLE', report: null});
  const network = vi.fn().mockRejectedValue(new Error('unconfirmed write'));
  vi.stubGlobal('fetch', network);
  expect(await changePassword('test-current-password', 'test-next-password')).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network).toHaveBeenCalledTimes(1);
});

it('password form validation matches Unicode character and UTF-8 byte policy', () => {
  expect(passwordChangeProblem('previous-password', '😀'.repeat(12), '😀'.repeat(12))).toBeNull();
  expect(passwordChangeProblem('previous-password', '😀'.repeat(11), '😀'.repeat(11))).toContain('12 characters');
  expect(passwordChangeProblem('previous-password', '😀'.repeat(256), '😀'.repeat(256))).toBeNull();
  expect(passwordChangeProblem('previous-password', '😀'.repeat(257), '😀'.repeat(257))).toContain('1024 UTF-8 bytes');
  expect(passwordChangeProblem('previous-password', 'next-long-password', 'different-password')).toContain('do not match');
  expect(passwordChangeProblem('previous-password', 'previous-password', 'previous-password')).toContain('different password');
  expect(passwordChangeProblem('', 'next-long-password', 'next-long-password')).toContain('current password');
});
