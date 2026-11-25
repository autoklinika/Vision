import { expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { originalSha256 } from '../../src/startup/brand';
import reference from '../../src/startup/brand-reference.json' with { type: 'json' };
import { enterDesktop } from './helpers';
let pageErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
});
test.afterEach(() => expect(pageErrors).toEqual([]));

const fixture = JSON.parse(readFileSync(new URL('../fixtures/brand.json', import.meta.url), 'utf8'));
const intro = Buffer.from(fixture.intro, 'base64');
const logo = Buffer.from(fixture.logo, 'base64');
const hash = (data: Buffer) => createHash('sha256').update(data).digest('hex');
async function brandFixture(page: Page) {
  await page.route('**/local-brand/**', route => {
    const name = route.request().url().split('/').pop();
    if (name === 'manifest.json') return route.fulfill({ json: {
      sourceSha256: originalSha256, durationMs: 3490,
      introSha256: hash(intro), logoSha256: hash(logo),
    } });
    return route.fulfill({ contentType: name === 'intro.gif' ? 'image/gif' : 'image/png', body: name === 'intro.gif' ? intro : logo });
  });
}

test('B → C → D: report, disabled credentials, no external requests', async ({ page }) => {
  const external: string[] = [];
  const writes: string[] = [];
  page.on('request', request => {
    if (!request.url().startsWith('http://127.0.0.1:4173/') && !request.url().startsWith('blob:')) external.push(request.url());
    if (request.method() !== 'GET') writes.push(request.url());
  });
  await page.route('**/local-brand/**', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/');
  await expect(page.getByRole('dialog', { name: 'Vision Workstation Startup' })).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('UNKNOWN');
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toContainText('Client report read finished');
  await expect(page.getByRole('dialog')).not.toContainText(/READY|\d+%/);
  await page.getByRole('button', { name: 'Continue to login presentation' }).click();
  await expect(page.getByLabel('User name', { exact: true })).toBeDisabled();
  await expect(page.getByLabel('Password', { exact: true })).toBeDisabled();
  await expect(page.getByRole('dialog')).toContainText('does not authenticate');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Welcome to Vision' })).toBeVisible();
  await page.getByRole('button', { name: 'Continue to DEMO desktop' }).click();
  await expect(page.getByRole('region', { name: 'System Status', exact: true, includeHidden: true})).toBeVisible();
  expect(external).toEqual([]);
  expect(writes).toEqual([]);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual(['vision.workspace.v2']);
});

for (const mode of ['demo', 'real', 'invalid']) {
  test(`missing asset: ${mode} stays explicit and permits disconnected navigation`, async ({ page }) => {
    const requests: string[] = [];
    page.on('request', r => requests.push(r.url()));
    await page.route('**/local-brand/**', route => route.fulfill({ status: 404, body: '' }));
    await page.goto(`/?mode=${mode}`);
    await expect(page.getByRole('dialog')).toContainText('Original intro unavailable or corrupt');
    if (mode !== 'demo') await expect(page.getByRole('dialog')).toContainText('Real adapter unavailable');
    if (mode === 'real') await page.screenshot({ path: 'test-results/startup-no-brand.png', animations: 'disabled' });
    await expect(page.getByRole('dialog')).toContainText('UNKNOWN');
    await enterDesktop(page);
    await expect(page.locator('.app-header')).toContainText(mode === 'demo' ? 'DEMO' : 'UNAVAILABLE');
    if (mode !== 'demo') {
      await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).toContainText('Real adapter unavailable');
      expect(requests.some(url => /\/demo\/|\/adapter-/.test(url))).toBe(false);
    }
    expect(requests.filter(url => !url.startsWith('http://127.0.0.1:4173/'))).toEqual([]);
    expect(requests.filter(url => new URL(url).pathname === '/api/v1/status')).toHaveLength(mode === 'real' ? 1 : 0);
  });
}

test('substituted bytes and matching attacker manifest are rejected', async ({ page }) => {
  await brandFixture(page);
  await page.goto('/');
  await expect(page.getByRole('dialog')).toContainText('unavailable or corrupt');
  await expect(page.locator('img')).toHaveCount(0);
});

test('snapshot rejection remains UNKNOWN through login and desktop', async ({ page }) => {
  test.skip(process.env.GUI_BUILD_SMOKE === '1', 'Dev module substitution only; report failure also covered by unit tests.');
  await page.route('**/src/api/realAdapter.ts', route => route.fulfill({ contentType: 'text/javascript', body: 'export const realAdapter = { mode: "real", readSnapshot: async () => { throw Error("test rejection"); } };' }));
  await page.route('**/local-brand/**', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/?mode=real');
  await expect(page.getByRole('dialog')).toContainText('selected adapter failed');
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  await expect(page.getByRole('dialog')).toContainText('Client report read finished');
  await enterDesktop(page);
  await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).toContainText('selected adapter failed');
  await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).toContainText('UNKNOWN');
  await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).not.toContainText('Synthetic');
});

test('pending snapshot never blocks diagnostic navigation', async ({ page }) => {
  test.skip(process.env.GUI_BUILD_SMOKE === '1', 'Dev module substitution only.');
  const calls: string[] = [];
  page.on('console', message => { if (message.text() === 'snapshot-read-started') calls.push(message.text()); });
  await page.route('**/src/api/realAdapter.ts', route => route.fulfill({ contentType: 'text/javascript', body: 'export const realAdapter = { mode: "real", readSnapshot: () => { console.log("snapshot-read-started"); return new Promise(() => {}); } };' }));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 360, height: 640 });
  await page.route('**/local-brand/**', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/?mode=real');
  const progress = page.getByRole('progressbar');
  await expect(progress).toBeVisible();
  await expect(progress).not.toHaveAttribute('aria-valuenow');
  expect(await progress.locator('span').evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  await expect(page.getByRole('button', { name: 'Open read-only diagnostics' })).toBeInViewport();
  expect(calls).toEqual(['snapshot-read-started']);
  await expect(page.getByRole('dialog')).toContainText('No system status has been received');
  await page.getByRole('button', { name: 'Open read-only diagnostics' }).click();
  await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).toContainText('UNKNOWN');
  expect(calls).toHaveLength(1);
});

test('private original renders locally at original dimensions with static hold', async ({ page }) => {
  test.skip(process.env.GUI_PRIVATE_ORIGINAL !== '1', 'Explicit local-only opt-in, no screenshots/traces.');
  await page.goto('/');
  const animation = page.getByAltText('Original Vision handwriting intro');
  await expect(animation).toBeVisible();
  await expect(animation).toHaveJSProperty('naturalWidth', 800);
  await expect(animation).toHaveJSProperty('naturalHeight', 100);
  await page.waitForTimeout(2000);
  await expect(animation).toBeVisible();
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 6000 });
  const hold = page.getByAltText('Original Vision logo', { exact: true });
  await expect(hold).toHaveJSProperty('naturalWidth', 800);
  await expect(hold).toHaveJSProperty('naturalHeight', 100);
});

for (const reduced of [false, true]) {
  test(`private original skip/reduced motion ${reduced}`, async ({ page }) => {
    test.skip(process.env.GUI_PRIVATE_ORIGINAL !== '1', 'Explicit private opt-in.');
    await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
    await page.goto('/');
    if (!reduced) {
      await expect(page.getByAltText('Original Vision handwriting intro')).toBeVisible();
      await page.getByRole('button', { name: 'Skip intro' }).click();
    }
    await expect(page.getByAltText('Original Vision handwriting intro')).toHaveCount(0);
    await expect(page.getByAltText('Original Vision logo', { exact: true })).toHaveJSProperty('naturalWidth', 800);
    await enterDesktop(page);
  });
}

test('genuine remote HTTP is insecure and never requests brand files', async ({ page }) => {
  const brandRequests: string[] = [];
  page.on('request', r => { if (r.url().includes('/local-brand/')) brandRequests.push(r.url()); });
  // Intercept a non-local origin; Chromium still applies its real secure-context rules.
  await page.route('http://vision-audit.test/**', async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: `http://127.0.0.1:4173${url.pathname}${url.search}` });
    await route.fulfill({ response });
  });
  await page.goto('http://vision-audit.test/?mode=real');
  expect(await page.evaluate(() => isSecureContext)).toBe(false);
  await expect(page.getByRole('status').filter({ hasText: 'secure context' })).toBeVisible();
  expect(brandRequests).toEqual([]);
  await enterDesktop(page);
  await expect(page.getByRole('region', {name: 'System Status', exact: true, includeHidden: true})).toContainText('UNKNOWN');
});

test('one-byte corrupt asset with trusted manifest is rejected', async ({ page }) => {
  await page.route('**/local-brand/**', route => route.request().url().endsWith('manifest.json')
    ? route.fulfill({ json: { ...reference, durationMs: 3490 } })
    : route.fulfill({ body: Buffer.from([0]), contentType: 'application/octet-stream' }));
  await page.goto('/');
  await expect(page.getByRole('dialog')).toContainText('unavailable or corrupt');
  await expect(page.locator('img')).toHaveCount(0);
});

test('private original one-byte mutation is rejected', async ({ page }) => {
  test.skip(process.env.GUI_PRIVATE_ORIGINAL !== '1', 'Explicit private opt-in.');
  const bytes = readFileSync('public/local-brand/intro.gif');
  bytes[bytes.length - 1] ^= 1;
  await page.route('**/local-brand/intro.gif', route => route.fulfill({ body: bytes, contentType: 'image/gif' }));
  await page.goto('/');
  await expect(page.getByRole('dialog')).toContainText('unavailable or corrupt');
  await expect(page.locator('img')).toHaveCount(0);
});

for (const rejected of [false, true]) {
  test(`pending indicator ends after adapter ${rejected ? 'rejects' : 'resolves'}`, async ({ page }) => {
    test.skip(process.env.GUI_BUILD_SMOKE === '1', 'Test-only dev module injection.');
    await page.route('**/src/api/realAdapter.ts', route => route.fulfill({ contentType: 'text/javascript', body: `export const realAdapter = { mode: 'real', readSnapshot: () => new Promise((resolve, reject) => { window.finishTestRead = () => ${rejected ? "reject(Error('test'))" : "resolve({ schema: 'client-view-v1', source: 'real', connection: 'UNAVAILABLE', readiness: 'UNKNOWN', observedAt: null, reason: 'Closed test stub', components: [] })"}; }) };` }));
    await page.route('**/local-brand/**', route => route.fulfill({ status: 404, body: '' }));
    await page.goto('/?mode=real');
    await expect(page.getByRole('progressbar')).toBeVisible();
    await expect(page.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow');
    await page.evaluate('window.finishTestRead()');
    await expect(page.getByRole('progressbar')).toHaveCount(0);
    await expect(page.getByRole('dialog')).toContainText('Client report read finished');
    await expect(page.getByRole('dialog')).toContainText('UNKNOWN');
    await expect(page.getByRole('dialog')).not.toContainText(/READY|\d+%/);
  });
}
