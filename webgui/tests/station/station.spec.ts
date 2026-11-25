import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { identityFixture, stationFixture } from '../fixtures/station';
import { libraryFixture, libraryDetailFixture, libraryHistoryFixture, draftEntry } from '../fixtures/library';
import { sessionFixture, eventsFixture } from '../fixtures/session';

const contentType = 'application/json; charset=utf-8';
async function login(page: Page, username: string, password: string) {
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await page.getByLabel('User name', {exact: true}).fill(username);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'System Status', exact: true})).toBeVisible();
}
async function mockStation(page: Page) {
  const state = {authenticated: false, offline: false, coreConnected: true, active: false, revoked: false, logoutOffline: false,
    libraryCount: 2, libraryView: 'c'.repeat(64), reads: [] as string[], writes: [] as string[], holdDetail: null as null | (() => Promise<void>)};
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname;
    if (route.request().method() === 'POST') state.writes.push(path); else state.reads.push(path + url.search);
    if (state.offline || path.endsWith('/logout') && state.logoutOffline) return route.abort('failed');
    const reply = (value: unknown, status = 200) => route.fulfill({status, contentType, body: JSON.stringify(value)});
    if (path === '/api/v1/auth/login') { state.authenticated = true; state.revoked = false; return reply(identityFixture()); }
    if (path === '/api/v1/auth/logout') { state.authenticated = false; return reply({schema: 'vision.api.logout.v1', loggedOut: true}); }
    if (!state.authenticated || state.revoked) return reply({schema: 'vision.api.error.v1', code: 'ACCESS_DENIED'}, 401);
    if (path === '/api/v1/auth/session') return reply(identityFixture());
    if (path === '/api/v1/station') return reply(stationFixture(state.coreConnected && state.active, state.coreConnected));
    const session = {...sessionFixture(), source: 'STATION', sessionId: 'station-session'} as const;
    if (!state.coreConnected && (path === '/api/v1/session' || path === '/api/v1/events')) return reply({schema: 'vision.api.error.v1', code: 'REPORT_UNAVAILABLE'}, 503);
    if (path === '/api/v1/session') return state.active ? reply(session) : reply({schema: 'vision.api.error.v1', code: 'NO_ACTIVE_SESSION'}, 409);
    if (path === '/api/v1/events') return reply(eventsFixture(session, Number(url.searchParams.get('after'))));
    if (path.startsWith('/api/v1/library')) {
      if (!state.coreConnected) return reply({schema: 'vision.api.error.v1', code: 'REPORT_UNAVAILABLE'}, 503);
      if (state.holdDetail && path.endsWith(draftEntry.entryId)) { await state.holdDetail(); return reply({schema: 'vision.api.error.v1', code: 'ACCESS_DENIED'}, 401); }
      const data = path.endsWith('/history') ? libraryHistoryFixture(undefined, Number(url.searchParams.get('after'))) :
        path.includes('/entries/') ? libraryDetailFixture(path.endsWith(draftEntry.entryId) ? 'draft' : 'catalog') : libraryFixture(state.libraryCount, Number(url.searchParams.get('after')));
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
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  await expect(status).toContainText('Vision Core is not connected');
  await expect(status.locator('dd').filter({hasText: /^Unavailable$/})).toBeVisible();
  await expect(status).toContainText('Session report unavailable');
  await expect(status).not.toContainText('No active inspection session');
  await status.getByRole('button', {name: 'Refresh session'}).click();
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  await expect(page.locator('.mode-banner')).not.toContainText('DEMO');
  await page.getByRole('button', {name: 'Start', exact: true}).click();
  await page.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await expect(page.locator('.desktop')).toHaveCount(0);
  expect(state.writes).toEqual(['/api/v1/auth/login','/api/v1/auth/logout']);
});

test('connected idle Core creates no session and its outage clears library data without closing the desktop', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  await expect(status).toContainText('Vision Core is connected. No inspection session is active.');
  await expect(status).toContainText('Unknown');
  await expect(status.getByRole('button', {name: 'Refresh session'})).toBeDisabled();
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  await page.locator('.desktop-icons').getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('dialog', {name: 'ECU Library', exact: true});
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
  await expect(status).toContainText('Vision Core is connected. No inspection session is active.');
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  await expect(library.getByRole('region', {name: 'Library entry details'})).toHaveCount(0);
  expect(state.reads.some(path => path === '/api/v1/session' || path.startsWith('/api/v1/events'))).toBe(false);
  expect(state.writes).toEqual(['/api/v1/auth/login']);
});

test('station polling clears offline and revoked data, reconnects and follows active Core ownership', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.locator('.desktop-icons').getByRole('button', {name: 'ECU Library', exact: true}).click();
  await expect(page.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  state.offline = true;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('dialog', {name: 'Connection lost'})).toBeVisible();
  await expect(page.locator('.desktop')).toHaveCount(0);
  state.offline = false;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('dialog', {name: 'System Status', exact: true})).toBeVisible();
  await expect(page.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  state.active = true;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('dialog', {name: 'System Status', exact: true})).toContainText('station-session');
  await page.locator('.desktop-icons').getByRole('button', {name: 'Inspection Manager', exact: true}).click();
  await expect(page.getByRole('table', {name: 'Reported inspection stages'}).locator('tbody tr')).toHaveCount(11);
  state.coreConnected = false;
  await page.clock.fastForward(5100);
  const inspection = page.getByRole('dialog', {name: 'Inspection Manager', exact: true});
  await expect(inspection).toContainText('Session report unavailable');
  await expect(inspection).not.toContainText('No active inspection session');
  await expect(page.getByRole('table', {name: 'Reported inspection stages'})).toHaveCount(0);
  state.coreConnected = true;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('table', {name: 'Reported inspection stages'}).locator('tbody tr')).toHaveCount(11);
  state.active = false;
  await page.clock.fastForward(5100);
  await expect(page.getByRole('dialog', {name: 'System Status', exact: true})).toContainText('Vision Core is connected. No inspection session is active.');
  await expect(page.getByRole('table', {name: 'Reported inspection stages'})).toHaveCount(0);
  await expect(page.getByRole('dialog', {name: 'Inspection Manager', exact: true})).toContainText('No active inspection session');
  state.revoked = true;
  await page.clock.fastForward(5100);
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  await expect(page.locator('.desktop')).toHaveCount(0);
  await expect(page.getByRole('table')).toHaveCount(0);
});

test('automatic library refresh preserves valid selected detail and history page', async ({page}) => {
  await page.clock.install();
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  await page.locator('.desktop-icons').getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('dialog', {name: 'ECU Library', exact: true});
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
  await page.locator('.desktop-icons').getByRole('button', {name: 'ECU Library', exact: true}).click();
  let release: (() => void) | undefined;
  state.holdDetail = () => new Promise<void>(resolve => { release = resolve; });
  await page.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await expect.poll(() => release !== undefined).toBe(true);
  await page.getByRole('button', {name: 'Start', exact: true}).click();
  await page.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
  await login(page, 'operator', 'mock-password');
  state.holdDetail = null;
  const previousDenial = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(draftEntry.entryId) && response.status() === 401);
  release!();
  await previousDenial;
  await expect(page.getByRole('dialog', {name: 'System Status', exact: true})).toBeVisible();
  await page.locator('.desktop-icons').getByRole('button', {name: 'System Status', exact: true}).click();
  await page.getByRole('dialog', {name: 'System Status', exact: true}).getByRole('button', {name: 'Refresh station'}).click();
  await expect(page.locator('.mode-banner')).toContainText('CONNECTED · VENTUNO');
});

test('unconfirmed logout hides protected data and retries without restoring the desktop', async ({page}) => {
  const state = await mockStation(page);
  await page.goto('/'); await login(page, 'operator', 'mock-password');
  state.logoutOffline = true;
  await page.getByRole('button', {name: 'Start', exact: true}).click();
  await page.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Vision sign out'})).toContainText('Sign-out is not confirmed yet');
  await expect(page.locator('.desktop')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Sign in', exact: true})).toHaveCount(0);
  state.logoutOffline = false;
  await page.getByRole('button', {name: 'Retry sign out'}).click();
  await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
  expect(state.authenticated).toBe(false);
});

test('TEST actual station: login, cookie resume, two independent clients and logout', async ({page, browser, context}) => {
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
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  await expect(status).toContainText('Vision Core is connected. No inspection session is active.');
  const core = await (await page.request.get('/api/v1/station')).json();
  expect(core).toMatchObject({coreConnection: 'CONNECTED', state: 'NO_ACTIVE_SESSION', sessionId: null, sessionViewId: null, coreReadiness: 'UNKNOWN'});
  expect((await context.cookies()).some(cookie => cookie.name === 'vision_session' && cookie.httpOnly && cookie.sameSite === 'Strict')).toBe(true);
  await page.locator('.desktop-icons').getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('dialog', {name: 'ECU Library', exact: true});
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(1);
  await expect(library).not.toContainText('SYNTHETIC');
  await library.getByRole('button', {name: 'Browse ETC3 v1', exact: true}).click();
  await expect(library).toContainText('Catalog record only');
  await page.screenshot({path: 'test-results/station-desktop.png'});
  const stored = await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
  expect(stored.includes(credentials.password)).toBe(false);
  expect(stored.includes('vision-ecu-library')).toBe(false);
  await page.reload();
  await expect(status).toBeVisible();
  await expect(page.getByLabel('Password', {exact: true})).toHaveCount(0);
  const secondContext = await browser.newContext({baseURL: 'http://127.0.0.1:18491'});
  try {
    const second = await secondContext.newPage();
    await second.goto('/'); await login(second, credentials.username, credentials.password);
    await page.getByRole('button', {name: 'Start', exact: true}).click();
    await page.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
    await expect(page.getByLabel('User name', {exact: true})).toBeEnabled();
    expect((await page.request.get('/api/v1/auth/session')).status()).toBe(401);
    const secondReport = await second.request.get('/api/v1/station');
    expect(secondReport.status()).toBe(200);
    expect(await secondReport.json()).toMatchObject({instanceId: core.instanceId, coreConnection: 'CONNECTED', state: 'NO_ACTIVE_SESSION'});
    await second.getByRole('button', {name: 'Start', exact: true}).click();
    await second.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
    await expect(second.getByLabel('User name', {exact: true})).toBeEnabled();
  } finally { await secondContext.close(); }
  expect(errors).toEqual([]);
});
