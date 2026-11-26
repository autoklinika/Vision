/** Search only the bounded, authorized catalog projection. Never load draft documents. */
import {isLibraryReport, matchesLibrary} from './libraryContract';
import type {LibraryEntry, LibraryReport} from './libraryContract';
import type {ProtectedResult} from './protectedAdapter';

export type LibraryKind = 'all' | LibraryEntry['kind'];
export type LibrarySearchCriteria = Readonly<{query: string; kind: LibraryKind}>;
export type LibrarySearchHit = Readonly<{entry: LibraryEntry; page: LibraryReport}>;
export type LibrarySearch = Readonly<{criteria: LibrarySearchCriteria; hits: readonly LibrarySearchHit[]; after: number}>;

const normalize = (value:string) => value.normalize('NFKC').toLowerCase();
export function matchesSearch(entry:LibraryEntry, criteria:LibrarySearchCriteria):boolean {
  if(criteria.kind!=='all' && entry.kind!==criteria.kind)return false;
  const fields=normalize([entry.displayName,entry.family,entry.variant,entry.profileId,entry.revision].join(' '));
  return normalize(criteria.query.trim()).split(/\s+/).every(token=>fields.includes(token));
}

/** Scan a single coherent view (max 512 entries / 11 pages). Abort instead of
 * showing partial or mixed results on changed view, denial, timeout or logout.
 */
export async function searchLibraryPages(first:LibraryReport, criteria:LibrarySearchCriteria,
  read:(prior:LibraryReport,after:number)=>Promise<ProtectedResult<LibraryReport>>,
  current:()=>boolean, clock:()=>number=()=>performance.now()):Promise<ProtectedResult<LibrarySearch>> {
  const unavailable={status:'UNAVAILABLE',report:null} as const;
  if(!isLibraryReport(first)||first.after!==0||criteria.query.length>160||
      !['all','CATALOG_RECORD','REFERENCE_DRAFT'].includes(criteria.kind))return unavailable;
  const hits:LibrarySearchHit[]=[];
  const seen=new Set<string>();
  const deadline=clock()+30000;
  let page=first;
  for(let i=0;i<11;i++){
    if(!current()||clock()>deadline)return unavailable;
    for(const entry of page.entries){
      if(seen.has(entry.entryId))return unavailable;
      seen.add(entry.entryId);
      if(matchesSearch(entry,criteria))hits.push({entry,page});
    }
    if(page.nextAfter===null){
      return seen.size===first.totalCount?{status:'AVAILABLE',report:{criteria,hits,after:0}}:unavailable;
    }
    const after=page.nextAfter;
    const result=await read(first,after);
    if(!current())return unavailable;
    if(result.status!=='AVAILABLE')return result;
    if(!isLibraryReport(result.report)||!matchesLibrary(result.report,first,after))return unavailable;
    page=result.report;
  }
  return unavailable;
}
