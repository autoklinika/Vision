import {expect,test} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {librarySections} from '../../src/api/libraryContract';
const fixture=JSON.parse(readFileSync(new URL('../fixtures/editor-profile.json',import.meta.url),'utf8'));

test('actual ECU editor: neutral forms, measurements, images, conflict protection and history',async({page})=>{
  test.setTimeout(120000);
  const credentials=JSON.parse(readFileSync('../.station-test-auth.json','utf8'));
  const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.getByLabel('User name',{exact:true}).fill(credentials.username);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.locator('.vision-workspace')).toBeVisible();
  const identity=await (await page.request.get('/api/v1/auth/session')).json();
  expect(identity.role).toBe('operator');
  await page.getByRole('button', {name: 'Open navigation', exact: true}).click();
  await page.getByRole('dialog', {name: 'Navigation', exact: true}).getByRole('button', {name:'ECU Library',exact:true}).click();
  const library=page.locator('[data-module="ecu"]');
  const newProfile = library.getByRole('button',{name:'New profile',exact:true});
  await expect(newProfile).toHaveClass(/fui-Button/);
  await newProfile.click();
  const editor=library.getByRole('region',{name:'ECU reference editor'});
  const button=(name:string)=>editor.getByRole('button',{name,exact:true});
  const label=(name:string)=>editor.getByLabel(name,{exact:true});
  const section=async(name:string)=>{await label('Section').selectOption(name);};
  await expect(editor.locator('.fui-Input')).toHaveCount(5);
  await expect(button('Create draft')).toBeDisabled();
  await label('ECU family').fill('synthetic-family');
  await label('Variant ID').fill('synthetic-variant');
  await label('New profile ID').fill('browser-neutral');
  await label('Revision').fill('r1');
  await label('Display name').fill('Browser neutral draft');
  await expect(button('Create draft')).toHaveClass(/fui-Button/);
  await button('Create draft').click();
  await expect(editor).toContainText('Draft saved in Core.');
  await expect(editor).toContainText('DRAFT / NOT_READY');
  await expect(button('Check structure')).toHaveClass(/fui-Button/);
  await button('Check structure').click();
  await expect(editor).toContainText('Valid structure · NOT_READY');
  await expect(editor).toContainText('Structural validation only');

  await section('identity');
  await label('Manufacturer (optional)').fill('Synthetic browser manufacturer');
  await section('provenance_release');
  await button('Add source').click();
  const source=editor.getByRole('group',{name:'source 1',exact:true});
  await source.getByLabel('Source ID',{exact:true}).fill('source-test');
  await source.getByLabel('Measurement date',{exact:true}).fill('2026-01-01');
  await source.getByLabel('Source status',{exact:true}).selectOption('MEASURED');
  await source.getByLabel('Instrument / method',{exact:true}).fill('Synthetic fixture instrument');
  await source.getByLabel('Datum',{exact:true}).fill('Fixture origin');
  await source.getByLabel('Measurement uncertainty (mm)',{exact:true}).fill('0,25');
  await source.getByLabel('Evidence reference',{exact:true}).fill('Synthetic browser evidence');
  await section('physical_states');
  await button('Add physical state').click();
  const state=editor.getByRole('group',{name:'physical state 1',exact:true});
  await state.getByLabel('State ID',{exact:true}).fill('state-test');
  await state.getByLabel('State name',{exact:true}).fill('Synthetic state');
  await state.getByLabel('Measurement source (optional)',{exact:true}).selectOption('source-test');
  await section('geometry');
  await button('Add envelope').click();
  const envelope=editor.getByRole('group',{name:'envelope 1',exact:true});
  await envelope.getByLabel('Geometry ID',{exact:true}).fill('envelope-test');
  await envelope.getByLabel('Physical state',{exact:true}).selectOption('state-test');
  await expect(envelope.getByLabel('Maximum envelope X (mm)',{exact:true})).toHaveValue('');
  await envelope.getByLabel('Maximum envelope X (mm)',{exact:true}).fill('100,25');
  await envelope.getByLabel('Maximum envelope Y (mm)',{exact:true}).fill('80');
  await envelope.getByLabel('Measurement source',{exact:true}).selectOption('source-test');
  await envelope.getByLabel('Measurement uncertainty (mm)',{exact:true}).fill('0,25');
  await button('Save draft generation').click();
  await expect(editor).toContainText('Maximum envelope / Z');
  await expect(button('Save draft generation')).toBeEnabled();
  await envelope.getByLabel('Maximum envelope Z (mm)',{exact:true}).fill('20');
  await section('physical_states');
  await state.getByLabel('Geometry (optional)',{exact:true}).selectOption('envelope-test');
  await section('identity');
  await expect(label('Manufacturer (optional)')).toHaveValue('Synthetic browser manufacturer');

  // Cancellation of the window-close prompt must preserve unsaved fields.
  page.once('dialog',dialog=>dialog.dismiss());
  await page.getByRole('button',{name:'Close ECU Library',exact:true}).click();
  await expect(editor).toBeVisible();
  await expect(label('Manufacturer (optional)')).toHaveValue('Synthetic browser manufacturer');
  await button('Save draft generation').click();
  await expect(editor).toContainText('Draft saved in Core.');
  await expect(button('Save draft generation')).toBeDisabled();

  // Import the actual synthetic PNG. No file path or digest is supplied by the form.
  await section('reference_assets');
  await label('Image file').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAANklEQVQ4Ea3BAQEAAAABIJZ33QlV5KHIQ5GHIg9FHoo8FHko8lDkochDkYciD0UeijwUeSjyMLa3F+G+cxutAAAAAElFTkSuQmCC','base64')});
  await label('Imported asset ID').fill('synthetic.image');
  await label('Image physical state').selectOption('state-test');
  await label('Image source').selectOption('source-test');
  await button('Import reference image').click();
  await expect(editor).toContainText('Image imported as UNVERIFIED.');
  await expect(editor.getByRole('group',{name:'asset 1',exact:true}).getByLabel('Evidence verified (declaration)',{exact:true})).not.toBeChecked();
  await button('Save draft generation').click();
  await expect(editor).toContainText('Draft saved in Core.');
  await label('Saved image preview').selectOption('synthetic.image');
  await button('Preview saved image').click();
  const image=editor.getByRole('img',{name:'Stored reference image synthetic.image',exact:true});
  await expect(image).toBeVisible();
  await expect.poll(()=>image.evaluate((node:HTMLImageElement)=>node.naturalWidth)).toBe(24);
  await button('Close preview').click();

  const station=await (await page.request.get('/api/v1/station')).json();
  const headers={Origin:'http://127.0.0.1:18492','X-Vision-Client':'webgui'};
  const base='/api/v1/library/editor/';
  const post=(action:string,data:unknown)=>page.request.post(base+action,{headers,data:data as object});
  const opened=await (await post('open',{instanceId:station.instanceId,key:'browser-neutral'})).json();
  expect(opened.document.geometry.per_physical_state[0].envelope_xyz_mm).toEqual([100.25,80,20]);
  expect(opened.document.provenance_release.measurement_sources[0].uncertainty_mm).toBe(.25);
  expect(opened.document.reference_assets.assets[0].verified).toBe(false);
  expect(opened.document.provenance_release.asset_hashes[0].sha256).toBe(opened.document.reference_assets.assets[0].sha256);

  // Concurrent edit: old ETag must not overwrite the saved document.
  opened.document.identity.aliases=['other-client'];
  opened.document.identity.oem_part_numbers=['OE-SYN-12345'];
  expect((await post('save',{instanceId:station.instanceId,key:opened.key,etag:opened.etag,document:opened.document})).status()).toBe(200);
  await section('identity');
  await label('Manufacturer (optional)').fill('stale local text');
  await button('Save draft generation').click();
  await expect(editor).toContainText('Core rejected this change');
  await expect(button('Save draft generation')).toBeDisabled();
  page.once('dialog',dialog=>dialog.accept());
  await button('Reload latest').click();
  await expect(editor).toContainText('Draft loaded from Core.');
  await expect(label('Aliases 1')).toHaveValue('other-client');
  await expect(label('Manufacturer (optional)')).toHaveValue('Synthetic browser manufacturer');

  await editor.getByText('Clone saved draft to a new revision',{exact:true}).click();
  await label('New profile ID').fill('browser-neutral-r2');
  await label('New revision').fill('r2');
  await button('Clone saved revision').click();
  await expect(editor).toContainText('New draft revision created.');
  await button('Close editor').click();
  await expect(library.getByRole('button',{name:'Browse Browser neutral draft r2',exact:true})).toBeVisible();

  // A populated synthetic fixture exercises every nested presentation form.
  const filled=await (await post('create_empty',{instanceId:station.instanceId,family:fixture.metadata.family_id,
    variant:fixture.metadata.variant_id,key:fixture.metadata.profile_id,revision:'r1',displayName:fixture.metadata.display_name})).json();
  expect((await post('save',{instanceId:station.instanceId,key:filled.key,etag:filled.etag,document:fixture})).status()).toBe(200);
  await library.getByRole('button',{name:'Refresh library',exact:true}).click();
  await library.getByRole('button',{name:'Browse Synthetic form fixture r1',exact:true}).click();
  await library.getByRole('button',{name:'Open reference editor',exact:true}).click();
  await button('Load draft fixture-reference').click();
  await expect(editor).toContainText('Draft loaded from Core.');
  for(const name of librarySections){
    await section(name);
    await expect(editor.locator('.editor-section-form')).toBeVisible();
    await expect(editor.locator('.editor-section-form :is(.fui-Input,.fui-Select,.fui-Checkbox)').first()).toBeVisible();
  }
  await section('photography_recipes');
  const view=editor.getByRole('group',{name:'camera view 1',exact:true});
  await view.getByLabel('Camera position Z (mm)',{exact:true}).fill('101,5');
  await section('thermal_recipes');
  await expect(editor.getByLabel('Thermal mode',{exact:true})).toHaveValue('relative_intensity');
  await section('validation_policies');
  await expect(editor.getByRole('group',{name:'policy 1',exact:true}).getByLabel('Metric 1',{exact:true})).toHaveValue('minimum');
  await expect(button('Check structure')).toHaveClass(/fui-Button/);
  await button('Check structure').click();
  await expect(editor).toContainText('Valid structure · NOT_READY');
  await button('Save draft generation').click();
  await expect(editor).toContainText('Draft saved in Core.');
  const final=await (await post('open',{instanceId:station.instanceId,key:filled.key})).json();
  const expected=structuredClone(fixture);
  expected.photography_recipes.recipes[0].views[0].camera_goal.translation_mm[2]=101.5;
  expect(final.document).toEqual(expected);
  // Submit a saved complete structure for independent review. It remains
  // unsigned and read-only; withdrawal creates a fresh active generation.
  page.once('dialog',dialog=>dialog.accept());
  await button('Submit for review').click();
  await expect(editor).toContainText('Submitted for review');
  await expect(editor).toContainText('Independent review authority is not configured on this Core.');
  await expect(button('Publish reviewed release')).toHaveCount(0);
  const exportEvent=page.waitForEvent('download');
  await button('Export review request').click();
  const download=await exportEvent;
  expect(download.suggestedFilename()).toBe('fixture-reference-review-request.json');
  const packageData=JSON.parse(readFileSync((await download.path())!,'utf8'));
  expect(packageData.schema).toBe('vision.reference-review-request.v1');
  expect(packageData.document).toEqual(expected);
  expect(packageData.submittedEtag).toMatch(/^"[a-f0-9]{64}"$/);
  await download.delete();
  await expect(button('Save draft generation')).toBeDisabled();
  await expect(label('Metric 1')).toBeDisabled();
  page.once('dialog',dialog=>dialog.accept());
  await button('Withdraw from review').click();
  await expect(editor).toContainText('Profile lifecycle updated.');
  await expect(label('Metric 1')).toBeEnabled();
  await button('Close editor').click();
  await library.getByRole('button',{name:'Browse Browser neutral draft r1',exact:true}).click();
  await library.getByRole('tab',{name:'Revision history (4)'}).click();
  await expect(library.getByRole('table',{name:'Reference revision history'})).toHaveClass(/fui-Table/);
  await expect(library.getByRole('table',{name:'Reference revision history'}).locator('tbody tr')).toHaveCount(4);
  await library.getByRole('tab',{name:'Saved profile',exact:true}).click();
  const viewer=library.getByRole('region',{name:'Saved profile viewer',exact:true});
  const generation=viewer.getByRole('combobox',{name:'Saved generation',exact:true});
  await generation.selectOption({index:1});
  await viewer.getByRole('button',{name:'Preview saved profile',exact:true}).click();
  await expect(viewer.getByRole('combobox',{name:'Section',exact:true})).toBeVisible();
  await viewer.getByRole('combobox',{name:'Section',exact:true}).selectOption('identity');
  await expect(viewer.getByLabel('Manufacturer (optional)',{exact:true})).toHaveValue('');
  await expect(viewer.getByLabel('Manufacturer (optional)',{exact:true})).toBeDisabled();
  await viewer.getByRole('button',{name:'Compare saved versions',exact:true}).click();
  await expect(viewer.getByRole('table',{name:'Version differences'})).toContainText('Synthetic browser manufacturer');
  await generation.selectOption('');
  await viewer.getByLabel('Compare with profile ID (optional)',{exact:true}).fill('browser-neutral-r2');
  await viewer.getByRole('button',{name:'Compare saved versions',exact:true}).click();
  await expect(viewer.getByRole('table',{name:'Version differences'})).toContainText('browser-neutral-r2');

  // Archive an existing saved revision, filter the catalog by lifecycle
  // and by the actual declared OEM number, then restore it.
  await library.getByRole('button',{name:'Open reference editor',exact:true}).click();
  await button('Load draft browser-neutral').click();
  await expect(editor).toContainText('Draft loaded from Core.');
  page.once('dialog',dialog=>dialog.accept());
  await button('Archive profile').click();
  await expect(editor).toContainText('Archived profile');
  await expect(button('Save draft generation')).toBeDisabled();
  await button('Close editor').click();
  const search=library.getByRole('textbox',{name:'Search ECU library',exact:true});
  await search.fill('OE-SYN-12345');
  await library.getByRole('combobox',{name:'Profile lifecycle',exact:true}).selectOption('ARCHIVED');
  await library.getByRole('button',{name:'Search library',exact:true}).click();
  const entries=library.getByRole('table',{name:'ECU library entries'});
  await expect(entries.locator('tbody tr')).toHaveCount(1);
  await expect(entries).toContainText('Archived profile');
  await entries.getByRole('button',{name:'Browse Browser neutral draft r1',exact:true}).click();
  await library.getByRole('button',{name:'Open reference editor',exact:true}).click();
  await button('Load draft browser-neutral').click();
  await expect(editor).toContainText('Archived profile');
  page.once('dialog',dialog=>dialog.accept());
  await button('Restore profile').click();
  await expect(editor).toContainText('Profile lifecycle updated.');
  await button('Close editor').click();
  await expect(entries.locator('tbody tr')).toHaveCount(0);
  await library.getByRole('button',{name:'Clear search',exact:true}).click();

  const after=await (await page.request.get('/api/v1/station')).json();
  expect(after).toMatchObject({instanceId:station.instanceId,state:'NO_ACTIVE_SESSION',coreConnection:'CONNECTED'});
  expect(errors).toEqual([]);
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('Synthetic browser manufacturer');

  // Responsive regression using the same authorized fixture.
  await page.setViewportSize({width:390,height:844});
  await library.getByRole('button',{name:'New profile',exact:true}).click();
  for(const name of ['ECU family','Variant ID','New profile ID','Display name']) {
    await expect(editor.getByLabel(name,{exact:true})).toHaveValue('');
  }
  await expect(editor.getByLabel('Revision',{exact:true})).toHaveValue('r1');
  await editor.getByLabel('ECU family',{exact:true}).fill('mobile-synthetic');
  await page.getByRole('tab',{name:'System Status',exact:true}).click();
  await page.getByRole('tab',{name:'ECU Library',exact:true}).click();
  await expect(editor.getByLabel('ECU family',{exact:true})).toHaveValue('mobile-synthetic');
  await expect(editor.getByRole('button',{name:'Create draft',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await editor.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
  // Live localization changes neither the draft owner nor the unsaved input.
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  await page.getByRole('dialog',{name:'Navigation',exact:true}).getByRole('button',{name:'Settings',exact:true}).click();
  await page.locator('[data-module="settings"]').getByLabel('Interface language',{exact:true}).selectOption('pl');
  await page.getByRole('tab',{name:'Biblioteka ECU',exact:true}).click();
  await expect(library.locator('.draft-editor').getByLabel('Rodzina ECU',{exact:true})).toHaveValue('mobile-synthetic');
  await expect(library.locator('.draft-editor').getByRole('button',{name:'Utwórz projekt',exact:true})).toBeDisabled();
  await page.getByRole('tab',{name:'Ustawienia',exact:true}).click();
  await page.locator('[data-module="settings"]').getByLabel('Język interfejsu',{exact:true}).selectOption('en');
  await page.getByRole('tab',{name:'ECU Library',exact:true}).click();
  await expect(editor.getByLabel('ECU family',{exact:true})).toHaveValue('mobile-synthetic');

});
