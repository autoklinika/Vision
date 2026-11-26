import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReadOnlyVisionClient } from './types';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from './libraryContract';
import {searchLibraryPages} from './librarySearch';
import type {LibrarySearch, LibrarySearchCriteria} from './librarySearch';

export type LibraryView = Readonly<{
  status: 'NOT_REQUESTED' | 'LOADING' | 'AVAILABLE' | 'ACCESS_DENIED' | 'UNAVAILABLE' | 'DISABLED';
  library: LibraryReport | null; detail: LibraryDetail | null; history: LibraryHistory | null;
  refreshing?: boolean;
  search?: LibrarySearch;
}>;
export type LibraryControls = Readonly<{
  view: LibraryView; refreshLibrary: () => void; browseEntry: (entry: LibraryEntry) => void;
  libraryPage: (direction: 'previous' | 'next') => void; historyPage: (direction: 'previous' | 'next') => void;
  autoRefresh?: boolean;
  searchLibrary: (criteria: LibrarySearchCriteria | null) => void;
}>;
const empty = (status: LibraryView['status']): LibraryView => ({status, library: null, detail: null, history: null});

/** Ephemeral authorized presentation: list, optional bounded search and detail/history. */
export function useLibraryView(client: ReadOnlyVisionClient, intervalMs = 0, owner = ''): LibraryControls {
  const enabled = client.mode === 'real' && !!client.readLibrary && !!client.readLibraryEntry && !!client.readLibraryHistory;
  // A -> disconnected -> A is a new observation, even with the same IDs.
  const ownerToken = useMemo(() => Symbol(owner), [owner]);
  const [ownedView, setOwnedView] = useState(() => ({owner: ownerToken, view: empty(enabled ? 'NOT_REQUESTED' : 'DISABLED')}));
  // Mask the old owner synchronously, before effects and late requests settle.
  const view = ownedView.owner === ownerToken ? ownedView.view : empty(enabled ? 'NOT_REQUESTED' : 'DISABLED');
  const setView = (next: LibraryView) => setOwnedView({owner: ownerToken, view: next});
  const busy = useRef(false);
  const generation = useRef(0);
  const refreshRef = useRef<() => void>(() => {});
  useEffect(() => () => { generation.current++; busy.current = false; }, [ownerToken, enabled]);

  async function run(read: (current:()=>boolean) => Promise<LibraryView>, quiet = false) {
    if (!enabled || busy.current) return;
    busy.current = true;
    const current = ++generation.current;
    setView(quiet && view.library ? {...view, refreshing: true} : empty('LOADING'));
    try {
      const result = await read(()=>current===generation.current);
      if (current === generation.current) setView(result);
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally { if (current === generation.current) busy.current = false; }
  }
  function refreshLibrary(quiet = false, requested?:LibrarySearchCriteria|null) {
    const previous = view;
    const criteria = requested===undefined ? previous.search?.criteria : requested;
    void run(async current => {
      let result = await client.readLibrary!();
      if (result.status !== 'AVAILABLE') return empty(result.status);
      let library=result.report;
      let search:LibrarySearch|undefined;
      const preserve=quiet && requested===undefined;
      if(criteria){
        if(preserve && previous.search && previous.library?.viewId===library.viewId &&
            previous.library.source===library.source && previous.library.libraryId===library.libraryId &&
            previous.library.totalCount===library.totalCount){
          search=previous.search;
        }else{
          const found=await searchLibraryPages(library,criteria,client.readLibrary!,current);
          if(found.status!=='AVAILABLE')return empty(found.status);
          search=found.report;
          if(preserve && previous.search){
            search={...search,after:Math.min(previous.search.after, Math.max(0,Math.floor((search.hits.length-1)/50)*50))};
          }
        }
      }else if (preserve && previous.library && previous.library.after > 0 && previous.library.after < library.totalCount) {
        result = await client.readLibrary!(library, previous.library.after);
        if (result.status !== 'AVAILABLE') return empty(result.status);
        library=result.report;
      }
      const base:LibraryView={status:'AVAILABLE',library,detail:null,history:null,search};
      if (!preserve || !previous.detail || !current()) return base;
      const hit=search?.hits.find(row=>row.entry.entryId===previous.detail!.entry.entryId);
      const selected=search?hit?.entry:library.entries.find(entry=>entry.entryId===previous.detail!.entry.entryId);
      if(!selected)return base;
      if(hit)library=hit.page;
      if(previous.library?.viewId===library.viewId && previous.library.libraryId===library.libraryId && previous.library.source===library.source){
        return {...base,library,detail:previous.detail,history:previous.history};
      }
      const detail=await client.readLibraryEntry!(library,selected);
      if(detail.status!=='AVAILABLE')return empty(detail.status);
      if(!detail.report.profile || !current())return {...base,library,detail:detail.report};
      const after=previous.history && previous.history.after<detail.report.profile.historyCount?previous.history.after:0;
      const history=await client.readLibraryHistory!(detail.report,after);
      return history.status==='AVAILABLE'?{...base,library,detail:detail.report,history:history.report}:empty(history.status);
    },quiet);
  }
  function searchLibrary(criteria:LibrarySearchCriteria|null){
    refreshLibrary(true,criteria && (criteria.query.trim()||criteria.kind!=='all')?{...criteria,query:criteria.query.trim()}:null);
  }
  function libraryPage(direction: 'previous' | 'next') {
    if(busy.current)return;
    if(view.search){
      const after=view.search.after+(direction==='previous'?-50:50);
      if(after>=0 && after<view.search.hits.length)setView({...view,detail:null,history:null,search:{...view.search,after}});
      return;
    }
    const library = view.library;
    if (!library) return;
    const after = direction === 'previous' ? library.after - 50 : library.nextAfter;
    if (after === null || after < 0) return;
    void run(async () => {
      const result = await client.readLibrary!(library, after);
      return result.status === 'AVAILABLE' ? {status: 'AVAILABLE', library: result.report, detail: null, history: null} : empty(result.status);
    });
  }
  function browseEntry(entry: LibraryEntry) {
    const search=view.search;
    const hit=search?.hits.find(row=>row.entry.entryId===entry.entryId);
    if(search&&!hit)return;
    const library=hit?.page??view.library;
    if(!library)return;
    void run(async current=>{
      const result=await client.readLibraryEntry!(library,entry);
      if(result.status!=='AVAILABLE')return empty(result.status);
      const detail=result.report;
      if(!detail.profile||!current())return {status:'AVAILABLE',library,detail,history:null,search};
      const history=await client.readLibraryHistory!(detail);
      return history.status==='AVAILABLE'?{status:'AVAILABLE',library,detail,history:history.report,search}:empty(history.status);
    },!!search);
  }
  function historyPage(direction: 'previous' | 'next') {
    const {library, detail, history} = view;
    if (!library || !detail || !history) return;
    const after = direction === 'previous' ? history.after - 50 : history.nextAfter;
    if (after === null || after < 0) return;
    void run(async () => {
      const result = await client.readLibraryHistory!(detail, after);
      return result.status === 'AVAILABLE' ? {status: 'AVAILABLE', library, detail, history: result.report,search:view.search} : empty(result.status);
    });
  }
  useEffect(() => { refreshRef.current = () => refreshLibrary(true); });
  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    const first = window.setTimeout(() => refreshRef.current(), 0);
    const timer = window.setInterval(() => refreshRef.current(), intervalMs);
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [enabled, intervalMs, ownerToken]);
  return {view, refreshLibrary: () => refreshLibrary(intervalMs > 0), browseEntry, libraryPage, historyPage, searchLibrary, autoRefresh: intervalMs > 0};
}
