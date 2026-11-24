import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { isBootStatus } from '../../src/api/statusContract';
import { enterDesktop } from './helpers';

const fixtures = JSON.parse(readFileSync(new URL('../../../contracts/vision-api/v1/status-fixtures.json', import.meta.url), 'utf8'));
const endpoint = '**/api/v1/status';
const type = 'application/json; charset=utf-8';

test.beforeEach(async ({page}) => {
  await page.route('**/local-brand/**', route => route.fulfill({status:404,body:''}));
});

test('actual API: Python loopback response and refresh recovery', async ({page}) => {
  test.skip(process.env.VISION_API_INTEGRATION !== '1', 'Actual loopback Python server is explicit opt-in.');
  const requests: {method:string;url:string}[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) requests.push({method:r.method(),url:r.url()}); });
  const reply = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/status');
  await page.goto('/?mode=real');
  const response = await reply;
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toBe(type);
  expect(response.headers()['cache-control']).toBe('no-store');
  const report = await response.json();
  expect(isBootStatus(report)).toBe(true);
  const startup = page.getByRole('dialog',{name:'Vision Workstation Startup'});
  await expect(startup).toContainText('API AVAILABLE (last report)');
  await expect(startup).toContainText(report.reportTime);
  await expect(startup).toContainText('CORE_REPORT_NOT_CONNECTED');
  await expect(startup).toContainText('UNKNOWN');
  await expect(startup).not.toContainText('READY');
  await enterDesktop(page);
  const desktop = page.getByRole('dialog',{name:'System Status',exact:true});
  await expect(desktop).toContainText('API AVAILABLE (last report)');
  await expect(page.locator('.mode-banner')).toContainText('REAL · API REPORT');
  expect(requests).toHaveLength(1);

  // Simulate loss of the HTTP path, then restore real, unmocked Python replies.
  await page.route(endpoint, route => route.abort('failed'));
  await desktop.getByRole('button',{name:'Refresh API report'}).click();
  await expect(desktop).toContainText('Real adapter unavailable');
  await expect(desktop).not.toContainText('API AVAILABLE');
  await expect(desktop).not.toContainText(report.reportTime);
  await expect(page.locator('.mode-banner')).toContainText('UNAVAILABLE');
  await page.unroute(endpoint);
  const next = page.waitForResponse(r => new URL(r.url()).pathname === '/api/v1/status');
  await desktop.getByRole('button',{name:'Refresh API report'}).click();
  const recovered = await (await next).json();
  expect(isBootStatus(recovered)).toBe(true);
  await expect(desktop).toContainText('API AVAILABLE (last report)');
  await expect(desktop).toContainText(recovered.reportTime);
  await expect(desktop).toContainText('UNKNOWN');
  expect(requests).toHaveLength(3);
  expect(requests.every(r => r.method === 'GET' && r.url === 'http://127.0.0.1:4173/api/v1/status')).toBe(true);
  expect(errors).toEqual([]);
  await page.locator('.desktop-icons').getByRole('button',{name:'ECU Library',exact:true}).click();
  await expect(page.getByRole('button',{name:'Open reference editor'})).toBeDisabled();
  expect(requests).toHaveLength(3);
});

test('API client rejects false readiness and HTTP errors, then accepts valid fixture', async ({page}) => {
  await page.route(endpoint, route => route.fulfill({
    contentType:type,body:JSON.stringify({...fixtures.valid,coreReadiness:'READY'}),
  }));
  await page.goto('/?mode=real');
  const startup = page.getByRole('dialog',{name:'Vision Workstation Startup'});
  await expect(startup).toContainText('Real adapter unavailable');
  await expect(startup).toContainText('UNKNOWN');
  await expect(startup).not.toContainText('API AVAILABLE');
  await page.unroute(endpoint);
  await page.route(endpoint, route => route.fulfill({status:503,contentType:type,body:'{"private":"not shown"}'}));
  await startup.getByRole('button',{name:'Refresh API report'}).click();
  await expect(startup).toContainText('Real adapter unavailable');
  await expect(startup).not.toContainText('not shown');
  await page.unroute(endpoint);
  await page.route(endpoint, route => route.fulfill({contentType:type,body:JSON.stringify(fixtures.valid)}));
  await startup.getByRole('button',{name:'Refresh API report'}).click();
  await expect(startup).toContainText('API AVAILABLE (last report)');
  await expect(startup).toContainText(fixtures.valid.reportTime);
  await expect(startup).toContainText('UNKNOWN');
});

test('API client rejects redirect instead of following it', async ({page}) => {
  let followed = false;
  await page.route('**/unexpected-api-target', route => { followed=true; return route.fulfill({contentType:type,body:JSON.stringify(fixtures.valid)}); });
  await page.route(endpoint, route => route.fulfill({status:302,headers:{Location:'/unexpected-api-target'}}));
  await page.goto('/?mode=real');
  await expect(page.getByRole('dialog',{name:'Vision Workstation Startup'})).toContainText('Real adapter unavailable');
  expect(followed).toBe(false);
});

test('ambiguous mode never contacts API', async ({page}) => {
  let calls = 0;
  await page.route(endpoint, route => { calls++; return route.fulfill({status:500}); });
  await page.goto('/?mode=real&mode=demo');
  await expect(page.getByRole('dialog',{name:'Vision Workstation Startup'})).toContainText('invalid client mode');
  await enterDesktop(page);
  await expect(page.locator('.mode-banner')).toContainText('UNAVAILABLE');
  expect(calls).toBe(0);
});
