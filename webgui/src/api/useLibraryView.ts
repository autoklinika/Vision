import { useEffect, useRef, useState } from 'react';
import type { ReadOnlyVisionClient } from './types';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from './libraryContract';

export type LibraryView = Readonly<{
  status: 'NOT_REQUESTED' | 'LOADING' | 'AVAILABLE' | 'ACCESS_DENIED' | 'UNAVAILABLE' | 'DISABLED';
  library: LibraryReport | null; detail: LibraryDetail | null; history: LibraryHistory | null;
}>;
export type LibraryControls = Readonly<{
  view: LibraryView; refreshLibrary: () => void; browseEntry: (entry: LibraryEntry) => void;
  libraryPage: (direction: 'previous' | 'next') => void; historyPage: (direction: 'previous' | 'next') => void;
}>;
const empty = (status: LibraryView['status']): LibraryView => ({status, library: null, detail: null, history: null});

/** Ephemeral presentation only: one list page and one detail/history page. */
export function useLibraryView(client: ReadOnlyVisionClient): LibraryControls {
  const enabled = client.mode === 'real' && !!client.readLibrary && !!client.readLibraryEntry && !!client.readLibraryHistory;
  const [view, setView] = useState<LibraryView>(() => empty(enabled ? 'NOT_REQUESTED' : 'DISABLED'));
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);

  async function run(read: () => Promise<LibraryView>) {
    if (!enabled || busy.current) return;
    busy.current = true;
    const current = ++generation.current;
    setView(empty('LOADING'));
    try {
      const result = await read();
      if (current === generation.current) setView(result);
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally { busy.current = false; }
  }
  function refreshLibrary() {
    void run(async () => {
      const result = await client.readLibrary!();
      return result.status === 'AVAILABLE' ? {status: 'AVAILABLE', library: result.report, detail: null, history: null} : empty(result.status);
    });
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
  return {view, refreshLibrary, browseEntry, libraryPage, historyPage};
}
