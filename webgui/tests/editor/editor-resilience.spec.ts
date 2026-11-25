import {expect,test} from '@playwright/test';
import type {Page,Request} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {openApp} from '../browser/helpers';

async function newEditor(page:Page,key:string,create=true){
  await page.clock.install();
  const credentials=JSON.parse(readFileSync('../.station-test-auth.json','utf8'));
  await page.goto('/');
  await page.getByLabel('User name',{exact:true}).fill(credentials.username);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('region', {name:'System Status',exact:true, includeHidden: true})).toBeVisible();
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button',{name:'ECU Library',exact:true}).click();
  const library=page.getByRole('region', {name:'ECU Library',exact:true, includeHidden: true});
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
  // Settle real HTTP observations before moving virtual time. Otherwise a
  // clock jump can expire a request that has only spent milliseconds in flight.
  const observations=new Set<Request>();
  page.on('request',request=>{
    if(request.method()==='GET'&&new URL(request.url()).pathname.startsWith('/api/v1/'))observations.add(request);
  });
  page.on('requestfinished',request=>observations.delete(request));
  page.on('requestfailed',request=>observations.delete(request));
  // Exercise pre-create discard protection in the same authenticated flow.
  // The suite stays within the real five-login limit; no throttling override.
  const {library,editor}=await newEditor(page,'resilience-profile',false);
  const signOutRequests:string[]=[];
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/v1/auth/logout'))signOutRequests.push(request.url());});
  await openApp(page,'System Status');
  await expect(library).toBeHidden();
  await expect(library).toHaveCount(1);
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  expect(signOutRequests).toEqual([]);
  await openApp(page,'Control Panel');
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Reset workspace',exact:true}).click();
  await expect(page.getByRole('heading',{level:1,name:'Control Panel',exact:true})).toBeVisible();
  await openApp(page,'ECU Library');
  await expect(editor.getByLabel('ECU family',{exact:true})).toHaveValue('resilience-family');
  page.once('dialog',dialog=>dialog.dismiss());
  await editor.getByRole('button',{name:'Close editor',exact:true}).click();
  await expect(editor.getByLabel('New profile ID',{exact:true})).toHaveValue('resilience-profile');
  await editor.getByRole('button',{name:'Create draft',exact:true}).click();
  await expect(editor).toContainText('Draft saved in Core.');
  await editor.getByLabel('Section',{exact:true}).selectOption('identity');
  await editor.getByLabel('Manufacturer (optional)',{exact:true}).fill('Unsaved synthetic manufacturer');
  await openApp(page,'Inspection Manager');
  await expect(library).toBeHidden();
  await openApp(page,'ECU Library');
  await expect(editor.getByLabel('Manufacturer (optional)',{exact:true})).toHaveValue('Unsaved synthetic manufacturer');
  const manufacturer=editor.getByLabel('Manufacturer (optional)',{exact:true});
  const save=editor.getByRole('button',{name:'Save draft generation',exact:true});
  // A hidden in-flight editor operation still blocks destructive global actions.
  let releaseValidation:(()=>void)|undefined;
  await page.route('**/api/v1/library/editor/validate_structure',async route=>{
    await new Promise<void>(resolve=>{releaseValidation=resolve;});
    await route.continue();
  },{times:1});
  await editor.getByRole('button',{name:'Check structure',exact:true}).click();
  await expect.poll(()=>releaseValidation!==undefined).toBe(true);
  await expect(editor).toHaveAttribute('data-editor-busy','true');
  await openApp(page,'System Status');
  const blockedActions:string[]=[];
  page.once('dialog',dialog=>{blockedActions.push(dialog.type());void dialog.accept();});
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await openApp(page,'Control Panel');
  page.once('dialog',dialog=>{blockedActions.push(dialog.type());void dialog.accept();});
  await page.getByRole('button',{name:'Reset workspace',exact:true}).click();
  expect(blockedActions).toEqual(['alert','alert']);
  expect(signOutRequests).toEqual([]);
  releaseValidation!();
  await openApp(page,'ECU Library');
  await expect(editor).toHaveAttribute('data-editor-busy','false');
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  const station=await (await page.request.get('/api/v1/station')).json();
  const inspection=await (await page.request.get('/api/v1/inspection')).json();
  // Keep transport states deterministic while the actual form/storage/API
  // remain the disposable integration fixture. No hardware session is started.
  let mode:'normal'|'failed'|'disconnected'|'active'='normal';
  async function advanceObservation(milliseconds:number,nextMode:typeof mode=mode){
    await expect.poll(()=>observations.size,{message:'Previous API observations have settled'}).toBe(0);
    mode=nextMode;
    await page.clock.fastForward(milliseconds);
  }
  await page.route('**/api/v1/station',route=>{
    if(mode==='failed')return route.abort('failed');
    const report=mode==='disconnected'?{...station,instanceId:'f'.repeat(32),coreConnection:'NOT_CONNECTED',state:'NO_ACTIVE_SESSION',sessionId:null,sessionViewId:null}
      :mode==='active'?{...station,state:'SESSION_ACTIVE',sessionId:'synthetic-other-session',sessionViewId:'e'.repeat(32)}:station;
    return route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify(report)});
  });
  await page.route('**/api/v1/inspection',route=>route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify({
    ...inspection,sessionId:mode==='active'?'synthetic-other-session':null,
  })}));
  // An open mobile drawer must release its document-level focus trap when
  // the retained workspace is hidden behind the connection recovery screen.
  const desktopViewport=page.viewportSize()!;
  await page.setViewportSize({width:360,height:780});
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await advanceObservation(5100,'failed');
  const connection=page.getByRole('dialog',{name:'Connection lost'});
  await expect(connection).toBeVisible();
  await expect(page.locator('.app-shell')).toBeHidden();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toHaveCount(0);
  await expect(page.getByRole('table')).toHaveCount(0);
  const retry=connection.getByRole('button',{name:'Retry connection',exact:true});
  const reload=connection.getByRole('button',{name:'Reload interface',exact:true});
  const signOut=connection.getByRole('button',{name:'Sign out',exact:true});
  await retry.focus();
  await page.keyboard.press('Tab');
  await expect(reload).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(signOut).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Shift+Tab');
  await expect(retry).toBeFocused();
  await advanceObservation(5100,'normal');
  await expect(page.locator('.app-shell')).toBeVisible();
  const restoredNavigation=page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'ECU Library',exact:true});
  await expect(restoredNavigation).toHaveAttribute('aria-current','page');
  await expect(restoredNavigation).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Open navigation',exact:true})).toHaveAttribute('aria-expanded','false');
  await page.setViewportSize(desktopViewport);
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  await expect(save).toBeEnabled();

  await page.route('**/api/v1/auth/session',route=>route.abort('failed'),{times:1});
  await advanceObservation(15100);
  await expect(page.getByRole('dialog',{name:'Connection lost'})).toBeVisible();
  await expect(page.locator('.app-shell')).toBeHidden();
  await expect(page.getByRole('table')).toHaveCount(0);
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Connection lost'})).toBeVisible();
  await advanceObservation(5100);
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  await expect(save).toBeEnabled();

  await advanceObservation(5100,'disconnected');
  await expect(page.locator('.app-header')).toContainText('Session status unavailable');
  await expect(page.locator('.app-header')).not.toContainText('No active session');
  await expect(editor).toContainText('Core connection is unavailable');
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  await expect(manufacturer).toBeDisabled();
  await expect(save).toBeDisabled();
  await advanceObservation(5100,'normal');
  await expect(save).toBeEnabled();

  await advanceObservation(5100,'active');
  await expect(editor).toContainText('Core has an active session');
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  await expect(save).toBeDisabled();
  await advanceObservation(5100,'normal');
  await expect(manufacturer).toHaveValue('Unsaved synthetic manufacturer');
  await expect(save).toBeEnabled();
  // Preservation is in component memory only, never browser persistence.
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('Unsaved synthetic manufacturer');

  await page.route('**/api/v1/auth/session',route=>route.fulfill({status:401,contentType:'application/json; charset=utf-8',body:JSON.stringify({schema:'vision.api.error.v1',code:'ACCESS_DENIED'})}));
  await advanceObservation(15100);
  await expect(page.getByLabel('User name',{exact:true})).toBeEnabled();
  await expect(page.locator('.app-shell')).toHaveCount(0);
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
    await expect(page.locator('.app-shell')).toBeVisible();
    await expect(page.locator('.app-header')).toContainText(change==='role'?'Read only':'synthetic-other-owner');
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
  await openApp(page,'System Status');
  const status=page.getByRole('region', {name:'System Status',exact:true, includeHidden: true});
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
  await page.getByRole('navigation', {name: 'Main navigation'}).getByRole('button',{name:'ECU Library',exact:true}).click();
  await expect(editor.getByLabel('Manufacturer (optional)',{exact:true})).toHaveValue('Unsaved synthetic manufacturer');
  expect(operations).toEqual([]);
});
