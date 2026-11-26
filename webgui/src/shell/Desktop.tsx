import { useTranslation } from '../i18n/LanguageProvider';
import { Button, Tab, TabList } from '@fluentui/react-components';
import { DismissRegular } from '@fluentui/react-icons';
import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { ReadOnlyVisionClient, Snapshot } from '../api/types';
import { AppContent } from '../apps/AppContent';
import { StationNavigation } from './StationNavigation';
import { useSessionView } from '../api/useSessionView';
import { useLibraryView } from '../api/useLibraryView';
import type { StationPresentation } from '../station/client';
import { modeLabel, modeDescription, connectionLabel } from '../api/presentation';
import { apps, clamp, decodeLayout, encodeLayout, reduce, storageKey } from './model';
import type { Action, AppId, Bounds, Rect, WindowState } from './model';
function bounds(stationMode = false): Bounds { return { width: Math.max(1, window.innerWidth), height: Math.max(1, window.innerHeight - (stationMode ? 78 : 72)) }; }
export function Icon({ id, small = false }: { id: AppId; small?: boolean }) {
  const index = apps.findIndex(a => a.id === id);
  // Original geometric SVG artwork; no imported OS icons or branding.
  return <svg className={small ? 'app-icon small' : 'app-icon'} viewBox="0 0 32 32" aria-hidden="true" shapeRendering="crispEdges"><path d="M3 5h23v3h3v21H3z" fill="#000"/><path d="M4 6h21v3h3v19H4z" fill="#fff"/><path d="M6 9h19v16H6z" fill={['#008080','#b59c42','#487a48','#367ca5','#756198','#a65d5d','#488b8b','#777','#b38b45','#6a7484'][index]}/><path d="M6 9h19v3H6z" fill="#000080"/><text x="16" y="23" textAnchor="middle" fontSize="15" fill="white">{apps[index].glyph}</text><path d="M2 29h27v2H2z" fill="#004747"/></svg>;
}
export function Desktop({ client, snapshot, refresh, station, stationAvailable = true }: { client: ReadOnlyVisionClient; snapshot: Snapshot | null; refresh: () => void; station?: StationPresentation; stationAvailable?: boolean }) {
  const {t}=useTranslation();
  const projectionOwner = station ? [station.report.instanceId, station.report.coreConnection,
    station.report.state, station.report.sessionId, station.report.sessionViewId].join(':') : '';
  const sessionRead = useSessionView(client, station?.report.state === 'SESSION_ACTIVE' ? 5000 : 0, projectionOwner);
  const sessionControls = station?.report.coreConnection === 'NOT_CONNECTED'
    ? {...sessionRead, refreshSession: station.refresh, view: {status: 'UNAVAILABLE' as const, session: null, events: null}}
    : station?.report.state === 'NO_ACTIVE_SESSION' ? {...sessionRead, view: {status: 'NO_ACTIVE_SESSION' as const, session: null, events: null}} : sessionRead;
  const libraryRead = useLibraryView(client, station ? 15000 : 0, projectionOwner);
  const libraryControls = station?.report.coreConnection === 'NOT_CONNECTED'
    ? {...libraryRead, view: {status: 'UNAVAILABLE' as const, library: null, detail: null, history: null}} : libraryRead;
  const mode = station ? t('CONNECTED · VENTUNO') : modeLabel(client.mode, snapshot);
  const connection = station ? t('Connected') : connectionLabel(snapshot);
  const description = station ? `${station.identity.username} · ${t(station.report.coreConnection === 'CONNECTED' ? 'Core connected' : 'Core not connected')} · ${t(station.identity.role==='operator'?'Operator':'Read only')}` : modeDescription(client.mode, snapshot);
  const stationMode = !!station;
  const [size, setSize] = useState(() => bounds(stationMode));
  const layoutKey = stationMode ? 'vision.fluent.workspace.v1' : storageKey;
  const [state, setState] = useState(() => { try { return decodeLayout(localStorage.getItem(layoutKey), bounds(stationMode)); } catch { return decodeLayout(null, bounds(stationMode)); } });
  const [persistence, setPersistence] = useState('Layout preferences are local to this browser.');
  const [start, setStart] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const windowsRef = useRef(new Map<AppId, HTMLElement>());
  const gesture = useRef<{ id: AppId; kind: 'move' | 'resize'; x: number; y: number; rect: Rect } | null>(null);
  const dispatch = (action: Action) => setState(s => reduce(s, action, bounds(stationMode)));
  useEffect(() => { const update = () => { setSize(bounds(stationMode)); setState(s => reduce(s, { type: 'bounds' }, bounds(stationMode))); }; window.addEventListener('resize', update); return () => window.removeEventListener('resize', update); }, [stationMode]);
  useEffect(() => { try { localStorage.setItem(layoutKey, encodeLayout(state)); } catch { /* Browser storage is optional; the desktop remains usable. */ } }, [state, layoutKey]);
  useEffect(() => {
    if (state.active) {
      const target = windowsRef.current.get(state.active);
      // Switching via the tab strip must leave keyboard focus on the tab.
      const tabFocused = stationMode && document.activeElement?.closest('.vision-workspace-tabs');
      if (!tabFocused && !target?.contains(document.activeElement)) target?.focus({ preventScroll: true });
    }
  }, [state.active, stationMode]);
  useEffect(() => {
    if (!stationMode || !state.active) return;
    const tab = document.getElementById('tab-'+state.active);
    const strip = tab?.closest('.vision-workspace-tabs');
    if (!tab || !strip) return;
    const item = tab.parentElement!.getBoundingClientRect();
    const visible = strip.getBoundingClientRect();
    if (item.left < visible.left) strip.scrollLeft += item.left-visible.left;
    else if (item.right > visible.right) strip.scrollLeft += item.right-visible.right;
  }, [state.active, stationMode]);
  useEffect(() => {
    if (!start) return;
    menuRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const dismiss = (event: PointerEvent) => { if (!menuRef.current?.contains(event.target as Node) && !startRef.current?.contains(event.target as Node)) setStart(false); };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [start]);
  function launch(id: AppId) { dispatch({ type: 'open', id }); setStart(false); requestAnimationFrame(() => windowsRef.current.get(id)?.focus()); }
  function begin(event: ReactPointerEvent, win: WindowState, kind: 'move' | 'resize') {
    if (event.button !== 0 || win.maximized || (event.target as HTMLElement).closest('button')) return;
    dispatch({ type: 'focus', id: win.id });
    gesture.current = { id: win.id, kind, x: event.clientX, y: event.clientY, rect: win.rect };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: ReactPointerEvent) {
    const g = gesture.current;
    if (!g) return;
    const dx = event.clientX - g.x, dy = event.clientY - g.y;
    dispatch({ type: 'rect', id: g.id, rect: g.kind === 'move' ? { ...g.rect, x: g.rect.x + dx, y: g.rect.y + dy } : { ...g.rect, width: g.rect.width + dx, height: g.rect.height + dy } });
  }
  function keyboard(event: ReactKeyboardEvent, win: WindowState, kind: 'move' | 'resize') {
    if (event.target !== event.currentTarget || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault(); const step = event.shiftKey ? 32 : 8;
    const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
    const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
    dispatch({ type: 'rect', id: win.id, rect: kind === 'move' ? { ...win.rect, x: win.rect.x + dx, y: win.rect.y + dy } : { ...win.rect, width: win.rect.width + dx, height: win.rect.height + dy } });
  }
  function allowEditorExit(id?:AppId) {
    const root=id?windowsRef.current.get(id):document;
    if(root?.querySelector('[data-editor-busy="true"]')) {
      window.alert(t('A Core editor request is pending. Wait for its outcome before closing the editor.'));
      return false;
    }
    return !root?.querySelector('[data-editor-dirty="true"]')||window.confirm(t('Discard unsaved ECU draft changes?'));
  }
  function closeStationTab(id: AppId) {
    if(!allowEditorExit(id)) return;
    const next=reduce(state,{type:'close',id},bounds(true));
    // The close button is a sibling of its tab, so closing an inactive
    // module never activates it. Restore focus after the removal.
    dispatch({type:'close',id});
    requestAnimationFrame(() => {
      const target=next.active?document.getElementById('tab-'+next.active):document.getElementById('vision-open-navigation');
      target?.focus({preventScroll:true});
    });
  }
  function reset() {
    if(!allowEditorExit())return;
    try { localStorage.removeItem(layoutKey); setPersistence('Layout reset. Only desktop preferences were affected.'); } catch { setPersistence('Browser storage unavailable. Layout reset for this tab.'); }
    dispatch({ type: 'reset' });
  }
  if (station) {
    const openModules = apps.filter(app => state.windows.some(win => win.id === app.id));
    return <main className="desktop station-fluent-shell vision-workspace">
      <StationNavigation available={stationAvailable} active={state.active} onNavigate={launch} accountBusy={station.accountBusy} onSignOut={() => { if (allowEditorExit()) station.logout(); }} tabs={
        <TabList className="vision-workspace-tabs" aria-label={t("Open modules")} selectedValue={state.active ?? undefined} onTabSelect={(_, data) => dispatch({type:'focus',id:data.value as AppId})}>
          {openModules.map(app => <div key={app.id} role="presentation" className="vision-tab-item">
            <Tab value={app.id} id={'tab-'+app.id} aria-controls={'panel-'+app.id} aria-keyshortcuts="Delete" onKeyDown={event => { if (event.key==='Delete') { event.preventDefault(); closeStationTab(app.id); } }}>{t(app.title)}</Tab>
            <Button className="vision-tab-close" appearance="subtle" size="small" icon={<DismissRegular/>} tabIndex={-1} aria-label={t('Close {module}',{module:t(app.title)})} title={t('Close {module}',{module:t(app.title)})} onClick={() => closeStationTab(app.id)}/>
          </div>)}
        </TabList>
      }/>
      <div className="vision-workspace-body">
        {state.windows.map(win => {
          const app = apps.find(a => a.id === win.id)!;
          return <section id={'panel-'+win.id} role="tabpanel" aria-labelledby={'tab-'+win.id} data-module={win.id} key={win.id} hidden={state.active!==win.id} tabIndex={0} ref={node => { if(node)windowsRef.current.set(win.id,node);else windowsRef.current.delete(win.id); }} className="vision-module">
            <div className="vision-module-title"><h1>{t(app.title)}</h1><span>{t(app.description)}</span></div>
            <AppContent id={win.id} snapshot={snapshot} reset={reset} persistence={t(persistence)} refresh={client.canRefresh ? refresh : undefined} sessionControls={sessionControls} libraryControls={libraryControls} station={station} onNavigate={launch}/>
          </section>;
        })}
        {!state.active && <div className="vision-workspace-empty"><h1>{t("Vision workspace")}</h1><p>{t("Choose a module from Navigation.")}</p><Button appearance="primary" onClick={()=>launch('status')}>{t("Open System Status")}</Button></div>}
      </div>
      <footer className="vision-workspace-status"><span>{description}</span><span>{t('Vision client · {connection}',{connection})}</span></footer>
    </main>;
  }
  return <main className="desktop" onKeyDown={e => { if (e.key === 'Escape' && start) { setStart(false); startRef.current?.focus(); } }}>
    <header className="mode-banner"><strong>{mode}</strong><span>{description}</span><span className="shell-version">VISION / API-03</span></header>
    <div className="workspace" style={{ height: size.height }}>
      {!station && <nav className="desktop-icons" aria-label="Desktop applications">{apps.map(app => <button className="desktop-shortcut" key={app.id} onClick={() => launch(app.id)} title={app.description}><Icon id={app.id}/><span>{app.title}</span></button>)}</nav>}
      <div className="desktop-watermark" aria-hidden="true"><strong>VISION</strong><span>DESKTOP SHELL / V1</span><small>Client of the Vision system</small></div>
      {state.windows.map((win, z) => {
        const app = apps.find(a => a.id === win.id)!;
        const rect = win.maximized ? { x: 0, y: 0, ...size } : clamp(win.rect, size);
        return <section role="dialog" aria-modal="false" aria-labelledby={`title-${win.id}`} tabIndex={-1} ref={node => { if (node) windowsRef.current.set(win.id, node); else windowsRef.current.delete(win.id); }} className={`window app-window ${state.active === win.id ? 'active' : ''}`} key={win.id} hidden={win.minimized} style={{ left: rect.x, top: rect.y, width: rect.width, height: rect.height, zIndex: z + 1 }} onPointerDown={() => { if (state.active !== win.id) dispatch({ type: 'focus', id: win.id }); }} onFocus={() => { if (state.active !== win.id) dispatch({ type: 'focus', id: win.id }); }}>
          <div className={`title-bar ${state.active !== win.id ? 'inactive' : ''}`} tabIndex={0} aria-label={`Move ${app.title} with arrow keys`} onKeyDown={e => keyboard(e, win, 'move')} onPointerDown={e => begin(e, win, 'move')} onPointerMove={move} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }} onDoubleClick={e => { if (!(e.target as HTMLElement).closest('button')) dispatch({ type: 'maximize', id: win.id }); }}>
            <div className="title-bar-text" id={`title-${win.id}`}><Icon id={win.id} small/>{app.title}</div><div className="title-bar-controls"><button aria-label={`Minimize ${app.title}`} onClick={() => dispatch({ type: 'minimize', id: win.id })}/><button aria-label={`${win.maximized ? 'Restore' : 'Maximize'} ${app.title}`} className={win.maximized ? 'restore-button' : 'maximize-button'} onClick={() => dispatch({ type: 'maximize', id: win.id })}/><button aria-label={`Close ${app.title}`} onClick={() => {if(allowEditorExit(win.id))dispatch({type:'close',id:win.id});}}/></div>
          </div>
          <div className="window-menubar"><span>Vision client</span><span>{mode}</span><span>{win.id === 'settings' ? 'Account settings' : t("Read only")}</span></div>
          <div className="window-body"><AppContent id={win.id} snapshot={snapshot} reset={reset} persistence={t(persistence)} refresh={client.canRefresh ? refresh : undefined} sessionControls={sessionControls} libraryControls={libraryControls} station={station}/></div>
          <footer className="status-bar"><p className="status-bar-field">{win.id === 'control' ? 'Local UI preferences' : win.id === 'settings' ? 'Your account security' : 'No operational commands'}</p><p className="status-bar-field">{connection}</p>{!win.maximized && <button className="resize-handle" aria-label={`Resize ${app.title} with arrow keys`} onKeyDown={e => keyboard(e, win, 'resize')} onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); gesture.current = { id: win.id, kind: 'resize', x: e.clientX, y: e.clientY, rect: win.rect }; }} onPointerMove={move} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }}>◢</button>}</footer>
        </section>;
      })}
    </div>
    {!station && start && <div className="start-menu window" ref={menuRef} role="menu" aria-label="Start applications" onKeyDown={e => { const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')); const i = items.indexOf(document.activeElement as HTMLButtonElement); if (['ArrowDown','ArrowUp','Home','End'].includes(e.key)) { e.preventDefault(); items[e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus(); } }}><div className="start-brand">VISION <b>Desktop</b></div><div className="start-items">{apps.map(app => <button role="menuitem" key={app.id} onClick={() => launch(app.id)}><Icon id={app.id} small/>{app.title}</button>)}<hr/><button role="menuitem" disabled>Log in… · unavailable</button><button role="menuitem" disabled>Restart system… · unavailable</button><button role="menuitem" disabled>Shut down system… · unavailable</button></div></div>}
    <footer className="taskbar">{!station && <button className={`start-button ${start ? 'pressed' : ''}`} ref={startRef} aria-expanded={start} aria-haspopup="menu" onClick={() => setStart(!start)}><span className="start-symbol" aria-hidden="true">V</span>Start</button>}{!station && <span className="taskbar-divider"/>}<div className="task-buttons">{state.windows.map(win => <button key={win.id} className={state.active === win.id && !win.minimized ? 'pressed' : ''} aria-pressed={state.active === win.id && !win.minimized} onClick={() => dispatch({ type: state.active === win.id && !win.minimized ? 'minimize' : 'focus', id: win.id })}><Icon id={win.id} small/><span>{apps.find(a => a.id === win.id)!.title}</span></button>)}</div><div className="tray" role="status">{connection}<span>Client only</span></div></footer>
  </main>;
}
