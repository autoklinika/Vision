import { useEffect, useRef, useState } from 'react';
import type { ReadOnlyVisionClient } from './types';
import type { EventsReport, SessionReport } from './sessionContract';

export type SessionView = Readonly<{
  status: 'NOT_REQUESTED' | 'LOADING' | 'AVAILABLE' | 'ACCESS_DENIED' | 'UNAVAILABLE' | 'DISABLED';
  session: SessionReport | null; events: EventsReport | null;
}>;
export type SessionControls = Readonly<{
  view: SessionView; refreshSession: () => void; nextEvents: () => void;
}>;
const empty = (status: SessionView['status']): SessionView => ({status, session: null, events: null});

/** In-memory presentation cache only. No persistence, polling, commands, or gate decisions. */
export function useSessionView(client: ReadOnlyVisionClient): SessionControls {
  const enabled = client.mode === 'real' && !!client.readSession && !!client.readEvents;
  const [view, setView] = useState<SessionView>(() => empty(enabled ? 'NOT_REQUESTED' : 'DISABLED'));
  const busy = useRef(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);

  async function refreshSession() {
    if (!enabled || busy.current || !client.readSession || !client.readEvents) return;
    busy.current = true;
    const current = ++generation.current;
    setView(empty('LOADING'));
    try {
      const session = await client.readSession();
      if (current !== generation.current) return;
      if (session.status !== 'AVAILABLE') { setView(empty(session.status)); return; }
      const events = await client.readEvents(session.report, 0);
      if (current !== generation.current) return;
      if (events.status !== 'AVAILABLE') { setView(empty(events.status)); return; }
      setView({status: 'AVAILABLE', session: session.report, events: events.report});
    } catch {
      if (current === generation.current) setView(empty('UNAVAILABLE'));
    } finally {
      busy.current = false;
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
      busy.current = false;
    }
  }
  return {view, refreshSession, nextEvents};
}
