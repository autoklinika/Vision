import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { ReadOnlyVisionClient, Snapshot } from '../api/types';
import { AppContent } from '../apps/AppContent';
import { useSessionView } from '../api/useSessionView';
import { useLibraryView } from '../api/useLibraryView';
import { modeLabel, modeDescription, connectionLabel } from '../api/presentation';
import { apps, clamp, decodeLayout, encodeLayout, reduce, storageKey } from './model';
import type { Action, AppId, Bounds, Rect, WindowState } from './model';
function bounds(): Bounds { return { width: Math.max(1, window.innerWidth), height: Math.max(1, window.innerHeight - 72) }; }
export function Icon({ id, small = false }: { id: AppId; small?: boolean }) {
  const index = apps.findIndex(a => a.id === id);
  // Original geometric SVG artwork; no imported OS icons or branding.
  return <svg className={small ? 'app-icon small' : 'app-icon'} viewBox="0 0 32 32" aria-hidden="true" shapeRendering="crispEdges"><path d="M3 5h23v3h3v21H3z" fill="#000"/><path d="M4 6h21v3h3v19H4z" fill="#fff"/><path d="M6 9h19v16H6z" fill={['#008080','#b59c42','#487a48','#367ca5','#756198','#a65d5d','#488b8b','#777','#b38b45'][index]}/><path d="M6 9h19v3H6z" fill="#000080"/><text x="16" y="23" textAnchor="middle" fontSize="15" fill="white">{apps[index].glyph}</text><path d="M2 29h27v2H2z" fill="#004747"/></svg>;
}
export function Desktop({ client, snapshot, refresh }: { client: ReadOnlyVisionClient; snapshot: Snapshot | null; refresh: () => void }) {
  const sessionControls = useSessionView(client);
  const libraryControls = useLibraryView(client);
  const [size, setSize] = useState(bounds);
  const [state, setState] = useState(() => { try { return decodeLayout(localStorage.getItem(storageKey), bounds()); } catch { return decodeLayout(null, bounds()); } });
  const [persistence, setPersistence] = useState('Layout preferences are local to this browser.');
  const [start, setStart] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const windowsRef = useRef(new Map<AppId, HTMLElement>());
  const gesture = useRef<{ id: AppId; kind: 'move' | 'resize'; x: number; y: number; rect: Rect } | null>(null);
  const dispatch = (action: Action) => setState(s => reduce(s, action, bounds()));
  useEffect(() => { const update = () => { setSize(bounds()); setState(s => reduce(s, { type: 'bounds' }, bounds())); }; window.addEventListener('resize', update); return () => window.removeEventListener('resize', update); }, []);
  useEffect(() => { try { localStorage.setItem(storageKey, encodeLayout(state)); } catch { /* Browser storage is optional; the desktop remains usable. */ } }, [state]);
  useEffect(() => {
    if (state.active) {
      const target = windowsRef.current.get(state.active);
      if (!target?.contains(document.activeElement)) target?.focus({ preventScroll: true });
    }
  }, [state.active]);
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
  function reset() {
    try { localStorage.removeItem(storageKey); setPersistence('Layout reset. Only desktop preferences were affected.'); } catch { setPersistence('Browser storage unavailable. Layout reset for this tab.'); }
    dispatch({ type: 'reset' });
  }
  return <main className="desktop" onKeyDown={e => { if (e.key === 'Escape' && start) { setStart(false); startRef.current?.focus(); } }}>
    <header className="mode-banner"><strong>{modeLabel(client.mode, snapshot)}</strong><span>{modeDescription(client.mode, snapshot)}</span><span className="shell-version">VISION / API-03</span></header>
    <div className="workspace" style={{ height: size.height }}>
      <nav className="desktop-icons" aria-label="Desktop applications">{apps.map(app => <button className="desktop-shortcut" key={app.id} onClick={() => launch(app.id)} title={app.description}><Icon id={app.id}/><span>{app.title}</span></button>)}</nav>
      <div className="desktop-watermark" aria-hidden="true"><strong>VISION</strong><span>DESKTOP SHELL / V1</span><small>Client of the Vision system</small></div>
      {state.windows.map((win, z) => {
        const app = apps.find(a => a.id === win.id)!;
        const rect = win.maximized ? { x: 0, y: 0, ...size } : clamp(win.rect, size);
        return <section role="dialog" aria-modal="false" aria-labelledby={`title-${win.id}`} tabIndex={-1} ref={node => { if (node) windowsRef.current.set(win.id, node); else windowsRef.current.delete(win.id); }} className={`window app-window ${state.active === win.id ? 'active' : ''}`} key={win.id} hidden={win.minimized} style={{ left: rect.x, top: rect.y, width: rect.width, height: rect.height, zIndex: z + 1 }} onPointerDown={() => { if (state.active !== win.id) dispatch({ type: 'focus', id: win.id }); }} onFocus={() => { if (state.active !== win.id) dispatch({ type: 'focus', id: win.id }); }}>
          <div className={`title-bar ${state.active !== win.id ? 'inactive' : ''}`} tabIndex={0} aria-label={`Move ${app.title} with arrow keys`} onKeyDown={e => keyboard(e, win, 'move')} onPointerDown={e => begin(e, win, 'move')} onPointerMove={move} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }} onDoubleClick={e => { if (!(e.target as HTMLElement).closest('button')) dispatch({ type: 'maximize', id: win.id }); }}>
            <div className="title-bar-text" id={`title-${win.id}`}><Icon id={win.id} small/>{app.title}</div><div className="title-bar-controls"><button aria-label={`Minimize ${app.title}`} onClick={() => dispatch({ type: 'minimize', id: win.id })}/><button aria-label={`${win.maximized ? 'Restore' : 'Maximize'} ${app.title}`} className={win.maximized ? 'restore-button' : 'maximize-button'} onClick={() => dispatch({ type: 'maximize', id: win.id })}/><button aria-label={`Close ${app.title}`} onClick={() => dispatch({ type: 'close', id: win.id })}/></div>
          </div>
          <div className="window-menubar"><span>Vision client</span><span>{modeLabel(client.mode, snapshot)}</span><span>Read only</span></div>
          <div className="window-body"><AppContent id={win.id} snapshot={snapshot} reset={reset} persistence={persistence} refresh={client.canRefresh ? refresh : undefined} sessionControls={sessionControls} libraryControls={libraryControls}/></div>
          <footer className="status-bar"><p className="status-bar-field">{win.id === 'control' ? 'Local UI preferences' : 'No operational commands'}</p><p className="status-bar-field">{connectionLabel(snapshot)}</p>{!win.maximized && <button className="resize-handle" aria-label={`Resize ${app.title} with arrow keys`} onKeyDown={e => keyboard(e, win, 'resize')} onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); gesture.current = { id: win.id, kind: 'resize', x: e.clientX, y: e.clientY, rect: win.rect }; }} onPointerMove={move} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }}>◢</button>}</footer>
        </section>;
      })}
    </div>
    {start && <div className="start-menu window" ref={menuRef} role="menu" aria-label="Start applications" onKeyDown={e => { const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')); const i = items.indexOf(document.activeElement as HTMLButtonElement); if (['ArrowDown','ArrowUp','Home','End'].includes(e.key)) { e.preventDefault(); items[e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus(); } }}><div className="start-brand">VISION <b>Desktop</b></div><div className="start-items">{apps.map(app => <button role="menuitem" key={app.id} onClick={() => launch(app.id)}><Icon id={app.id} small/>{app.title}</button>)}<hr/><button role="menuitem" disabled>Log in… · unavailable</button><button role="menuitem" disabled>Restart system… · unavailable</button><button role="menuitem" disabled>Shut down system… · unavailable</button></div></div>}
    <footer className="taskbar"><button className={`start-button ${start ? 'pressed' : ''}`} ref={startRef} aria-expanded={start} aria-haspopup="menu" onClick={() => setStart(!start)}><span className="start-symbol" aria-hidden="true">V</span>Start</button><span className="taskbar-divider"/><div className="task-buttons">{state.windows.map(win => <button key={win.id} className={state.active === win.id && !win.minimized ? 'pressed' : ''} aria-pressed={state.active === win.id && !win.minimized} onClick={() => dispatch({ type: state.active === win.id && !win.minimized ? 'minimize' : 'focus', id: win.id })}><Icon id={win.id} small/><span>{apps.find(a => a.id === win.id)!.title}</span></button>)}</div><div className="tray" role="status">{connectionLabel(snapshot)}<span>Client only</span></div></footer>
  </main>;
}
