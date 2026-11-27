import {expect,it,vi} from 'vitest';
import {matchesSearch,searchLibraryPages} from '../src/api/librarySearch';
import type {LibrarySearchCriteria} from '../src/api/librarySearch';
import {catalogEntry,draftEntry,libraryFixture} from './fixtures/library';
import type {LibraryReport} from '../src/api/libraryContract';
import type {ProtectedResult} from '../src/api/protectedAdapter';

const available=(report:LibraryReport):ProtectedResult<LibraryReport>=>({status:'AVAILABLE',report});
it('matches all entered terms across projected fields, case-insensitively, and filters record type',()=>{
  expect(matchesSearch(draftEntry,{query:'etc3 R1 SYNTHETIC',kind:'REFERENCE_DRAFT'})).toBe(true);
  expect(matchesSearch(draftEntry,{query:'etc3',kind:'CATALOG_RECORD'})).toBe(false);
  expect(matchesSearch({...catalogEntry,displayName:'Żółty moduł'},{query:'ŻÓŁTY',kind:'all'})).toBe(true);
  expect(matchesSearch(catalogEntry,{query:'not present',kind:'all'})).toBe(false);
});
it('searches beyond the first page and preserves the exact source page for detail reads',async()=>{
  const first=libraryFixture(101);
  const read=vi.fn(async(_p:LibraryReport,after:number)=>available(libraryFixture(101,after)));
  const result=await searchLibraryPages(first,{query:'catalog_100',kind:'all'},read,()=>true);
  expect(result.status).toBe('AVAILABLE');
  expect(result.report?.hits.map(h=>[h.entry.profileId,h.page.after])).toEqual([['catalog_100',100]]);
  expect(read.mock.calls.map(c=>c[1])).toEqual([50,100]);
});
it('returns no partial results on stale view, duplicate cross-page ID, denial, or cancelled ownership',async()=>{
  const first=libraryFixture(51);
  const criteria:LibrarySearchCriteria={query:'',kind:'all'};
  const second=libraryFixture(51,50);
  for(const result of [
    available({...second,viewId:'a'.repeat(64)}),
    available({...second,entries:[first.entries[0]]}),
    {status:'ACCESS_DENIED',report:null} as const,
  ]){
    const actual=await searchLibraryPages(first,criteria,async()=>result,()=>true);
    expect(actual.report).toBeNull();
    expect(actual.status).toBe(result.status==='ACCESS_DENIED'?'ACCESS_DENIED':'UNAVAILABLE');
  }
  let current=true;
  const result=await searchLibraryPages(first,criteria,async()=>{current=false;return available(second);},()=>current);
  expect(result).toEqual({status:'UNAVAILABLE',report:null});
});
it('bounds the scan and never presents incomplete results after the deadline',async()=>{
  const first=libraryFixture(512);
  const read=vi.fn(async(_p:LibraryReport,after:number)=>available(libraryFixture(512,after)));
  const result=await searchLibraryPages(first,{query:'',kind:'all'},read,()=>true);
  expect(result.report?.hits.length).toBe(512);
  expect(read).toHaveBeenCalledTimes(10);
  let time=0;
  const late=await searchLibraryPages(first,{query:'',kind:'all'},async()=>{time=31000;return available(libraryFixture(512,50));},()=>true,()=>time);
  expect(late).toEqual({status:'UNAVAILABLE',report:null});
});
