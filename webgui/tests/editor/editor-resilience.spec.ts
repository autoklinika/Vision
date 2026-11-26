import {expect,test} from '@playwright/test';
import type {Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

async function newEditor(page:Page,key:string,create=true,virtualClock=true){
  if(virtualClock)await page.clock.install();
  const credentials=JSON.parse(readFileSync('../.station-test-auth.json','utf8'));
  await page.goto('/');
  await expect(page.getByLabel('User name',{exact:true})).toBeEnabled();
  await page.getByLabel('User name',{exact:true}).fill(credentials.username);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('.vision-workspace')).toBeVisible();
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name:'ECU Library',exact:true}).click();
  const library=page.locator('[data-module="ecu"]');
  await library.getByRole('button',{name:'New profile',exact:true}).click();
  const editor=library.getByRole('region',{name:'ECU reference editor'});
  await editor.getByLabel('ECU family',{exact:true}).fill('resilience-family');
  await editor.getByLabel('Variant ID',{exact:true}).fill('synthetic-'+key);
  await editor.getByLabel('New profile ID',{exact:true}).fill(key);
  await editor.getByLabel('Revision',{exact:true}).fill('r1');
  await editor.getByLabel('Display name',{exact:true}).fill('Synthetic resilience fixture');
  if(create){
    await editor.getByRole('button',{name:'Create draft',exact:true}).click();
    await expect(editor).toContainText('Draft saved in Core.');
    await editor.getByLabel('Section',{exact:true}).selectOption('identity');
    await editor.getByLabel('Manufacturer (optional)',{exact:true}).fill('Unsaved synthetic manufacturer');
  }
  await expect(editor).toHaveAttribute('data-editor-dirty','true');
  return {library,editor};
}

test('unsaved editor survives transient station/auth failures, Core outage and session ownership changes',async({page})=>{
  // This scenario combines the real HTTP fixture with independent station,
  // identity and library polling. Advancing a fake clock can expire real
  // network requests while their responses are still being processed.
  // Test actual polling with bounded expectations instead.
  test.setTimeout(210000);
  // Exercise pre-create discard protection in the same authenticated flow.
  // The suite stays within the real five-login limit; no throttling override.
  const {editor}=await newEditor(page,'resilience-profile',false,false);
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Close ECU Library',exact:true}).click();
  await expect(editor.getByLabel('ECU family',{exact:true})).toHaveValue('resilience-family');
  page.once('dialog',dialog=>dialog.dismiss());
  await editor.getByRole('button',{name:'Close editor',exact:true}).click();
  await expect(editor.getByLabel('New profile ID',{exact:true})).toHaveValue('resilience-profile');
  await editor.getByRole('button',{name:'Create draft',exact:true}).click();
  await expect(editor).toContainText('Draft saved in Core.');
  await editor.getByLabel('Section',{exact:true}).selectOption('identity');
  await editor.getByLabel('Manufacturer (optional)',{exact:true}).fill('Unsaved synthetic manufacturer');
  const manufacturer=editor.getByLabel('Manufacturer (optional)',{exact:true});
  const save=editor.getByRole('button',{name:'Save draft generation',exact:true});
  // A real identity store extends its idle deadline on protected reads.
  // Healthy renewals must not hide/remount the workspace or steal focus.
  await manufacturer.focus();
  const input=await manufacturer.elementHandle();
  const originalEditor=await editor.elementHandle();
  const wrapper=page.locator('.desktop').locator('..');
  await wrapper.evaluate(el=>{
    el.setAttribute('data-test-hidden-transitions','0');
    const observer=new MutationObserver(records=>{
      el.setAttribute('data-test-hidden-transitions',String(Number(el.getAttribute('data-test-hidden-transitions'))+records.length));
    });
    observer.observe(el,{attributes:true,attributeFilter:['hidden']});
  });
  const identityBefore=await (await page.request.get('/api/v1/auth/session')).json();
  let expiry=identityBefore.expiresAt as string;
  for(let i=0;i<2;i++){
    const identityPoll=await page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/auth/session'&&r.request().method()==='GET'&&r.status()===200,{timeout:22000});
    const next=await identityPoll.json();
    expect(next.expiresAt>expiry,'real sliding idle deadline advanced').toBe(true);
    expiry=next.expiresAt;
    await page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/station'&&r.status()===200,{timeout:10000});
    await expect(editor).toBeVisible();
    await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
    await expect(manufacturer).toBeFocused();
    expect(await manufacturer.evaluate((el,previous)=>el===previous,input)).toBe(true);
    expect(await editor.evaluate((el,previous)=>el===previous,originalEditor)).toBe(true);
    await expect(wrapper).toHaveAttribute('data-test-hidden-transitions','0');
  }
  await input?.dispose();
  await originalEditor?.dispose();

  const station=await (await page.request.get('/api/v1/station')).json();
  const inspection=await (await page.request.get('/api/v1/inspection')).json();
  // Keep transport states deterministic while the actual form/storage/API
  // remain the disposable integration fixture. No hardware session is started.
  let mode:'normal'|'failed'|'disconnected'|'active'='normal';
  const transitionTimeout=20000;
  await page.route('**/api/v1/station',route=>{
    if(mode==='failed')return route.abort('failed');
    const report=mode==='disconnected'?{...station,instanceId:'f'.repeat(32),coreConnection:'NOT_CONNECTED',state:'NO_ACTIVE_SESSION',sessionId:null,sessionViewId:null}
      :mode==='active'?{...station,state:'SESSION_ACTIVE',sessionId:'synthetic-other-session',sessionViewId:'e'.repeat(32)}:station;
    return route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify(report)});
  });
  await page.route('**/api/v1/inspection',route=>route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify({
    ...inspection,sessionId:mode==='active'?'synthetic-other-session':null,
  })}));
  mode='failed';
  await expect(page.getByRole('dialog',{name:'Connection lost'})).toBeVisible({timeout:transitionTimeout});
  await expect(page.locator('.desktop')).toBeHidden();
  await expect(page.getByRole('table')).toHaveCount(0);
  mode='normal';
  await expect(editor).toBeVisible({timeout:transitionTimeout});
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer',{timeout:transitionTimeout});
  await expect(save).toBeEnabled({timeout:transitionTimeout});

  await page.route('**/api/v1/auth/session',route=>route.abort('failed'));
  await expect(page.getByRole('dialog',{name:'Connection lost'})).toBeVisible({timeout:transitionTimeout});
  await expect(page.locator('.desktop')).toBeHidden();
  await expect(page.getByRole('table')).toHaveCount(0);
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Connection lost'})).toBeVisible({timeout:transitionTimeout});
  await page.unroute('**/api/v1/auth/session');
  await expect(editor).toBeVisible({timeout:transitionTimeout});
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer',{timeout:transitionTimeout});
  await expect(save).toBeEnabled({timeout:transitionTimeout});

  mode='disconnected';
  await expect(editor).toContainText('Core connection is unavailable',{timeout:transitionTimeout});
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer',{timeout:transitionTimeout});
  await expect(manufacturer).toBeDisabled();
  await expect(save).toBeDisabled();
  mode='normal';
  await expect(save).toBeEnabled({timeout:transitionTimeout});

  mode='active';
  await expect(editor).toContainText('Core has an active session',{timeout:transitionTimeout});
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer',{timeout:transitionTimeout});
  await expect(save).toBeDisabled();
  mode='normal';
  await expect(editor).toBeVisible({timeout:transitionTimeout});
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer',{timeout:transitionTimeout});
  await expect(save).toBeEnabled({timeout:transitionTimeout});
  // Preservation is in component memory only, never browser persistence.
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('Unsaved synthetic manufacturer');

  await page.route('**/api/v1/auth/session',route=>route.fulfill({status:401,contentType:'application/json; charset=utf-8',body:JSON.stringify({schema:'vision.api.error.v1',code:'ACCESS_DENIED'})}));
  await expect(page.getByLabel('User name',{exact:true})).toBeEnabled({timeout:transitionTimeout});
  await expect(page.locator('.desktop')).toHaveCount(0);
  await expect(page.locator('[data-editor-dirty]')).toHaveCount(0);
});

for(const change of ['role','user'] as const){
  test('authenticated '+change+' change clears the previous working copy',async({page})=>{
    const {editor}=await newEditor(page,'identity-'+change);
    const identity=await (await page.request.get('/api/v1/auth/session')).json();
    await page.route('**/api/v1/auth/session',route=>route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify({
      ...identity,...(change==='role'?{role:'reader'}:{username:'synthetic-other-owner'}),
    })}));
    await page.clock.fastForward(15100);
    await expect(page.locator('.vision-workspace')).toBeVisible();
    await expect(page.locator('.desktop .mode-banner')).toContainText(change==='role'?'Read only':'synthetic-other-owner');
    await expect(editor).toHaveCount(0);
    await expect(page.locator('[data-editor-dirty]')).toHaveCount(0);
  });
}

test('Core reconnect discards previous READY evidence until a fresh inspection report arrives',async({page})=>{
  const {editor}=await newEditor(page,'readiness-reconnect');
  const station=await (await page.request.get('/api/v1/station')).json();
  const inspection=await (await page.request.get('/api/v1/inspection')).json();
  const ready={...inspection,
    devices:inspection.devices.map((device:Record<string,unknown>)=>({...device,availability:'ACTIVE',readiness:'READY'})),
    selections:[{selectionId:'synthetic-selection',family:'synthetic-family',variant:'synthetic-variant',revision:'r1',physicalState:'synthetic-state',recipe:'synthetic-recipe'}],
    blockers:[],startAllowed:true,closeAllowed:false,
  };
  let connected=true,holdInspection=false;
  let releaseInspection:(()=>void)|undefined;
  const operations:string[]=[];
  page.on('request',request=>{if(request.method()==='POST'&&request.url().includes('/inspection/'))operations.push(request.url());});
  await page.route('**/api/v1/station',route=>route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify(connected?station:{
    ...station,instanceId:'d'.repeat(32),coreConnection:'NOT_CONNECTED',state:'NO_ACTIVE_SESSION',sessionId:null,sessionViewId:null,
  })}));
  await page.route('**/api/v1/inspection',async route=>{
    if(holdInspection)await new Promise<void>(resolve=>{releaseInspection=resolve;});
    await route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify(ready)});
  });
  await page.getByRole('tab',{name:'System Status',exact:true}).click();
  const status=page.locator('[data-module="status"]');
  const readyCells=status.getByRole('cell',{name:'READY',exact:true});
  const start=status.getByRole('button',{name:'Start inspection session',exact:true});
  await page.clock.fastForward(5100);
  await expect(readyCells).toHaveCount(4);
  await status.getByLabel('Declared ECU and recipe',{exact:true}).selectOption('synthetic-selection');
  await expect(start).toBeEnabled();
  connected=false;
  await page.clock.fastForward(5100);
  await expect(status).toContainText('Vision Core is not connected');
  await expect(readyCells).toHaveCount(0);
  connected=true;holdInspection=true;
  await page.clock.fastForward(5100);
  await expect.poll(()=>releaseInspection!==undefined).toBe(true);
  // Immediate checks prevent a timeout from concealing a stale READY flash.
  expect(await readyCells.count()).toBe(0);
  expect(await start.count()).toBe(0);
  holdInspection=false;releaseInspection!();
  await expect(readyCells).toHaveCount(4);
  await expect(start).toBeDisabled();
  await expect(status.getByLabel('Declared ECU and recipe',{exact:true})).toHaveValue('');
  await page.getByRole('tab',{name:'ECU Library',exact:true}).click();
  await expect(editor.getByLabel('Manufacturer (optional)',{exact:true})).toHaveValue('Unsaved synthetic manufacturer');
  expect(operations).toEqual([]);
});
