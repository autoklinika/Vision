import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { resolve } from 'node:path';
export async function enterDesktop(page: Page) {
  await page.getByRole('button', { name: 'Continue to login presentation' }).click();
  await page.getByRole('button', { name: /Continue to DEMO desktop|Open read-only view/ }).click();
}

/** Workspaces retain their working copy while only the selected page is shown. */
export function appPanel(page: Page, name: string) {
  return page.getByRole('region', {name, exact: true, includeHidden: true});
}
export async function openApp(page: Page, name: string) {
  const openNavigation = page.getByRole('button', {name: 'Open navigation', exact: true});
  if (await openNavigation.isVisible()) await openNavigation.click();
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button', {name, exact: true}).click();
  await expect(appPanel(page, name)).toBeVisible();
}

/** Test-only credentials must be inaccessible through every Vite serving path. */
export async function assertPrivateFixtureFile(page: Page, filename: '.api02-test-auth.json' | '.api03-test-auth.json', cookieValue: string) {
  const absolute = resolve(filename);
  const targets = [
    `/${filename}`, `/%2e${filename.slice(1)}`,
    `/${filename}?raw`, `/${filename}?import`, `/${filename}?url`,
    `/${filename}?import&raw`, `/${filename}?import&url&inline`,
    `/@fs/${absolute}`, `/@fs/${absolute}?raw`, `/@fs/${absolute}?import&raw`, `/@fs/${absolute}?import&url&inline`,
    `/@fs${absolute}`, `/@fs${absolute}?raw`, `/@fs${absolute}?import&raw`, `/@fs${absolute}?import&url&inline`,
  ];
  for (const target of targets) {
    const response = await page.request.get(target);
    const body = await response.text();
    // Boolean assertions deliberately keep credential values and bodies out
    // of failure diagnostics, including when a regression exposes the file.
    expect(body.includes(cookieValue)).toBe(false);
    expect(body.includes('cookieValue')).toBe(false);
    expect(body.includes('cookieName')).toBe(false);
    if (process.env.GUI_BUILD_SMOKE !== '1') expect(response.status()).toBe(403);
  }
}
