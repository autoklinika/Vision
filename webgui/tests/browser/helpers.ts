import type { Page } from '@playwright/test';
export async function enterDesktop(page: Page) {
  await page.getByRole('button', { name: 'Continue to login presentation' }).click();
  await page.getByRole('button', { name: /Continue to DEMO desktop|Open read-only disconnected view/ }).click();
}
