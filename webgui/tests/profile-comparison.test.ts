import {expect,it} from 'vitest';
import {readFileSync} from 'node:fs';
import {compareProfiles} from '../src/station/profileComparison';
import {matchesSearch} from '../src/api/librarySearch';
import {draftEntry} from './fixtures/library';
import {isLibraryEntry} from '../src/api/libraryContract';
import type {DraftDocument} from '../src/station/draftContract';

it('compares exact nested measurement and identity changes without mutating either saved version',()=>{
  const original=JSON.parse(readFileSync(new URL('./fixtures/editor-profile.json',import.meta.url),'utf8'));
  const later=structuredClone(original);
  later.geometry.per_physical_state[0].envelope_xyz_mm[2]=999;
  later.identity.manufacturer='New manufacturer';
  const result=compareProfiles(original,later);
  expect(result.truncated).toBe(false);
  expect(result.differences.some(d=>d.section==='geometry'&&d.after==='999')).toBe(true);
  expect(result.differences.some(d=>d.section==='identity'&&d.path==='manufacturer')).toBe(true);
  expect(compareProfiles(original,original)).toEqual({differences:[],truncated:false});
  expect(original.identity.manufacturer).not.toBe('New manufacturer');
});
it('bounds excessive differences explicitly',()=>{
  const a={identity:{aliases:Array.from({length:300},(_,i)=>String(i))}} as unknown as DraftDocument;
  const b={identity:{aliases:Array.from({length:300},(_,i)=>String(i+1000))}} as unknown as DraftDocument;
  const r=compareProfiles(a,b);
  expect(r.differences).toHaveLength(256);
  expect(r.truncated).toBe(true);
});
it('searches manufacturer/part number and exact administrative state',()=>{
  const entry={...draftEntry,lifecycle:'ARCHIVED' as const,searchTerms:'Synthetic Manufacturer OE-123',searchComplete:true};
  expect(isLibraryEntry(entry)).toBe(true);
  expect(matchesSearch(entry,{query:'manufacturer oe-123',kind:'REFERENCE_DRAFT',lifecycle:'ARCHIVED'})).toBe(true);
  expect(matchesSearch(entry,{query:'oe-123',kind:'all',lifecycle:'ACTIVE'})).toBe(false);
  expect(isLibraryEntry({...entry,lifecycle:'APPROVED'})).toBe(false);
  expect(isLibraryEntry({...entry,searchComplete:undefined})).toBe(false);
});
