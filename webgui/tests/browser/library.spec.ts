import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { isLibraryDetail, isLibraryHistory, isLibraryReport, matchesLibraryDetail, matchesLibraryHistory } from '../../src/api/libraryContract';
import { catalogEntry, draftEntry, libraryDetailFixture, libraryFixture, libraryHistoryFixture } from '../fixtures/library';
import { assertPrivateFixtureFile, enterDesktop } from './helpers';

const type = 'application/json; charset=utf-8';
const boot = JSON.parse(readFileSync(new URL('../../../contracts/vision-api/v1/status-fixtures.json', import.meta.url), 'utf8')).valid;
test.beforeEach(async ({page}) => { await page.route('**/local-brand/**', route => route.fulfill({status: 404, body: ''})); });

test('library browsing is explicit, separates catalog and drafts, and clears protected data on denial', async ({page}) => {
  const reads: string[] = [];
  let denied = false;
  await page.route('**/api/v1/status', route => route.fulfill({contentType: type, body: JSON.stringify(boot)}));
  await page.route(/\/api\/v1\/library(?:\/|\?|$)/, route => {
    const url = new URL(route.request().url()); reads.push(url.pathname + url.search);
    expect(route.request().method()).toBe('GET');
    if (denied) return route.fulfill({status: 401, contentType: type, body: JSON.stringify({private: 'must never display'})});
    const value = url.pathname.endsWith('/history') ? libraryHistoryFixture(undefined, Number(url.searchParams.get('after'))) :
      url.pathname.endsWith(catalogEntry.entryId) ? libraryDetailFixture('catalog') :
      url.pathname.endsWith(draftEntry.entryId) ? libraryDetailFixture() : libraryFixture();
    return route.fulfill({contentType: type, body: JSON.stringify(value)});
  });
  await page.goto('/?mode=real');
  const startup = page.getByRole('dialog', {name: 'Vision Workstation Startup'});
  await expect(startup.getByRole('button', {name: 'Refresh library'})).toHaveCount(0);
  await enterDesktop(page);
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('region', {name: 'ECU Library', exact: true, includeHidden: true});
  expect(reads).toEqual([]);
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await expect(library).toContainText('SYNTHETIC TEST · no station library');
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  await library.getByRole('button', {name: 'Browse ETC3 v1', exact: true}).click();
  await expect(library).toContainText('Catalog record only');
  await expect(library).toContainText('2 field notes · unverified');
  await expect(library.getByRole('tab', {name: '15 sections'})).toHaveCount(0);
  await library.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  await expect(library).toContainText('NOT_READY · Unsigned draft');
  await expect(library).toContainText('Yes · not an approval');
  await library.getByRole('tab', {name: '15 sections'}).click();
  await expect(library.getByRole('table', {name: 'Reference profile sections'}).locator('tbody tr')).toHaveCount(15);
  await expect(library).toContainText('counts do not indicate completeness or approval');
  await library.getByRole('tab', {name: 'Revision history (53)'}).click();
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(50);
  await library.getByRole('button', {name: 'Next history page'}).click();
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(3);
  await expect(library).toContainText('53 · current');
  await expect(library.getByRole('button', {name: 'Next history page'})).toBeDisabled();
  await library.getByRole('button', {name: 'Previous history page'}).click();
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(50);
  await expect(library.getByRole('button', {name: 'Open reference editor'})).toBeDisabled();
  expect(reads).toHaveLength(6);
  denied = true;
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await expect(library).toContainText('Access denied');
  await expect(library).not.toContainText(draftEntry.profileId);
  await expect(library).not.toContainText('must never display');
  await expect(library.getByRole('table')).toHaveCount(0);
  denied = false;
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await expect(library.getByRole('table', {name: 'ECU library entries'}).locator('tbody tr')).toHaveCount(2);
  const stored = await page.evaluate(() => ({local: {...localStorage}, session: {...sessionStorage}}));
  expect(JSON.stringify(stored)).not.toContain(draftEntry.profileId);
  expect(JSON.stringify(stored)).not.toContain(libraryFixture().viewId);
  const beforeReload = reads.length;
  await page.reload(); await enterDesktop(page);
  await expect(library).toContainText('No protected library report requested');
  await expect(library.getByRole('table')).toHaveCount(0);
  expect(reads).toHaveLength(beforeReload);
});

test('library pages replace prior entries and stale views or empty libraries stay explicit', async ({page}) => {
  let mode: 'normal' | 'stale' | 'empty' = 'normal';
  await page.route('**/api/v1/status', route => route.fulfill({contentType: type, body: JSON.stringify(boot)}));
  await page.route(/\/api\/v1\/library(?:\/|\?|$)/, route => {
    const url = new URL(route.request().url());
    const after = Number(url.searchParams.get('after'));
    const report = libraryFixture(mode === 'empty' ? 0 : 51, after);
    return route.fulfill({contentType: type, body: JSON.stringify(mode === 'stale' && after > 0 ? {...report, viewId: 'f'.repeat(64)} : report)});
  });
  await page.goto('/?mode=real'); await enterDesktop(page);
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('region', {name: 'ECU Library', exact: true, includeHidden: true});
  const entries = library.getByRole('table', {name: 'ECU library entries'});
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await expect(entries.locator('tbody tr')).toHaveCount(50);
  await library.getByRole('button', {name: 'Next entries'}).click();
  await expect(entries.locator('tbody tr')).toHaveCount(1);
  await expect(library).toContainText('51–51 of 51 entries');
  await expect(library).not.toContainText(draftEntry.displayName);
  await library.getByRole('button', {name: 'Previous entries'}).click();
  await expect(entries.locator('tbody tr')).toHaveCount(50);
  mode = 'stale';
  await library.getByRole('button', {name: 'Next entries'}).click();
  await expect(library).toContainText('Library report unavailable or changed');
  await expect(entries).toHaveCount(0);
  mode = 'empty';
  await library.getByRole('button', {name: 'Refresh library'}).click();
  await expect(library).toContainText('No catalog records or reference drafts are available');
  await expect(library.getByRole('button', {name: 'Next entries'})).toBeDisabled();
});

test('library detail and history failures clear the whole previous view and allow recovery', async ({page}) => {
  let failure: 'none' | 'detail' | 'history' | 'disconnect' = 'none';
  await page.route('**/api/v1/status', route => route.fulfill({contentType: type, body: JSON.stringify(boot)}));
  await page.route(/\/api\/v1\/library(?:\/|\?|$)/, route => {
    const url = new URL(route.request().url());
    let report: unknown = libraryFixture();
    if (url.pathname.endsWith('/history')) {
      if (failure === 'disconnect') return route.abort('failed');
      const history = libraryHistoryFixture();
      report = failure === 'history' ? {...history, etag: '"' + 'f'.repeat(64) + '"'} : history;
    } else if (url.pathname.endsWith(draftEntry.entryId)) {
      const detail = libraryDetailFixture();
      report = failure === 'detail' ? {...detail, source: 'STATION'} : detail;
    }
    return route.fulfill({contentType: type, body: JSON.stringify(report)});
  });
  await page.goto('/?mode=real'); await enterDesktop(page);
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('region', {name: 'ECU Library', exact: true, includeHidden: true});
  for (const next of ['none','detail','history','disconnect','none'] as const) {
    failure = next;
    await library.getByRole('button', {name: 'Refresh library'}).click();
    await library.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
    if (next === 'none') await expect(library).toContainText('NOT_READY · Unsigned draft');
    else {
      await expect(library).toContainText('Library report unavailable or changed');
      await expect(library.getByRole('table')).toHaveCount(0);
      await expect(library).not.toContainText(draftEntry.profileId);
    }
  }
});

test('demo and invalid modes never request library data', async ({page}) => {
  const requests: string[] = [];
  await page.route('**/api/v1/**', route => { requests.push(route.request().url()); return route.fulfill({status: 500}); });
  for (const mode of ['demo','invalid']) {
    await page.goto('/?mode=' + mode); await enterDesktop(page);
    await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name: 'ECU Library', exact: true}).click();
    const library = page.getByRole('region', {name: 'ECU Library', exact: true, includeHidden: true});
    await expect(library).toContainText('Library reads are disabled');
    await expect(library.getByRole('button', {name: 'Refresh library'})).toBeDisabled();
    await expect(library.getByRole('button', {name: 'Open reference editor'})).toBeDisabled();
  }
  expect(requests).toEqual([]);
});

test('actual Library: authorized backend catalog, reference sections, exact history and reload isolation', async ({page, context}) => {
  test.skip(process.env.VISION_LIBRARY_INTEGRATION !== '1', 'Actual synthetic library fixture and test-only authorization are explicit opt-in.');
  const errors: string[] = [], methods: string[] = [], libraryRequests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { const path = new URL(request.url()).pathname; if (path.startsWith('/api/v1/')) methods.push(request.method()); if (path.startsWith('/api/v1/library')) libraryRequests.push(path); });
  await page.goto('/?mode=real'); await enterDesktop(page);
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name: 'ECU Library', exact: true}).click();
  const library = page.getByRole('region', {name: 'ECU Library', exact: true, includeHidden: true});
  const denied = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/library');
  await library.getByRole('button', {name: 'Refresh library'}).click();
  expect((await denied).status()).toBe(401);
  await expect(library).toContainText('Access denied');
  const auth = JSON.parse(readFileSync('.api03-test-auth.json', 'utf8'));
  await assertPrivateFixtureFile(page, '.api03-test-auth.json', auth.cookieValue);
  await context.addCookies([{name: auth.cookieName, value: auth.cookieValue, url: 'http://127.0.0.1:4173', httpOnly: true, sameSite: 'Strict'}]);
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/library');
  await library.getByRole('button', {name: 'Refresh library'}).click();
  const result = await response;
  expect(result.status()).toBe(200); expect(result.headers()['cache-control']).toBe('no-store');
  const report: unknown = await result.json();
  expect(isLibraryReport(report)).toBe(true);
  if (!isLibraryReport(report)) throw new Error('Invalid library fixture report');
  expect(report.source).toBe('SYNTHETIC_TEST'); expect(report.totalCount).toBe(2);
  await expect(library).toContainText('SYNTHETIC TEST · no station library');
  await library.getByRole('button', {name: 'Browse ETC3 v1', exact: true}).click();
  await expect(library).toContainText('Catalog record only');
  const draft = report.entries.find(entry => entry.kind === 'REFERENCE_DRAFT');
  if (!draft) throw new Error('Missing synthetic draft');
  const detailResponse = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/library/entries/${draft.entryId}`);
  const historyResponse = page.waitForResponse(response => new URL(response.url()).pathname === `/api/v1/library/entries/${draft.entryId}/history`);
  await library.getByRole('button', {name: 'Browse API-03 synthetic reference r1', exact: true}).click();
  const detail: unknown = await (await detailResponse).json(), history: unknown = await (await historyResponse).json();
  expect(isLibraryDetail(detail)).toBe(true); expect(isLibraryHistory(history)).toBe(true);
  if (!isLibraryDetail(detail) || !isLibraryHistory(history)) throw new Error('Invalid protected fixture detail');
  expect(matchesLibraryDetail(detail, report, draft)).toBe(true); expect(matchesLibraryHistory(history, detail, 0)).toBe(true);
  expect(history.totalCount).toBe(2); expect(history.items.at(-1)?.etag).toBe(draft.etag);
  await expect(library).toContainText('NOT_READY · Unsigned draft');
  await expect(library).toContainText('Closed enclosure');
  await library.getByRole('tab', {name: '15 sections'}).click();
  await expect(library.getByRole('table', {name: 'Reference profile sections'}).locator('tbody tr')).toHaveCount(15);
  const box = (await library.boundingBox())!;
  const navigation = (await page.getByRole('navigation', {name: 'Main navigation'}).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(navigation.x + navigation.width);
  expect(box.x + box.width).toBeLessThanOrEqual(1280);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({path: 'test-results/audit-library.png', fullPage: true});
  await library.getByRole('tab', {name: 'Revision history (2)'}).click();
  await expect(library.getByRole('table', {name: 'Reference revision history'}).locator('tbody tr')).toHaveCount(2);
  await expect(library.getByRole('button', {name: 'Next history page'})).toBeDisabled();
  await expect(library.getByRole('button', {name: 'Open reference editor'})).toBeDisabled();
  const beforeReload = libraryRequests.length;
  await page.reload(); await enterDesktop(page);
  await expect(library).toContainText('No protected library report requested');
  await expect(library).not.toContainText(draft.profileId);
  expect(libraryRequests).toHaveLength(beforeReload);
  const storage = await page.evaluate(() => JSON.stringify({...localStorage, ...sessionStorage}));
  expect(storage).not.toContain(draft.profileId); expect(storage).not.toContain(report.viewId); expect(storage.includes(auth.cookieValue)).toBe(false);
  expect(methods.every(method => method === 'GET')).toBe(true); expect(errors).toEqual([]);
});
