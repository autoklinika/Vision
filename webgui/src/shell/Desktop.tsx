import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { ReadOnlyVisionClient, Snapshot } from '../api/types';
import { AppContent } from '../apps/AppContent';
import { useSessionView } from '../api/useSessionView';
import { useLibraryView } from '../api/useLibraryView';
import type { StationPresentation } from '../station/client';
import { modeLabel, modeDescription, connectionLabel } from '../api/presentation';
import { apps, navigationGroups, readActiveApp, encodeActiveApp, storageKey } from './model';
import type { AppId } from './model';

const iconShapes: Record<AppId, ReactNode> = {
  status: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  ecu: <><rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/><rect x="9" y="9" width="6" height="6" rx="1"/></>,
  inspection: <><path d="M9 4H6a2 2 0 0 0-2 2v14h16V6a2 2 0 0 0-2-2h-3"/><rect x="9" y="2" width="6" height="4" rx="1"/><path d="m8 13 3 3 5-6"/></>,
  images: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 18 5-5 4 4 5-7 4 5"/></>,
  events: <><path d="M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01"/></>,
  luxonis: <><path d="M3 7h4l2-3h6l2 3h4v13H3z"/><circle cx="12" cy="13" r="4"/></>,
  nero: <><path d="M4 21h16M8 21v-5l5-4-3-6M13 12l5 3 3-3M6 3l4 3 4-3"/><circle cx="10" cy="6" r="2"/><circle cx="13" cy="12" r="2"/></>,
  sony: <><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M7 6V3h5v3"/><circle cx="13" cy="13" r="4"/></>,
  control: <><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="16" cy="17" r="3" fill="currentColor" stroke="none"/></>,
  settings: <><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
};

export function Icon({id, small = false}: {id: AppId; small?: boolean}) {
  return <svg className={small ? 'app-icon small' : 'app-icon'} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconShapes[id]}</svg>;
}

function initialApp(): AppId {
  try { return readActiveApp(localStorage.getItem(storageKey)); } catch { return 'status'; }
}

export function Desktop({client, snapshot, refresh, station, interactive = true}: {client: ReadOnlyVisionClient; snapshot: Snapshot | null; refresh: () => void; station?: StationPresentation; interactive?: boolean}) {
  const projectionOwner = station ? [station.report.instanceId, station.report.coreConnection,
    station.report.state, station.report.sessionId, station.report.sessionViewId].join(':') : '';
  const sessionRead = useSessionView(client, station?.report.state === 'SESSION_ACTIVE' ? 5000 : 0, projectionOwner);
  const sessionControls = station?.report.coreConnection === 'NOT_CONNECTED'
    ? {...sessionRead, refreshSession: station.refresh, view: {status: 'UNAVAILABLE' as const, session: null, events: null}}
    : station?.report.state === 'NO_ACTIVE_SESSION' ? {...sessionRead, view: {status: 'NO_ACTIVE_SESSION' as const, session: null, events: null}} : sessionRead;
  const libraryRead = useLibraryView(client, station ? 15000 : 0, projectionOwner);
  const libraryControls = station?.report.coreConnection === 'NOT_CONNECTED'
    ? {...libraryRead, view: {status: 'UNAVAILABLE' as const, library: null, detail: null, history: null}} : libraryRead;

  const [activeApp, setActiveApp] = useState<AppId>(initialApp);
  const [visited, setVisited] = useState<AppId[]>(() => [activeApp]);
  const [persistence, setPersistence] = useState('Only the last open section is remembered in this browser.');
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 900px)').matches);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const active = apps.find(app => app.id === activeApp)!;

  useEffect(() => {
    try { localStorage.setItem(storageKey, encodeActiveApp(activeApp)); } catch { /* Navigation works without browser storage. */ }
  }, [activeApp]);

  useEffect(() => {
    const query = window.matchMedia('(max-width: 900px)');
    const changed = (event: MediaQueryListEvent) => {
      setMobile(event.matches);
      if (!event.matches) setNavigationOpen(false);
    };
    query.addEventListener('change', changed);
    return () => query.removeEventListener('change', changed);
  }, []);

  useLayoutEffect(() => {
    if (!interactive || !mobile || !navigationOpen) return;
    const frame = requestAnimationFrame(() => sidebarRef.current?.querySelector<HTMLButtonElement>('[aria-current="page"]')?.focus());
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setNavigationOpen(false);
        menuButtonRef.current?.focus();
      } else if (event.key === 'Tab') {
        const controls = Array.from(sidebarRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
        const first = controls[0], last = controls.at(-1);
        if (!first || !last) return;
        if (event.shiftKey && (document.activeElement === first || !sidebarRef.current?.contains(document.activeElement))) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !sidebarRef.current?.contains(document.activeElement))) {
          event.preventDefault(); first.focus();
        }
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => { cancelAnimationFrame(frame); document.removeEventListener('keydown', handleKey); };
  }, [interactive, mobile, navigationOpen]);

  function focusWorkspace() {
    requestAnimationFrame(() => {
      headingRef.current?.focus({preventScroll: true});
      mainRef.current?.scrollTo({top: 0});
      window.scrollTo({top: 0});
    });
  }

  function openApp(id: AppId) {
    setVisited(previous => previous.includes(id) ? previous : [...previous, id]);
    setActiveApp(id);
    setNavigationOpen(false);
    focusWorkspace();
  }

  function closeNavigation() {
    setNavigationOpen(false);
    menuButtonRef.current?.focus();
  }

  function allowEditorExit() {
    if (shellRef.current?.querySelector('[data-editor-busy="true"]')) {
      window.alert('A Core editor request is pending. Wait for its outcome before closing the editor.');
      return false;
    }
    return !shellRef.current?.querySelector('[data-editor-dirty="true"]') || window.confirm('Discard unsaved ECU draft changes?');
  }

  function reset() {
    if (!allowEditorExit()) return;
    try {
      localStorage.removeItem(storageKey);
      setPersistence('Workspace reset. Your station data is unchanged.');
    } catch {
      setPersistence('Browser storage unavailable. Workspace reset for this tab.');
    }
    setVisited(['status']);
    setActiveApp('status');
    setNavigationOpen(false);
    focusWorkspace();
  }

  const coreConnected = station?.report.coreConnection === 'CONNECTED';
  const connection = station ? (coreConnected ? 'Core connected' : 'Core not connected') : connectionLabel(snapshot);
  const connectionState = station ? (coreConnected ? 'connected' : 'disconnected') : snapshot?.connection === 'API_AVAILABLE' ? 'connected' : 'preview';
  const sessionLabel = station ? (!coreConnected ? 'Session status unavailable' : station.report.state === 'SESSION_ACTIVE' ? 'Session active' : 'No active session') : modeLabel(client.mode, snapshot);

  return <div className="app-shell" ref={shellRef} inert={!interactive}>
    <a className="skip-link" href="#workspace-main">Skip to content</a>
    <header className="app-header">
      <button className="app-menu-toggle button-quiet" ref={menuButtonRef} aria-label={navigationOpen ? 'Close navigation' : 'Open navigation'} aria-controls="workspace-navigation" aria-expanded={navigationOpen} onClick={() => navigationOpen ? closeNavigation() : setNavigationOpen(true)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
      </button>
      <div className="app-brand"><span className="app-brand-mark" aria-hidden="true">V</span><div><strong>VISION</strong><span>{station ? 'Workstation' : 'Lab preview'}</span></div></div>
      <div className="app-header-status" title={station ? undefined : modeDescription(client.mode, snapshot)}>
        <span className="connection-badge" data-state={connectionState}>{connection}</span>
        <span className="app-session-state">{sessionLabel}</span>
      </div>
      {station && <div className="app-header-actions">
        <span className="app-identity"><strong>{station.identity.username}</strong><span>{station.identity.role === 'operator' ? 'Operator' : 'Read only'}</span></span>
        <button className="button-quiet" disabled={station.accountBusy} onClick={() => { if (allowEditorExit()) station.logout(); }}>Sign out</button>
      </div>}
    </header>
    <div className="app-body">
      {mobile && navigationOpen && <button className="nav-backdrop" aria-label="Close navigation overlay" tabIndex={-1} onClick={closeNavigation}/>}
      <aside id="workspace-navigation" ref={sidebarRef} className={navigationOpen ? 'app-sidebar is-open' : 'app-sidebar'} role={mobile ? 'dialog' : undefined} aria-modal={mobile && navigationOpen ? true : undefined} aria-label="Workspace navigation" aria-hidden={mobile && !navigationOpen ? true : undefined} inert={mobile && !navigationOpen}>
        <div className="app-sidebar-heading"><span>Navigation</span><button className="app-nav-close button-quiet" aria-label="Close menu" onClick={closeNavigation}>×</button></div>
        <nav aria-label="Main navigation">
          {navigationGroups.map(group => <div className="app-nav-group" key={group.id}>
            <h2 className="app-nav-group-label">{group.title}</h2>
            {apps.filter(app => app.group === group.id).map(app => <button key={app.id} className="app-nav-item" aria-current={activeApp === app.id ? 'page' : undefined} onClick={() => openApp(app.id)}><Icon id={app.id}/><span>{app.title}</span></button>)}
          </div>)}
        </nav>
        {station && <div className="app-account"><strong>{station.identity.username}</strong><small>{station.identity.role === 'operator' ? 'Operator' : 'Read only'}</small></div>}
      </aside>
      <main id="workspace-main" className="app-main" ref={mainRef} tabIndex={-1} inert={mobile && navigationOpen}>
        <div className="workspace-heading"><h1 ref={headingRef} tabIndex={-1}>{active.title}</h1><p>{active.description}</p></div>
        {visited.map(id => {
          // Keep a working reference in memory while navigating. Password fields
          // deliberately unmount on departure; pending auth stays with its owner.
          if (id === 'settings' && id !== activeApp) return null;
          const app = apps.find(item => item.id === id)!;
          return <section key={id} className="workspace-panel" role="region" aria-label={app.title} data-app-id={id} hidden={id !== activeApp}>
            <AppContent id={id} snapshot={snapshot} reset={reset} persistence={persistence} refresh={client.canRefresh ? refresh : undefined} sessionControls={sessionControls} libraryControls={libraryControls} station={station}/>
          </section>;
        })}
      </main>
    </div>
  </div>;
}
