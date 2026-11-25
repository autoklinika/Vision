import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReadOnlyVisionClient } from './types';
import type { EventsReport, SessionReport } from './sessionContract';

export type SessionView = Readonly<{
  status: 'NOT_REQUESTED' | 'LOADING' | 'AVAILABLE' | 'ACCESS_DENIED' | 'UNAVAILABLE' | 'DISABLED' | 'NO_ACTIVE_SESSION';
  session: SessionReport | null; events: EventsReport | null;
  refreshing?: boolean;
}>;
export type SessionControls = Readonly<{
  view: SessionView; refreshSession: () => void; nextEvents: () => void;
  autoRefresh?: boolean;
}>;
const empty = (status: SessionView['status']): SessionView => ({status, session: null, events: null});

/** In-memory presentation only. Station composition can opt into bounded polling. */
export function useSessionView(client: ReadOnlyVisionClient, intervalMs = 0, owner = ''): SessionControls {
  const enabled = client.mode === 'real' && !!client.readSession && !!client.readEvents;
  // A -> disconnected -> A is a new observation, even with the same IDs.
  const ownerToken = useMemo(() => Symbol(owner), [owner]);
  const [ownedView, setOwnedView] = useState(() => ({owner: ownerToken, view: empty(enabled ? 'NOT_REQUESTED' : 'DISABLED')}));
  // Mask the old owner synchronously, before effects and late requests settle.
  const view = ownedView.owner === ownerToken ? ownedView.view : empty(enabled ? 'NOT_REQUESTED' : 'DISABLED');
  const setView = (next: SessionView) => setOwnedView({owner: ownerToken, view: next});
  const busy = useRef(false);
  const generation = useRef(0);
  const refreshRef = useRef<(quiet: boolean) => Promise<void>>(async () => {});
  useEffect(() => () => { generation.current++; busy.current = false; }, [ownerToken, enabled]);

  async function refresh(quiet = false) {
    if (!enabled || busy.current || !client.readSession || !client.readEvents) return;
    busy.current = true;
    const current = ++generation.current;
    setView(quiet && view.session ? {...view, refreshing: true} : empty('LOADING'));
    try {
      const session = await client.readSession();
      if (current !== generation.current) return;
      if (session.status !== 'AVAILABLE') { setView(empty(session.status)); return; }
      const after = quiet && view.events && view.events.afterSequence <= session.report.journalSequence ? view.events.afterSequence : 0;
      const events = await client.readEvents(session.report, after);
      if (current !== generation.current) return;
      if (events.status !== 'AVAILABLE') { setView(empty(events.status)); return; }
      setView({status: 'AVAILABLE', session: session.report, events: events.report});
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally {
      if (current === generation.current) busy.current = false;
    }
  }

  async function nextEvents() {
    if (!enabled || busy.current || !client.readEvents || !view.session || !view.events || view.events.nextAfterSequence === null) return;
    const session = view.session;
    const after = view.events.nextAfterSequence;
    busy.current = true;
    const current = ++generation.current;
    setView(empty('LOADING'));
    try {
      const events = await client.readEvents(session, after);
      if (current !== generation.current) return;
      if (events.status !== 'AVAILABLE') { setView(empty(events.status)); return; }
      setView({status: 'AVAILABLE', session, events: events.report});
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally {
      if (current === generation.current) busy.current = false;
    }
  }
  useEffect(() => { refreshRef.current = refresh; });
  useEffect(() => {
    if (!enabled || intervalMs <= 0) return;
    const first = window.setTimeout(() => { void refreshRef.current(true); }, 0);
    const timer = window.setInterval(() => { void refreshRef.current(true); }, intervalMs);
    return () => { window.clearTimeout(first); window.clearInterval(timer); };
  }, [enabled, intervalMs, ownerToken]);
  return {view, refreshSession: () => { void refresh(); }, nextEvents, autoRefresh: intervalMs > 0};
}
