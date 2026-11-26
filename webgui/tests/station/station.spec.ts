import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { resolve } from 'node:path';
import { identityFixture, stationFixture } from '../fixtures/station';
import { libraryFixture, libraryDetailFixture, libraryHistoryFixture, draftEntry } from '../fixtures/library';
import { sessionFixture, eventsFixture } from '../fixtures/session';
import {luxonisFixture} from '../fixtures/luxonis';

const contentType = 'application/json; charset=utf-8';
async function login(page: Page, username: string, password: string) {
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await page.getByLabel('User name', {exact: true}).fill(username);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.locator('.vision-workspace')).toBeVisible();
}
async function fillPasswordChange(page: Page, current: string, next: string, confirmation = next) {
  const settings = page.locator('[data-module="settings"]');
  await settings.getByLabel('Current password', {exact: true}).fill(current);
  await settings.getByLabel('New password', {exact: true}).fill(next);
  await settings.getByLabel('Confirm new password', {exact: true}).fill(confirmation);
}
async function mockStation(page: Page) {
  const state = {authenticated: false, offline: false, coreConnected: true, active: false, revoked: false, logoutOffline: false,
    holdSession: null as null | (() => Promise<void>), libraryCount: 2, libraryView: 'c'.repeat(64), reads: [] as string[], writes: [] as string[], holdDetail: null as null | (() => Promise<void>),
    role: 'reader' as 'reader'|'operator', holdPassword: null as null | (() => Promise<void>), passwordResult: 'success' as 'success' | 'wrong' | 'rejected' | 'limited' | 'unconfirmed'};
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    if (route.request().method() === 'POST') state.writes.push(path); else state.reads.push(path + url.search);
    if (state.offline || path.endsWith('/logout') && state.logoutOffline) return route.abort('failed');
    const reply = (value: unknown, status = 200) => route.fulfill({status, contentType, body: JSON.stringify(value)});
    if (path === '/api/v1/auth/login') { state.authenticated = true; state.revoked = false; return reply({...identityFixture(),role:state.role}); }
    if (path === '/api/v1/auth/logout') { state.authenticated = false; return reply({schema: 'vision.api.logout.v1', loggedOut: true}); }
    if (!state.authenticated || state.revoked) return reply({schema: 'vision.api.error.v1', code: 'ACCESS_DENIED'}, 401);
    if (path === '/api/v1/auth/password') {
      if (state.holdPassword) await state.holdPassword();
      if (state.passwordResult === 'wrong') return reply({schema: 'vision.api.error.v1', code: 'CURRENT_PASSWORD_INVALID'}, 403);
      if (state.passwordResult === 'rejected') return reply({schema: 'vision.api.error.v1', code: 'PASSWORD_REJECTED'}, 400);
      if (state.passwordResult === 'limited') return reply({schema: 'vision.api.error.v1', code: 'RATE_LIMITED'}, 429);
      if (state.passwordResult === 'unconfirmed') return reply({schema: 'vision.api.error.v1', code: 'REPORT_UNAVAILABLE'}, 503);
      state.authenticated = false;
      return reply({schema: 'vision.api.password-change.v1', changed: true});
    }
    if (path === '/api/v1/auth/session') return reply({...identityFixture(),role:state.role});
    if (path === '/api/v1/station') return reply(stationFixture(state.coreConnected && state.active, state.coreConnected));
    const session = {...sessionFixture(), source: 'STATION', sessionId: 'station-session'} as const;
    if (!state.coreConnected && (path === '/api/v1/session' || path === '/api/v1/events')) return reply({schema: 'vision.api.error.v1', code: 'REPORT_UNAVAILABLE'}, 503);
    if (path === '/api/v1/session') {
      if (state.holdSession) await state.holdSession();
      return state.active ? reply(session) : reply({schema: 'vision.api.error.v1', code: 'NO_ACTIVE_SESSION'}, 409);
    }
    if (path === '/api/v1/events') return reply(eventsFixture(session, Number(url.searchParams.get('after'))));
    if (path.startsWith('/api/v1/library')) {
      if (!state.coreConnected) return reply({schema: 'vision.api.error.v1', code: 'REPORT_UNAVAILABLE'}, 503);
      if (state.holdDetail && path.endsWith(draftEntry.entryId)) { await state.holdDetail(); return reply({schema: 'vision.api.error.v1', code: 'ACCESS_DENIED'}, 401); }
      let data = path.endsWith('/history') ? libraryHistoryFixture(undefined, Number(url.searchParams.get('after'))) :
        path.includes('/entries/') ? libraryDetailFixture(path.endsWith(draftEntry.entryId) ? 'draft' : 'catalog') : libraryFixture(state.libraryCount, Number(url.searchParams.get('after')));
      if(path.includes('/entries/')&&!path.endsWith('/history')){
        const match=path.split('/').at(-1);
        for(let after=0;after<state.libraryCount;after+=50){
          const entry=libraryFixture(state.libraryCount,after).entries.find(item=>item.entryId===match);
          if(entry){data={...libraryDetailFixture(entry.kind==='REFERENCE_DRAFT'?'draft':'catalog'),entry};break;}
        }
      }
      return reply({...data, source: 'STATION', libraryId: 'vision-ecu-library', viewId: state.libraryView});
    }
    return reply({schema: 'vision.api.error.v1', code: 'NOT_FOUND'}, 404);
  });
  return state;
}

test('station build ignores demo URL, requires real login and reports missing Core truthfully', async ({page}) => {
  const state = await mockStation(page);
  state.coreConnected = false;
  await page.goto('/?mode=demo');
  await expect(page.locator('meta[name="vision-deployment"]')).toHaveAttribute('content', 'station');
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  expect(state.reads.every(path => path === '/api/v1/auth/session')).toBe(true);
  await login(page, 'operator', 'mock-password');
  const status = page.locator('[data-module="status"]');
  await expect(status).toContainText('Vision Core is not connected');
  await expect(status.locator('dd').filter({hasText: /^Unavailable$/})).toBeVisible();
  await expect(status).toContainText('Session report unavailable');
  await expect(status).not.toContainText('No active inspection session');
  await status.getByRole('button', {name: 'Refresh session'}).click();
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  await expect(page.locator('.mode-banner')).not.toContainText('DEMO');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Sign out', exact: true}).click();
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await expect(page.locator('.desktop')).toHaveCount(0);
  expect(state.writes).toEqual(['/api/v1/auth/login','/api/v1/auth/logout']);
});

test('connected idle Core creates no session and its outage clears library data without closing the desktop', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  const status = page.locator('[data-module="status"]');
  await expect(status).toContainText('No active inspection session');
  await expect(status.locator('.station-status-message')).toHaveCount(0);
  await expect(status.locator('.station-status-footer')).toHaveCount(0);
  await expect(status.getByText('Station information refreshes automatically. Closing this desktop leaves Vision running.',{exact:true})).toHaveCount(0);
  await expect(status).toContainText('Unknown');
  await expect(status.getByRole('button', {name: 'Refresh session'})).toBeDisabled();
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.locator('[data-module="ecu"]');
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  await library.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await expect(library.getByRole('region', {name: 'Library entry details'})).toBeVisible();
  state.coreConnected = false;
  await page.clock.fastForward(5100);
  await expect(status).toContainText('Vision Core is not connected');
  await expect(status).toContainText('Session report unavailable');
  await expect(status).not.toContainText('No active inspection session');
  await expect(page.locator('.desktop')).toBeVisible();
  await expect(page.getByRole('dialog', {name: 'Connection lost'})).toHaveCount(0);
  await expect(library).toContainText('Library report unavailable');
  await expect(library.getByRole('table', {name: 'ECU library entries'})).toHaveCount(0);
  await expect(library.getByRole('region', {name: 'Library entry details'})).toHaveCount(0);
  state.coreConnected = true;
  await page.clock.fastForward(5100);
  await expect(status).toContainText('No active inspection session');
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  await expect(library.getByRole('region', {name: 'Library entry details'})).toHaveCount(0);
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('station polling clears offline and revoked data, reconnects and follows active Core ownership', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  await expect(page.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  state.offline = true;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('dialog', {name: 'Connection lost'})).toBeVisible();
  await expect(page.locator('.desktop')).toBeHidden();
  await expect(page.getByRole('table')).toHaveCount(0);
  state.offline = false;
  await page.clock.fastForward(5100);
  await expect(page.locator('.vision-workspace')).toBeVisible();
  await expect(page.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  state.active = true;
  await page.clock.fastForward(5100);
  await expect(page.locator('[data-module="status"]')).toContainText('station-session');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Inspection Manager', exact: true}).click();
  await expect(page.getByRole('table', {name: 'Reported inspection stages'}).locator('tbody tr')).toHaveCount(11);
  state.coreConnected = false;
  await page.clock.fastForward(5100);
  const inspection = page.locator('[data-module="inspection"]');
  await expect(inspection).toContainText('Session report unavailable');
  await expect(inspection).not.toContainText('No active inspection session');
  await expect(page.getByRole('table', {name: 'Reported inspection stages'})).toHaveCount(0);
  state.coreConnected = true;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('table', {name: 'Reported inspection stages'}).locator('tbody tr')).toHaveCount(11);
  state.active = false;
  await page.clock.fastForward(5100);
  await expect(page.locator('[data-module="status"]')).toContainText('No active inspection session');
  await expect(page.getByRole('table', {name: 'Reported inspection stages'})).toHaveCount(0);
  await expect(page.locator('[data-module="inspection"]')).toContainText('No active inspection session');
  state.revoked = true;
  await page.clock.fastForward(5100);
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await expect(page.locator('.desktop')).toHaveCount(0);
  await expect(page.getByRole('table')).toHaveCount(0);
});

test('reconnecting to the same session keeps old stages hidden until a fresh report arrives', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  state.active = true;
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Inspection Manager', exact: true}).click();
  const stages = page.getByRole('table', {name: 'Reported inspection stages'});
  await expect(stages.locator('tbody tr')).toHaveCount(11);
  state.coreConnected = false;
  await page.clock.fastForward(5100);
  await expect(stages).toHaveCount(0);
  let releaseSession: (() => void) | undefined;
  state.holdSession = () => new Promise<void>(resolve => { releaseSession = resolve; });
  state.coreConnected = true;
  await page.clock.fastForward(5100);
  await expect.poll(() => releaseSession !== undefined).toBe(true);
  // Assert immediately, before the held request could expire and hide stale data.
  expect(await stages.count()).toBe(0);
  state.holdSession = null;
  releaseSession!();
  await expect(stages.locator('tbody tr')).toHaveCount(11);
});

test('automatic library refresh preserves valid selected detail and history page', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.locator('[data-module="ecu"]');
  await library.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await library.getByRole('tab', {name: 'Revision history (53)'}).click();
  await library.getByRole('button', {name: 'Next history page'}).click();
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(3);
  state.libraryView = '9'.repeat(64);
  await page.clock.fastForward(15100);
  await expect(library.getByRole('tab', {name: 'Revision history (53)'})).toHaveAttribute('aria-selected', 'true');
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(3);
  await expect.poll(() => state.reads.some(path => path.includes('view=' + state.libraryView) && path.includes('/history') && path.endsWith('after=50'))).toBe(true);
  state.libraryCount = 51;
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await library.getByRole('button', {name: 'Next entries'}).click();
  await expect(library).toContainText('51–51 of 51 entries');
  await page.clock.fastForward(15100);
  await expect(library).toContainText('51–51 of 51 entries');
});

test('late denial from a previous login cannot sign out a new login', async ({page}) => {
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  let release: (() => void) | undefined;
  state.holdDetail = () => new Promise<void>(resolve => { release = resolve; });
  await page.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await expect.poll(() => release !== undefined).toBe(true);
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Sign out', exact: true}).click();
  await login(page, 'operator', 'mock-password');
  state.holdDetail = null;
  const previousDenial = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(draftEntry.entryId) && response.status() === 401);
  release!();
  await previousDenial;
  await expect(page.locator('.vision-workspace')).toBeVisible();
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'System Status', exact: true}).click();
  await page.locator('[data-module="status"]').getByRole('button', {name: 'Refresh station'}).click();
  await expect(page.locator('.vision-workspace-status')).toContainText('Core connected');
});

test('unconfirmed logout hides protected data and retries without restoring the desktop', async ({page}) => {
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  state.logoutOffline = true;
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Sign out', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Vision sign out'})).toContainText('Sign-out is not confirmed yet');
  await expect(page.locator('.desktop')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Sign in', exact: true})).toHaveCount(0);
  state.logoutOffline = false;
  await page.getByRole('button', {name: 'Retry sign out'}).click();
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  expect(state.authenticated).toBe(false);
});

test('Settings validates locally, preserves login for a wrong current password and never stores form secrets', async ({page}) => {
  const state = await mockStation(page);
  state.passwordResult = 'wrong';
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  const settings = page.locator('[data-module="settings"]');
  await expect(settings).toContainText('Signed in as operator');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  await expect(settings).toHaveCount(1);
  await fillPasswordChange(page, 'test-current-password', 'short');
  await settings.getByRole('button', {name: 'Change password', exact: true}).click();
  await expect(settings).toContainText('Use at least 12 characters');
  await fillPasswordChange(page, 'test-current-password', 'test-next-password', 'mismatched-password');
  await settings.getByRole('button', {name: 'Change password', exact: true}).click();
  await expect(settings).toContainText('The new passwords do not match');
  await fillPasswordChange(page, 'test-current-password', 'test-current-password');
  await settings.getByRole('button', {name: 'Change password', exact: true}).click();
  await expect(settings).toContainText('Choose a different password');
  expect(state.writes).toEqual(['/api/v1/auth/login']);
  await fillPasswordChange(page, 'test-current-password', 'test-next-password');
  await settings.getByRole('button', {name: 'Change password', exact: true}).click();
  await expect(settings).toContainText('The current password is incorrect');
  await expect(page.locator('.desktop')).toBeVisible();
  for (const field of ['Current password', 'New password', 'Confirm new password']) await expect(settings.getByLabel(field, {exact: true})).toHaveValue('');
  for (const [result, message] of [['rejected', 'The new password was not accepted'], ['limited', 'Too many attempts']] as const) {
    state.passwordResult = result;
    await fillPasswordChange(page, 'test-current-password', 'test-next-password');
    await settings.getByRole('button', {name: 'Change password', exact: true}).click();
    await expect(settings).toContainText(message);
    await expect(page.locator('.desktop')).toBeVisible();
  }
  await fillPasswordChange(page, 'test-current-password', 'test-next-password');
  const stored = await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
  expect(stored).not.toContain('test-current-password'); expect(stored).not.toContain('test-next-password');
  await page.getByRole('button', {name: 'Close Settings', exact: true}).click();
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  for (const field of ['Current password', 'New password', 'Confirm new password']) await expect(settings.getByLabel(field, {exact: true})).toHaveValue('');
});

test('a pending password change survives closing Settings and late protected denial preserves its success message', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  let releasePassword: (() => void) | undefined, releaseDetail: (() => void) | undefined;
  state.holdPassword = () => new Promise<void>(resolve => { releasePassword = resolve; });
  state.holdDetail = () => new Promise<void>(resolve => { releaseDetail = resolve; });
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  const settings = page.locator('[data-module="settings"]');
  await fillPasswordChange(page, 'test-current-password', 'test-next-password');
  await settings.getByRole('button', {name: 'Change password', exact: true}).click();
  await expect.poll(() => releasePassword !== undefined).toBe(true);
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Sign out', exact: true})).toBeDisabled();
  await page.keyboard.press('Escape');
  await page.getByRole('button', {name: 'Close Settings', exact: true}).click();
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  await expect(settings.getByLabel('Current password', {exact: true})).toHaveValue('');
  await expect(settings.getByRole('button', {name: 'Changing password…', exact: true})).toBeDisabled();
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  await page.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await expect.poll(() => releaseDetail !== undefined).toBe(true);
  releasePassword!();
  const signIn = page.getByRole('dialog', {name: 'Welcome to Vision'});
  await expect(signIn).toContainText('Password changed. Sign in with your new password.');
  const denial = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(draftEntry.entryId) && response.status() === 401);
  releaseDetail!(); await denial;
  await page.clock.fastForward(15100);
  await expect(signIn).toContainText('Password changed. Sign in with your new password.');
  await expect(page.locator('.desktop')).toHaveCount(0);
  expect(state.writes.filter(path => path === '/api/v1/auth/password')).toHaveLength(1);
});

test('an unconfirmed password change requests explicit sign-in and never retries or resumes an old cookie', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  state.passwordResult = 'unconfirmed';
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
  await fillPasswordChange(page, 'test-current-password', 'test-next-password');
  await page.getByRole('button', {name: 'Change password', exact: true}).click();
  const signIn = page.getByRole('dialog', {name: 'Welcome to Vision'});
  await expect(signIn).toContainText('The password change could not be confirmed');
  await expect(signIn).toContainText('if it was not saved, use your previous password');
  expect(state.authenticated).toBe(true);
  const sessionReads = state.reads.filter(path => path === '/api/v1/auth/session').length;
  await page.clock.fastForward(45100);
  await expect(signIn).toContainText('The password change could not be confirmed');
  await expect(page.locator('.desktop')).toHaveCount(0);
  expect(state.reads.filter(path => path === '/api/v1/auth/session')).toHaveLength(sessionReads);
  expect(state.writes.filter(path => path === '/api/v1/auth/password')).toHaveLength(1);
  await expect(page.getByLabel('Password', {exact: true})).toHaveValue('');
});


test('TEST actual station: inspection blockers and password rotation preserve Core ownership', async ({page, browser, context}) => {
  const credentials = JSON.parse(readFileSync('../.station-test-auth.json', 'utf8'));
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const path of ['/.station-test-auth.json', '/%2estation-test-auth.json', '/@fs/' + resolve('../.station-test-auth.json') + '?raw']) {
    const body = await (await page.request.get(path)).text();
    expect(body.includes(credentials.password)).toBe(false);
    expect(body.includes('password')).toBe(false);
  }
  await page.goto('/?mode=demo');
  await login(page, credentials.username, credentials.password);
  // Reuse this real login: the shared fixture enforces the production limit
  // of five client login attempts per minute, including the password checks.
  const section = page.getByRole('region', {name: 'Inspection orchestration'});
  await expect(section).toContainText('Trusted Runtime composition is not configured.');
  await expect(section).toContainText('No approved ECU inspection recipe is available.');
  await expect(section).toContainText('Required device readiness is not verified.');
  await expect(section.getByRole('table').locator('tbody tr')).toHaveCount(4);
  await expect(section.getByRole('button', {name: 'Start inspection session'})).toHaveCount(0);
  const status = page.locator('[data-module="status"]');
  await expect(status).toContainText('No active inspection session');
  const core = await (await page.request.get('/api/v1/station')).json();
  expect(core).toMatchObject({coreConnection: 'CONNECTED', state: 'NO_ACTIVE_SESSION', sessionId: null, sessionViewId: null, coreReadiness: 'UNKNOWN'});
  expect((await context.cookies()).some(cookie => cookie.name === 'vision_session' && cookie.httpOnly && cookie.sameSite === 'Strict')).toBe(true);
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.locator('[data-module="ecu"]');
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(1);
  await expect(library).not.toContainText('SYNTHETIC');
  await library.getByRole('button', {name: 'Browse ETC3 v1', exact: true}).click();
  await expect(library).toContainText('Catalog record only');
  await page.screenshot({path: 'test-results/station-desktop.png'});
  const stored = await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
  expect(stored.includes(credentials.password)).toBe(false);
  expect(stored.includes('vision-ecu-library')).toBe(false);
  await page.reload();
  await expect(page.locator('.vision-workspace')).toBeVisible();
  await expect(page.getByLabel('Password', {exact: true})).toHaveCount(0);
  const secondContext = await browser.newContext({baseURL: 'http://127.0.0.1:18491'});
  const nextPassword = randomBytes(32).toString('base64url');
  let second: Page | undefined, passwordChanged = false;
  const jsonHeaders = {Origin: 'http://127.0.0.1:18491', 'X-Vision-Client': 'webgui'};
  try {
    second = await secondContext.newPage();
    await second.goto('/'); await login(second, credentials.username, credentials.password);
    await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
    await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Sign out', exact: true}).click();
    await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
    expect((await page.request.get('/api/v1/auth/session')).status()).toBe(401);
    const secondReport = await second.request.get('/api/v1/station');
    expect(secondReport.status()).toBe(200);
    expect(await secondReport.json()).toMatchObject({instanceId: core.instanceId, coreConnection: 'CONNECTED', state: 'NO_ACTIVE_SESSION'});
    // Reopen the first client so the change must revoke two independent cookies.
    await login(page, credentials.username, credentials.password);
    await second.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await second.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name: 'Settings', exact: true}).click();
    const settings = second.locator('[data-module="settings"]');
    await second.screenshot({path: 'test-results/station-settings.png'});
    await fillPasswordChange(second, 'wrong-test-password', nextPassword);
    await settings.getByRole('button', {name: 'Change password', exact: true}).click();
    await expect(settings).toContainText('The current password is incorrect');
    expect((await second.request.get('/api/v1/auth/session')).status()).toBe(200);
    second.on('response', response => {
      if (new URL(response.url()).pathname === '/api/v1/auth/password' && response.status() === 200) passwordChanged = true;
    });
    await fillPasswordChange(second, credentials.password, nextPassword);
    await settings.getByRole('button', {name: 'Change password', exact: true}).click();
    await expect(second.getByRole('dialog', {name: 'Welcome to Vision'})).toContainText('Password changed. Sign in with your new password.');
    expect(passwordChanged).toBe(true);
    expect((await second.request.get('/api/v1/auth/session')).status()).toBe(401);
    expect((await page.request.get('/api/v1/auth/session')).status()).toBe(401);
    await page.reload();
    await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
    await second.getByLabel('User name', {exact: true}).fill(credentials.username);
    await second.getByLabel('Password', {exact: true}).fill(credentials.password);
    await second.getByRole('button', {name: 'Sign in', exact: true}).click();
    await expect(second.getByRole('dialog', {name: 'Welcome to Vision'})).toContainText('Incorrect user name or password.');
    await login(second, credentials.username, nextPassword);
    expect(await (await second.request.get('/api/v1/station')).json()).toMatchObject({instanceId: core.instanceId, coreConnection: 'CONNECTED', state: 'NO_ACTIVE_SESSION'});
    const afterChange = await second.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
    expect(afterChange.includes(credentials.password)).toBe(false);
    expect(afterChange.includes(nextPassword)).toBe(false);
  } finally {
    try {
      // This is the generated, temporary fixture account. Restore it even if a
      // UI assertion fails after the write, so retries retain the same fixture.
      if (passwordChanged && second) {
        if ((await second.request.get('/api/v1/auth/session')).status() !== 200) {
          const recovery = await second.request.post('/api/v1/auth/login', {headers: jsonHeaders, data: {username: credentials.username, password: nextPassword}});
          expect(recovery.status()).toBe(200);
        }
        const restored = await second.request.post('/api/v1/auth/password', {headers: jsonHeaders, data: {currentPassword: nextPassword, newPassword: credentials.password}});
        expect(restored.status()).toBe(200);
      }
    } finally { await secondContext.close(); }
  }
  expect(errors).toEqual([]);
});

test('Fluent navigation is a left modal drawer 320px wide and closes on selection, Escape, backdrop and station loss', async ({page}) => {
  const state = await mockStation(page);
  await page.goto('/');
  await login(page, 'operator', 'mock-password');
  const trigger = page.getByRole('button', {name: 'Open navigation', exact: true});
  const drawer = page.getByRole('dialog', {name: 'Navigation', exact: true});
  await expect(drawer).toHaveCount(0);
  await trigger.click();
  await expect(drawer).toBeVisible();
  await expect(drawer).toHaveAttribute('aria-modal', 'true');
  await expect.poll(async () => Math.round((await drawer.boundingBox())?.width ?? 0)).toBe(320);
  await expect.poll(async () => Math.round((await drawer.boundingBox())?.x ?? -1)).toBe(0);
  await expect(drawer.getByRole('button', {name: 'System Status', exact: true})).toHaveAttribute('aria-current', 'page');
  await drawer.getByRole('button', {name: 'ECU Library', exact: true}).click();
  await expect(drawer).toHaveCount(0);
  await expect(page.locator('[data-module="ecu"]')).toBeVisible();
  await trigger.click();
  await expect(drawer.getByRole('button', {name: 'ECU Library', exact: true})).toHaveAttribute('aria-current', 'page');
  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
  await trigger.click();
  await drawer.getByRole('button', {name: 'Close navigation', exact: true}).click();
  await expect(drawer).toHaveCount(0);
  await trigger.click();
  await page.mouse.click(600, 100);
  await expect(drawer).toHaveCount(0);
  await trigger.click();
  state.offline = true;
  await expect(page.getByRole('dialog', {name: 'Connection lost'})).toBeVisible({timeout: 15000});
  await expect(drawer).toHaveCount(0);
});

test('private shell logo is the verified local original', async ({page}) => {
  test.skip(process.env.GUI_PRIVATE_SHELL_LOGO !== '1', 'Optional local original; no public asset.');
  await mockStation(page);
  await page.goto('/');
  await login(page, 'operator', 'mock-password');
  const logo = page.getByRole('img', {name: 'Original Vision logo', exact: true});
  await expect(logo).toBeVisible();
  await expect.poll(() => logo.evaluate((img: HTMLImageElement) => [img.naturalWidth,img.naturalHeight])).toEqual([800,100]);
  await expect(logo).toHaveAttribute('src', /^blob:/);
});

test('interface language changes live and persists without restarting authentication', async ({page}) => {
  const state=await mockStation(page);
  await page.addInitScript(()=>{ if(!localStorage.getItem('vision.ui.language.v1')) localStorage.setItem('vision.ui.language.v1','en'); });
  await page.goto('/');
  await login(page,'operator','mock-password');
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name:'Settings',exact:true}).click();
  const settings=page.locator('[data-module="settings"]');
  await settings.getByLabel('Interface language',{exact:true}).selectOption('pl');
  await expect(page.locator('html')).toHaveAttribute('lang','pl');
  await expect(settings.getByLabel('Język interfejsu',{exact:true})).toHaveValue('pl');
  await expect(page.getByRole('tab',{name:'Ustawienia',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Otwórz nawigację',exact:true}).click();
  const drawer=page.getByRole('dialog',{name:'Nawigacja',exact:true});
  await drawer.getByRole('button',{name:'Biblioteka ECU',exact:true}).click();
  await expect(page.locator('[data-module="ecu"]').getByRole('button',{name:'Nowy profil',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang','pl');
  await page.getByRole('tab',{name:'Ustawienia',exact:true}).click();
  await settings.getByLabel('Język interfejsu',{exact:true}).selectOption('en');
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(settings.getByLabel('Interface language',{exact:true})).toHaveValue('en');
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('Fluent system status presents only reported hardware/availability/readiness, updates in place and navigates without operations',async({page})=>{
  const state=await mockStation(page);
  await page.clock.install();
  const fixture=stationFixture(false,true);
  const observedAt='2026-11-25T12:00:00Z';
  let devices=[
    {device:'luxonis',hardwareConnection:'USB_DETECTED',availability:'ACTIVE',readiness:'UNKNOWN',observedAt},
    {device:'nero',hardwareConnection:'USB_CAN_DETECTED',availability:'ACTIVE',readiness:'NOT_READY',observedAt,readinessReason:'ARM_BRAKE_NOT_RELEASED'},
    {device:'moveit',hardwareConnection:'NOT_APPLICABLE',availability:'INACTIVE',readiness:'UNKNOWN',observedAt},
    {device:'sony',hardwareConnection:'USB_DETECTED',availability:'ACTIVE',readiness:'READY',observedAt},
  ];
  let pending=false;
  await page.route('**/api/v1/inspection',route=>pending?route.fulfill({status:503,contentType,body:JSON.stringify({schema:'vision.api.error.v1',code:'REPORT_UNAVAILABLE'})}):route.fulfill({contentType,body:JSON.stringify({
    schema:'vision.api.inspection.v1',source:'STATION',instanceId:fixture.instanceId,capturedAt:observedAt,sessionId:null,
    intentToken:'a'.repeat(32),devices,selections:[],blockers:['NO_APPROVED_SELECTION','DEVICES_NOT_VERIFIED'],startAllowed:false,closeAllowed:false,
  })}));
  await page.goto('/');await login(page,'operator','mock-password');
  const status=page.locator('[data-module="status"]');
  const table=status.getByRole('table',{name:'Devices and services'});
  await expect(status.getByRole('toolbar',{name:'Station actions'})).toBeVisible();
  await expect(table).toHaveClass(/fui-Table/);
  await expect(table.locator('tbody tr')).toHaveCount(4);
  await expect(table.getByRole('columnheader',{name:'Hardware connection'})).toBeVisible();
  await expect(table.locator('[data-device="luxonis"] [data-hardware-connection="USB_DETECTED"]')).toHaveText('USB detected');
  await expect(table.locator('[data-device="nero"] [data-hardware-connection="USB_CAN_DETECTED"]')).toHaveText('USB-CAN detected');
  await expect(table.locator('[data-device="moveit"] [data-hardware-connection="NOT_APPLICABLE"]')).toHaveText('Not applicable');
  await expect(table.locator('[data-device="luxonis"]')).toContainText('Active');
  await expect(table.locator('[data-device="luxonis"]')).toContainText('Unknown');
  await expect(table.locator('[data-device="nero"] [data-reported-state="NOT_READY"]')).toHaveText('Not ready');
  await expect(table.locator('[data-device="nero"] [data-readiness-reason="ARM_BRAKE_NOT_RELEASED"]')).toHaveText('Joint brakes not released');
  await expect(table.locator('[data-device="sony"] [data-reported-state="READY"]')).toHaveText('Ready');
  await expect(status).toContainText('Session start blocked');
  await expect(status).toContainText('No approved ECU inspection recipe is available.');
  await expect(status.getByRole('button',{name:'Start inspection session'})).toHaveCount(0);
  const original=await table.elementHandle();
  devices=devices.map(d=>d.device==='sony'?{...d,readiness:'NOT_READY',hardwareConnection:'USB_NOT_DETECTED'}:d.device==='nero'?{...d,hardwareConnection:'USB_CAN_NOT_DETECTED'}:d);
  await page.clock.fastForward(5100);
  await expect(table.locator('[data-device="sony"] [data-reported-state="NOT_READY"]')).toBeVisible();
  await expect(table.locator('[data-device="sony"] [data-hardware-connection="USB_NOT_DETECTED"]')).toHaveText('USB not detected');
  await expect(table.locator('[data-device="nero"] [data-hardware-connection="USB_CAN_NOT_DETECTED"]')).toHaveText('USB-CAN not detected');
  expect(await table.evaluate((element,previous)=>element===previous,original)).toBe(true);
  await original?.dispose();
  pending=true;
  await page.clock.fastForward(5100);
  await expect(table).toHaveCount(0);
  await expect(status).toContainText('Inspection readiness report unavailable. No session command is enabled.');
  pending=false;
  await page.clock.fastForward(5100);
  await expect(table.locator('tbody tr')).toHaveCount(4);

  // Existing workspace routing, not a session mutation.
  await status.getByRole('button',{name:'Open inspection manager'}).click();
  await expect(page.getByRole('tab',{name:'Inspection Manager',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(page.locator('[data-module="inspection"]')).toBeVisible();
  await page.getByRole('tab',{name:'System Status',exact:true}).click();
  await expect(table).toBeVisible();

  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Interface language',{exact:true}).selectOption('pl');
  await page.getByRole('tab',{name:'Stan systemu',exact:true}).click();
  const translated=status.getByRole('table',{name:'Urządzenia i usługi'});
  await expect(translated.getByRole('columnheader',{name:'Połączenie sprzętowe'})).toBeVisible();
  await expect(translated.locator('[data-device="luxonis"] [data-hardware-connection="USB_DETECTED"]')).toHaveText('Wykryto USB');
  await expect(translated.locator('[data-device="sony"] [data-hardware-connection="USB_NOT_DETECTED"]')).toHaveText('Nie wykryto USB');
  await expect(translated.locator('[data-device="nero"] [data-reported-state="NOT_READY"]')).toHaveText('Niegotowe');
  await expect(translated.locator('[data-device="nero"] [data-readiness-reason="ARM_BRAKE_NOT_RELEASED"]')).toHaveText('Hamulce przegubów niezwolnione');
  await expect(translated.locator('[data-device="nero"] [data-hardware-connection="USB_CAN_NOT_DETECTED"]')).toHaveText('Nie wykryto USB–CAN');
  await expect(status).toContainText('Rozpoczęcie sesji zablokowane');
  await expect(status.getByRole('button',{name:'Przejdź do menedżera inspekcji'})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  expect(await status.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  const area=translated.locator('..');
  expect(await area.evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('compact header keeps tabs beside the logo, closes the requested tab and supports keyboard and narrow screens', async ({page}) => {
  const state=await mockStation(page);
  await page.goto('/');
  await login(page,'operator','mock-password');
  const header=page.locator('.vision-topbar');
  const strip=header.getByRole('tablist',{name:'Open modules'});
  const drawer=page.getByRole('dialog',{name:'Navigation',exact:true});
  const open=async(name:string)=>{
    await header.getByRole('button',{name:'Open navigation',exact:true}).click();
    await drawer.getByRole('button',{name,exact:true}).click();
    await expect(drawer).toHaveCount(0);
  };
  await expect(strip).toBeVisible();
  await expect(header).not.toContainText('Core connected');
  await expect(page.locator('.vision-workspace-status')).toContainText('Core connected');
  expect(await page.locator('.vision-workspace').evaluate(el=>getComputedStyle(el).gridTemplateRows.split(' ').length)).toBe(3);
  await open('ECU Library');
  await open('Settings');
  const status=strip.getByRole('tab',{name:'System Status',exact:true});
  const library=strip.getByRole('tab',{name:'ECU Library',exact:true});
  const settings=strip.getByRole('tab',{name:'Settings',exact:true});
  const libraryClose=strip.getByRole('button',{name:'Close ECU Library',exact:true});
  await expect(settings).toHaveAttribute('aria-selected','true');
  await expect(page.locator('[data-module="settings"]')).toBeVisible();
  await page.mouse.move(10,200);
  await expect(libraryClose).toHaveCSS('opacity','0');
  await library.hover();
  await expect(libraryClose).toHaveCSS('opacity','1');
  await settings.click();
  await library.hover();
  await expect(strip.getByRole('button',{name:'Close Settings',exact:true})).toHaveCSS('opacity','0');
  await expect(libraryClose).toHaveCSS('opacity','1');
  await libraryClose.click();
  await expect(library).toHaveCount(0);
  await expect(settings).toHaveAttribute('aria-selected','true');
  await expect(page.locator('[data-module="settings"]')).toBeVisible();

  // An inactive tab can be reached by arrows, selected and closed via Delete.
  await settings.focus();
  await page.keyboard.press('ArrowLeft');
  await expect(status).toBeFocused();
  await expect(strip.getByRole('button',{name:'Close System Status',exact:true})).toHaveCSS('opacity','1');
  await page.keyboard.press('Enter');
  await expect(status).toHaveAttribute('aria-selected','true');
  await expect(status).toBeFocused();
  await expect(page.locator('[data-module="status"]')).toBeVisible();
  await page.keyboard.press('Delete');
  await expect(status).toHaveCount(0);
  await expect(settings).toBeFocused();
  await expect(settings).toHaveAttribute('aria-selected','true');

  await open('System Status');
  await open('ECU Library');
  await page.setViewportSize({width:390,height:844});
  await open('Event Viewer');
  await expect(strip.getByRole('tab',{name:'Event Viewer',exact:true})).toHaveAttribute('aria-selected','true');
  expect(await strip.evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const selected=strip.getByRole('tab',{name:'Event Viewer',exact:true});
  await expect.poll(()=>selected.evaluate(el=>{const a=el.getBoundingClientRect(),b=el.closest('.vision-workspace-tabs')!.getBoundingClientRect();return a.left>=b.left-1&&a.right<=b.right+1;})).toBe(true);
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('library searches all authorized pages, filters record type and browses the exact matching entry',async({page})=>{
  const state=await mockStation(page);
  state.libraryCount=101;
  await page.goto('/');
  await login(page,'operator','mock-password');
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name:'ECU Library',exact:true}).click();
  const library=page.locator('[data-module="ecu"]');
  const table=library.getByRole('table',{name:'ECU library entries'});
  const query=library.getByRole('textbox',{name:'Search ECU library',exact:true});
  await expect(table.locator('tbody tr')).toHaveCount(50);
  await query.fill('CATALOG_100');
  await library.getByRole('button',{name:'Search library',exact:true}).click();
  await expect(library).toContainText('Search results: 1 of 101');
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await table.getByRole('button',{name:'Browse Catalog 100 v1',exact:true}).click();
  await expect(library.getByRole('region',{name:'Library entry details'})).toContainText('Catalog 100');
  expect(state.reads.some(path=>path.includes('after=100'))).toBe(true);
  await query.fill('');
  await library.getByRole('combobox',{name:'Record type',exact:true}).selectOption('REFERENCE_DRAFT');
  await library.getByRole('button',{name:'Search library',exact:true}).click();
  await expect(library).toContainText('Search results: 1 of 101');
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.getByRole('button',{name:'Browse API-03 synthetic reference r1',exact:true})).toBeVisible();
  await library.getByRole('button',{name:'Clear search',exact:true}).click();
  await expect(table.locator('tbody tr')).toHaveCount(50);
  await expect(library).not.toContainText('Search results:');
  await query.fill('missing-profile');
  await library.getByRole('button',{name:'Search library',exact:true}).click();
  await expect(library).toContainText('No matching ECU entries.');
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('Devices Luxonis distinguishes saved settings and current frames, and stops polling preview when hidden',async({page})=>{
  const state=await mockStation(page);state.role='operator';
  let active=false,fail=false,previewReads=0,statusReads=0;
  await page.route('**/api/v1/devices/luxonis**',route=>{
    const preview=new URL(route.request().url()).pathname.endsWith('/preview');
    if(preview)previewReads++;else statusReads++;
    if(fail)return route.fulfill({status:503,contentType,body:JSON.stringify({schema:'vision.api.error.v1',code:'REPORT_UNAVAILABLE'})});
    return route.fulfill({contentType,body:JSON.stringify(luxonisFixture(active,preview))});
  });
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await login(page,'operator','mock-password');
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  const drawer=page.getByRole('dialog',{name:'Navigation',exact:true});
  const devices=drawer.getByRole('region',{name:'Devices',exact:true});
  await expect(devices.getByRole('button')).toHaveText(['Luxonis','NERO','Sony']);
  const workspace=drawer.getByRole('region',{name:'Workspace',exact:true});
  await expect(workspace.getByRole('button')).toHaveText(['System Status','ECU Library','Inspection Manager','Images']);
  await devices.getByRole('button',{name:'Luxonis',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Luxonis',exact:true})).toHaveAttribute('aria-selected','true');
  const panel=page.locator('[data-module="luxonis"]');
  await expect(panel).toContainText('Luxonis OAK-D Pro AF');
  await expect(panel).toContainText('USB detected');
  await expect(panel).toContainText('The camera node is not running');
  const select=panel.getByRole('combobox',{name:'Settings source',exact:true});
  await expect(select).toHaveValue('rgbd_lab');
  await select.selectOption('stereo800_lab');
  await expect(panel.getByRole('table',{name:'Stereo depth'})).toContainText('1280');
  await expect(panel).toContainText('Saved diagnostic configuration');
  await expect(panel.locator('.luxonis-image-viewport img')).toHaveCount(0);
  expect(previewReads).toBe(0);expect(statusReads).toBeGreaterThan(0);
  await panel.getByRole('button',{name:'Enable preview',exact:true}).click();
  active=true;
  await expect(panel.locator('.luxonis-image-viewport img')).toHaveCount(2);
  await expect.poll(()=>panel.locator('.luxonis-image-viewport img').first().evaluate((el:HTMLImageElement)=>el.naturalWidth)).toBe(32);
  await expect(panel.getByRole('region',{name:'RGB preview'})).toContainText('1920 × 1080');
  await select.selectOption('live');
  await expect(panel.getByRole('table',{name:'RGB camera'})).toContainText('15');
  await expect(panel).toContainText('/oak · ROS 186');
  fail=true;
  await expect(panel.locator('.luxonis-image-viewport img')).toHaveCount(0);
  await expect(panel).toContainText('Device report unavailable.');
  fail=false;
  await expect(panel.locator('.luxonis-image-viewport img')).toHaveCount(2);
  await page.getByRole('tab',{name:'System Status',exact:true}).click();
  await expect(panel).toBeHidden();
  await page.waitForTimeout(1200);
  const stopped=previewReads;await page.waitForTimeout(1100);
  expect(previewReads).toBe(stopped);
  await page.getByRole('tab',{name:'Luxonis',exact:true}).click();
  await expect(panel.getByRole('button',{name:'Enable preview',exact:true})).toBeEnabled();
  await expect(panel.locator('.luxonis-image-viewport img')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  expect(errors).toEqual([]);
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('Luxonis IR switches use independent verified readback and fixed command scope',async({page})=>{
  const state=await mockStation(page);state.role='operator';
  let dot=0,flood=0,reject=false;
  const commands:unknown[]=[];
  await page.route('**/api/v1/devices/luxonis**',async route=>{
    const now=Date.now()/1000;
    if(route.request().method()==='POST'){
      const body=route.request().postDataJSON();commands.push(body);
      expect(Object.keys(body).sort()).toEqual(['channel','enabled','instanceId']);
      if(reject)return route.fulfill({status:409,contentType,body:JSON.stringify({schema:'vision.api.error.v1',code:'IR_REJECTED'})});
      if(body.channel==='dot')dot=body.enabled ? 0.6 : 0;
      else if(body.channel==='flood')flood=body.enabled ? 0.6 : 0;
      else throw new Error('Unexpected IR command');
      return route.fulfill({contentType,body:JSON.stringify({schema:'vision.api.luxonis-ir.v1',source:'STATION',...body,dot,flood,capturedAt:now})});
    }
    const r=luxonisFixture(true,false,now);
    return route.fulfill({contentType,body:JSON.stringify({...r,settings:{...r.settings,'driver.i_enable_ir':true,
      'driver.r_laser_dot_intensity':dot,'driver.r_floodlight_intensity':flood},irControlAvailable:true})});
  });
  await page.goto('/');await login(page,'operator','mock-password');
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name:'Luxonis',exact:true}).click();
  const panel=page.locator('[data-module="luxonis"]');
  const laser=panel.getByRole('switch',{name:'IR dot projector',exact:true});
  const light=panel.getByRole('switch',{name:'IR flood illuminator',exact:true});
  await expect(laser).toBeEnabled();await expect(laser).not.toBeChecked();await expect(light).not.toBeChecked();
  await laser.click();await expect(laser).toBeChecked();await expect(light).not.toBeChecked();
  await expect(panel).toContainText('IR change confirmed by driver.');
  await expect(laser).toBeEnabled();
  await light.click();await expect(light).toBeChecked();await expect(laser).toBeChecked();
  await expect(light).toBeEnabled();
  reject=true;await laser.click();
  await expect(panel).toContainText('IR change rejected by Core.');
  await expect(laser).toBeChecked();
  expect(commands).toHaveLength(3);
  expect(commands).toEqual([
    {instanceId:'f'.repeat(32),channel:'dot',enabled:true},
    {instanceId:'f'.repeat(32),channel:'flood',enabled:true},
    {instanceId:'f'.repeat(32),channel:'dot',enabled:false}
  ]);
});
