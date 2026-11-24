import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { eventsFixture, sessionFixture } from '../fixtures/session';
import { isEventsReport, isSessionReport, matchesSession } from '../../src/api/sessionContract';
import { enterDesktop } from './helpers';

const type = 'application/json; charset=utf-8';
const boot = JSON.parse(readFileSync(new URL('../../../contracts/vision-api/v1/status-fixtures.json', import.meta.url), 'utf8')).valid;
test.beforeEach(async ({page}) => { await page.route('**/local-brand/**', route => route.fulfill({status: 404, body: ''})); });

test('Core report windows share one read view, preserve ACK meaning, page and clear on denial', async ({page}) => {
  let session = sessionFixture();
  let denied = false;
  const reads: string[] = [];
  await page.route('**/api/v1/status', route => route.fulfill({contentType: type, body: JSON.stringify(boot)}));
  await page.route('**/api/v1/session', route => {
    reads.push(route.request().url());
    return route.fulfill({status: denied ? 401 : 200, contentType: type, body: JSON.stringify(denied ? {private: 'never display'} : session)});
  });
  await page.route('**/api/v1/events?*', route => {
    reads.push(route.request().url());
    return route.fulfill({contentType: type, body: JSON.stringify(eventsFixture(session, Number(new URL(route.request().url()).searchParams.get('after'))))});
  });
  await page.goto('/?mode=real');
  const startup = page.getByRole('dialog', {name: 'Vision Workstation Startup'});
  await expect(startup).toContainText('API AVAILABLE (last report)');
  await expect(startup.getByRole('button', {name: 'Refresh session'})).toHaveCount(0);
  expect(reads).toHaveLength(0);
  await enterDesktop(page);
  expect(reads).toHaveLength(0);
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  await status.getByRole('button', {name: 'Refresh session', exact: true}).click();
  await expect(status).toContainText('SYNTHETIC TEST · no station session');
  await expect(status).toContainText(session.sessionId);
  expect(reads).toHaveLength(2);
  await page.locator('.desktop-icons').getByRole('button', {name: 'Inspection Manager', exact: true}).click();
  const inspection = page.getByRole('dialog', {name: 'Inspection Manager', exact: true});
  const stages = inspection.getByRole('table', {name: 'Reported inspection stages'});
  await expect(stages.locator('tbody tr')).toHaveCount(11);
  const s02 = stages.getByRole('row').filter({has: page.getByRole('cell', {name: 'S02', exact: true})});
  await expect(s02).toContainText('RUNNING');
  await expect(s02).toContainText('70');
  expect(reads).toHaveLength(2);
  await page.locator('.desktop-icons').getByRole('button', {name: 'Event Viewer', exact: true}).click();
  const journal = page.getByRole('dialog', {name: 'Event Viewer', exact: true});
  await expect(journal.getByRole('table', {name: 'Reported session events'}).locator('tbody tr')).toHaveCount(50);
  await journal.getByRole('button', {name: 'Load more events'}).click();
  await expect(journal.getByRole('table', {name: 'Reported session events'}).locator('tbody tr')).toHaveCount(20);
  await expect(journal.getByRole('button', {name: 'Load more events'})).toBeDisabled();
  expect(reads[2]).toContain('&after=50&through=70');
  session = {...session, invalidated: true, stages: session.stages.map(stage => ({...stage, state: 'BLOCKED' as const}))};
  await journal.getByRole('button', {name: 'Refresh session'}).click();
  await expect(journal).toContainText('INVALIDATED');
  const s01 = stages.getByRole('row').filter({has: page.getByRole('cell', {name: 'S01', exact: true})});
  await expect(s01).toContainText('BLOCKED');
  await expect(s01).toContainText('Recorded');
  denied = true;
  await journal.getByRole('button', {name: 'Refresh session'}).click();
  await expect(journal).toContainText('Access denied');
  for (const dialog of [status, inspection, journal]) {
    await expect(dialog).not.toContainText(session.sessionId);
    await expect(dialog).not.toContainText('never display');
  }
  await expect(stages).toHaveCount(0);
  await expect(journal.getByRole('table', {name: 'Reported session events'})).toHaveCount(0);
});

test('protected disconnect and provider mismatch clear old data and a fresh report can recover', async ({page}) => {
  const session = sessionFixture();
  let failure: 'none' | 'disconnect' | 'owner' = 'none';
  await page.route('**/api/v1/status', route => route.fulfill({contentType: type, body: JSON.stringify(boot)}));
  await page.route('**/api/v1/session', route => route.fulfill({contentType: type, body: JSON.stringify(session)}));
  await page.route('**/api/v1/events?*', route => {
    if (failure === 'disconnect') return route.abort('failed');
    const report = eventsFixture(session);
    return route.fulfill({contentType: type, body: JSON.stringify(failure === 'owner' ? {...report, viewId: 'b'.repeat(32)} : report)});
  });
  await page.goto('/?mode=real'); await enterDesktop(page);
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  for (const next of ['none', 'disconnect', 'owner', 'none'] as const) {
    failure = next;
    await status.getByRole('button', {name: 'Refresh session'}).click();
    if (next === 'none') await expect(status).toContainText(session.sessionId);
    else { await expect(status).toContainText('Session report unavailable'); await expect(status).not.toContainText(session.sessionId); }
  }
});

test('demo and invalid modes cannot request protected reports from desktop windows', async ({page}) => {
  const protectedReads: string[] = [];
  await page.route('**/api/v1/**', route => { protectedReads.push(route.request().url()); return route.fulfill({status: 500}); });
  for (const mode of ['demo', 'invalid']) {
    await page.goto('/?mode=' + mode); await enterDesktop(page);
    for (const name of ['System Status', 'Inspection Manager', 'Event Viewer']) {
      await page.locator('.desktop-icons').getByRole('button', {name, exact: true}).click();
      await expect(page.getByRole('dialog', {name, exact: true}).getByRole('button', {name: 'Refresh session'})).toBeDisabled();
    }
  }
  expect(protectedReads).toEqual([]);
});

test('actual Core: authorized synthetic Workflow projection, pinned journal and browser reload', async ({page, context}) => {
  test.skip(process.env.VISION_PROJECTION_INTEGRATION !== '1', 'Synthetic Workflow fixture and test-only authorization are explicit opt-in.');
  const errors: string[] = [];
  const methods: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/v1/')) methods.push(request.method()); });
  await page.goto('/?mode=real'); await enterDesktop(page);
  const status = page.getByRole('dialog', {name: 'System Status', exact: true});
  const deniedResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/session');
  await status.getByRole('button', {name: 'Refresh session'}).click();
  expect((await deniedResponse).status()).toBe(401);
  await expect(status).toContainText('Access denied');
  const auth = JSON.parse(readFileSync('.api02-test-auth.json', 'utf8'));
  await context.addCookies([{name: auth.cookieName, value: auth.cookieValue, url: 'http://127.0.0.1:4173', httpOnly: true, sameSite: 'Strict'}]);
  const sessionResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/session');
  await status.getByRole('button', {name: 'Refresh session'}).click();
  const result = await sessionResponse;
  expect(result.status()).toBe(200);
  expect(result.headers()['cache-control']).toBe('no-store');
  const session: unknown = await result.json();
  expect(isSessionReport(session)).toBe(true);
  if (!isSessionReport(session)) throw new Error('Invalid test fixture session');
  expect(session.source).toBe('SYNTHETIC_TEST');
  await expect(status).toContainText('SYNTHETIC TEST · no station session');
  await page.locator('.desktop-icons').getByRole('button', {name: 'Inspection Manager', exact: true}).click();
  const inspection = page.getByRole('dialog', {name: 'Inspection Manager', exact: true});
  const table = inspection.getByRole('table', {name: 'Reported inspection stages'});
  await expect(table.getByRole('row').filter({has: page.getByRole('cell', {name: 'S01', exact: true})})).toContainText('SUCCEEDED');
  await expect(table.getByRole('row').filter({has: page.getByRole('cell', {name: 'S02', exact: true})})).toContainText('RUNNING');
  await expect(inspection.getByRole('button', {name: 'Start inspection'})).toHaveCount(0);
  await page.locator('.desktop-icons').getByRole('button', {name: 'Event Viewer', exact: true}).click();
  const journal = page.getByRole('dialog', {name: 'Event Viewer', exact: true});
  await expect(journal.getByRole('table', {name: 'Reported session events'}).locator('tbody tr')).toHaveCount(50);
  const pageResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/events');
  await journal.getByRole('button', {name: 'Load more events'}).click();
  const second: unknown = await (await pageResponse).json();
  expect(isEventsReport(second)).toBe(true);
  if (!isEventsReport(second)) throw new Error('Invalid test fixture page');
  expect(matchesSession(second, session, second.afterSequence)).toBe(true);
  await expect(journal.getByRole('table', {name: 'Reported session events'}).locator('tbody tr')).toHaveCount(second.events.length);
  await page.reload(); await enterDesktop(page);
  await page.locator('.desktop-icons').getByRole('button', {name: 'System Status', exact: true}).click();
  const reloadedResponse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/session');
  await status.getByRole('button', {name: 'Refresh session'}).click();
  const reloaded = await (await reloadedResponse).json();
  expect(reloaded).toMatchObject({viewId: session.viewId, journalSequence: session.journalSequence, stages: session.stages});
  await expect(status).toContainText(session.sessionId);
  expect(methods.every(method => method === 'GET')).toBe(true);
  expect(errors).toEqual([]);
});
