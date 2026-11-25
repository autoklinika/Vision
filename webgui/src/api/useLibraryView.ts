import { useEffect, useRef, useState } from 'react';
import type { ReadOnlyVisionClient } from './types';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from './libraryContract';

export type LibraryView = Readonly<{
  status: 'NOT_REQUESTED' | 'LOADING' | 'AVAILABLE' | 'ACCESS_DENIED' | 'UNAVAILABLE' | 'DISABLED';
  library: LibraryReport | null; detail: LibraryDetail | null; history: LibraryHistory | null;
  refreshing?: boolean;
}>;
export type LibraryControls = Readonly<{
  view: LibraryView; refreshLibrary: () => void; browseEntry: (entry: LibraryEntry) => void;
  libraryPage: (direction: 'previous' | 'next') => void; historyPage: (direction: 'previous' | 'next') => void;
  autoRefresh?: boolean;
}>;
const empty = (status: LibraryView['status']): LibraryView => ({status, library: null, detail: null, history: null});

/** Ephemeral presentation only: one list page and one detail/history page. */
export function useLibraryView(client: ReadOnlyVisionClient, intervalMs = 0): LibraryControls {
  const enabled = client.mode === 'real' && !!client.readLibrary && !!client.readLibraryEntry && !!client.readLibraryHistory;
  const [view, setView] = useState<LibraryView>(() => empty(enabled ? 'NOT_REQUESTED' : 'DISABLED'));
  const busy = useRef(false);
  const generation = useRef(0);
  const refreshRef = useRef<() => void>(() => {});
  useEffect(() => () => { generation.current++; }, []);

  async function run(read: () => Promise<LibraryView>, quiet = false) {
    if (!enabled || busy.current) return;
    busy.current = true;
    const current = ++generation.current;
    setView(quiet && view.library ? {...view, refreshing: true} : empty('LOADING'));
    try {
      const result = await read();
      if (current === generation.current) setView(result);
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally { busy.current = false; }
  }
  function refreshLibrary(quiet = false) {
    const previous = view;
    void run(async () => {
      let result = await client.readLibrary!();
      if (result.status !== 'AVAILABLE') return empty(result.status);
      if (quiet && previous.library && previous.library.after > 0 && previous.library.after < result.report.totalCount) {
        result = await client.readLibrary!(result.report, previous.library.after);
        if (result.status !== 'AVAILABLE') return empty(result.status);
      }
      const library = result.report;
      if (!quiet || !previous.detail) return {status: 'AVAILABLE', library, detail: null, history: null};
      const selected = library.entries.find(entry => entry.entryId === previous.detail!.entry.entryId);
      if (!selected) return {status: 'AVAILABLE', library, detail: null, history: null};
      if (previous.library?.viewId === library.viewId && previous.library.libraryId === library.libraryId && previous.library.source === library.source) {
        return {status: 'AVAILABLE', library, detail: previous.detail, history: previous.history};
      }
      const detail = await client.readLibraryEntry!(library, selected);
      if (detail.status !== 'AVAILABLE') return empty(detail.status);
      if (!detail.report.profile) return {status: 'AVAILABLE', library, detail: detail.report, history: null};
      const after = previous.history && previous.history.after < detail.report.profile.historyCount ? previous.history.after : 0;
      const history = await client.readLibraryHistory!(detail.report, after);
      return history.status === 'AVAILABLE' ? {status: 'AVAILABLE', library, detail: detail.report, history: history.report} : empty(history.status);
    }, quiet);
  }
  function libraryPage(direction: 'previous' | 'next') {
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
    const library = view.library;
    if (!library) return;
    void run(async () => {
      const result = await client.readLibraryEntry!(library, entry);
      if (result.status !== 'AVAILABLE') return empty(result.status);
      const detail = result.report;
      if (!detail.profile) return {status: 'AVAILABLE', library, detail, history: null};
      const history = await client.readLibraryHistory!(detail);
      return history.status === 'AVAILABLE' ? {status: 'AVAILABLE', library, detail, history: history.report} : empty(history.status);
    });
  }
  function historyPage(direction: 'previous' | 'next') {
    const {library, detail, history} = view;
    if (!library || !detail || !history) return;
    const after = direction === 'previous' ? history.after - 50 : history.nextAfter;
    if (after === null || after < 0) return;
    void run(async () => {
      const result = await client.readLibraryHistory!(detail, after);
      return result.status === 'AVAILABLE' ? {status: 'AVAILABLE', library, detail, history: result.report} : empty(result.status);
    });
  }
  useEffect(() => { refreshRef.current = () => refreshLibrary(true); });
  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    const first = window.setTimeout(() => refreshRef.current(), 0);
    const timer = window.setInterval(() => refreshRef.current(), intervalMs);
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [enabled, intervalMs]);
  return {view, refreshLibrary: () => refreshLibrary(intervalMs > 0), browseEntry, libraryPage, historyPage, autoRefresh: intervalMs > 0};
}
