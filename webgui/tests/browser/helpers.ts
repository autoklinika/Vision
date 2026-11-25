import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { resolve } from 'node:path';
export async function enterDesktop(page: Page) {
  await page.getByRole('button', { name: 'Continue to login presentation' }).click();
  await page.getByRole('button', { name: /Continue to DEMO desktop|Open read-only view/ }).click();
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
