import { expect, test } from '@playwright/test';
import { appPanel, enterDesktop, openApp } from './helpers';

test.beforeEach(async ({page}) => {
  await page.route('**/local-brand/**', route => route.fulfill({status: 404, body: ''}));
});

test('workspace navigation shows one page, supports the keyboard and remembers the selected page', async ({page}) => {
  const external: string[] = [];
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:4173/')) external.push(request.url()); });
  await page.goto('/'); await enterDesktop(page);
  await expect(page.locator('.app-header')).toContainText('DEMO');
  const navigation = page.getByRole('navigation', {name: 'Main navigation'});
  const status = appPanel(page, 'System Status');
  await expect(status).toContainText('UNKNOWN');
  await expect(page.getByRole('heading', {level: 1, name: 'System Status', exact: true})).toBeVisible();
  const libraryLink = navigation.getByRole('button', {name: 'ECU Library', exact: true});
  await libraryLink.focus(); await page.keyboard.press('Enter');
  const library = appPanel(page, 'ECU Library');
  await expect(library).toBeVisible();
  await expect(status).toBeHidden();
  await expect(status).toHaveCount(1);
  await expect(libraryLink).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('heading', {level: 1, name: 'ECU Library', exact: true})).toBeVisible();
  await expect(library.getByRole('button', {name: 'Open reference editor'})).toBeDisabled();
  await openApp(page, 'System Status');
  await expect(library).toBeHidden();
  await expect(library).toHaveCount(1);
  await openApp(page, 'ECU Library');
  await page.reload(); await enterDesktop(page);
  await expect(library).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('vision.workspace.v2')!))).toEqual({schema: 'vision.workspace.v2', activeApp: 'ecu'});
  expect(external).toEqual([]);
});

test('invalid preferences and blocked browser storage retain usable, truthful navigation', async ({page}) => {
  await page.addInitScript(() => localStorage.setItem('vision.workspace.v2', '{corrupt'));
  await page.goto('/?mode=real'); await enterDesktop(page);
  const status = appPanel(page, 'System Status');
  await expect(page.locator('.app-header')).toContainText('UNAVAILABLE');
  await expect(status).toContainText('Real adapter unavailable');
  await expect(status).not.toContainText('Synthetic');
  await page.addInitScript(() => { Storage.prototype.setItem = () => { throw Error('disabled'); }; });
  await page.reload(); await enterDesktop(page);
  await expect(status).toBeVisible();
  await openApp(page, 'ECU Library');
  await openApp(page, 'Control Panel');
  await appPanel(page, 'Control Panel').getByRole('button', {name: 'Reset workspace', exact: true}).click();
  await expect(status).toBeVisible();
});

test('mobile navigation is reachable, closes on selection and Escape, and keeps content within the viewport', async ({page}) => {
  await page.setViewportSize({width: 360, height: 780});
  await page.goto('/'); await enterDesktop(page);
  const open = page.getByRole('button', {name: 'Open navigation', exact: true});
  await expect(open).toBeVisible();
  expect((await open.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await open.click();
  const navigation = page.getByRole('navigation', {name: 'Main navigation'});
  await expect(navigation).toBeVisible();
  const libraryLink = navigation.getByRole('button', {name: 'ECU Library', exact: true});
  expect((await libraryLink.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.keyboard.press('Escape');
  await expect(open).toHaveAttribute('aria-expanded', 'false');
  await expect(open).toBeFocused();
  await openApp(page, 'ECU Library');
  await expect(open).toHaveAttribute('aria-expanded', 'false');
  const library = appPanel(page, 'ECU Library');
  await expect(library).toBeVisible();
  await expect(appPanel(page, 'System Status')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  const typography = await library.evaluate(element => {
    const style = getComputedStyle(element);
    return {fontSize: parseFloat(style.fontSize), fontFamily: style.fontFamily};
  });
  expect(typography.fontSize).toBeGreaterThanOrEqual(16);
  expect(typography.fontFamily).not.toMatch(/ms sans serif/i);
  await page.screenshot({path: 'test-results/workspace-mobile.png', fullPage: true});
});

test('workspace reset returns to the status page and the desktop report uses the available width', async ({page}) => {
  await page.setViewportSize({width: 1280, height: 800});
  await page.goto('/'); await enterDesktop(page);
  const status = appPanel(page, 'System Status');
  await expect(status).toContainText('Sony Camera');
  const navigation = (await page.getByRole('navigation', {name: 'Main navigation'}).boundingBox())!;
  const panel = (await status.boundingBox())!;
  expect(panel.x).toBeGreaterThanOrEqual(navigation.x + navigation.width);
  expect(panel.width).toBeGreaterThan(800);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({path: 'test-results/workspace-desktop.png', fullPage: true});
  await openApp(page, 'Control Panel');
  await appPanel(page, 'Control Panel').getByRole('button', {name: 'Reset workspace', exact: true}).click();
  await expect(status).toBeVisible();
  await expect(appPanel(page, 'Control Panel')).toBeHidden();
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('vision.workspace.v2')!).activeApp)).toBe('status');
});
