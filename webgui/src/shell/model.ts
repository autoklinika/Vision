export const apps = [
  { id: 'status', title: 'System Status', glyph: '▥', description: 'Connection & system report' },
  { id: 'ecu', title: 'ECU Library', glyph: '▤', description: 'Reference profiles & revisions' },
  { id: 'inspection', title: 'Inspection Manager', glyph: '✓', description: 'Specimen & inspection session' },
  { id: 'luxonis', title: 'Luxonis', glyph: '◈', description: 'RGB, depth & point cloud' },
  { id: 'nero', title: 'NERO', glyph: '⌁', description: 'Motion & planning report' },
  { id: 'sony', title: 'Sony', glyph: '◉', description: 'Camera & acquisition' },
  { id: 'images', title: 'Images', glyph: '▧', description: 'Image archive & metadata' },
  { id: 'control', title: 'Control Panel', glyph: '☷', description: 'Local desktop preferences' },
  { id: 'events', title: 'Event Viewer', glyph: '≡', description: 'System event journal' },
] as const;
export type AppId = typeof apps[number]['id'];
export type Bounds = { width: number; height: number };
export type Rect = { x: number; y: number; width: number; height: number };
export type WindowState = { id: AppId; rect: Rect; minimized: boolean; maximized: boolean };
export type DesktopState = { windows: WindowState[]; active: AppId | null };
export type Action = { type: 'open' | 'focus' | 'minimize' | 'maximize' | 'close'; id: AppId } | { type: 'rect'; id: AppId; rect: Rect } | { type: 'bounds' } | { type: 'reset' };
export const initialState: DesktopState = { windows: [{ id: 'status', rect: { x: 220, y: 48, width: 610, height: 500 }, minimized: false, maximized: false }], active: 'status' };
export function clamp(rect: Rect, bounds: Bounds): Rect {
  const width = Math.min(Math.max(280, rect.width), bounds.width);
  const height = Math.min(Math.max(240, rect.height), bounds.height);
  return { width, height, x: Math.max(0, Math.min(rect.x, bounds.width - width)), y: Math.max(0, Math.min(rect.y, bounds.height - height)) };
}
export function reduce(state: DesktopState, action: Action, bounds: Bounds): DesktopState {
  let windows = state.windows.map(w => ({ ...w, rect: clamp(w.rect, bounds) }));
  let active = state.active;
  if (action.type === 'reset') return { ...initialState, windows: initialState.windows.map(w => ({ ...w, rect: clamp(w.rect, bounds) })) };
  if (action.type === 'bounds') return { windows, active };
  const old = windows.find(w => w.id === action.id);
  if (action.type === 'open' && !old) windows.push({ id: action.id, rect: clamp({ x: 220 + windows.length * 24, y: 40 + windows.length * 24, width: 570, height: 380 }, bounds), minimized: false, maximized: false });
  if (action.type === 'open' || action.type === 'focus') {
    const win = windows.find(w => w.id === action.id);
    if (win) { windows = [...windows.filter(w => w.id !== action.id), { ...win, minimized: false }]; active = action.id; }
  }
  if (action.type === 'close') windows = windows.filter(w => w.id !== action.id);
  if (action.type === 'minimize') windows = windows.map(w => w.id === action.id ? { ...w, minimized: true } : w);
  if (action.type === 'maximize') {
    windows = windows.map(w => w.id === action.id ? { ...w, maximized: !w.maximized } : w);
    return reduce({ windows, active }, { type: 'focus', id: action.id }, bounds);
  }
  if (action.type === 'rect') windows = windows.map(w => w.id === action.id && !w.maximized ? { ...w, rect: clamp(action.rect, bounds) } : w);
  if (!windows.some(w => w.id === active && !w.minimized)) active = windows.filter(w => !w.minimized).at(-1)?.id ?? null;
  return { windows, active };
}
export const storageKey = 'vision.desktop.layout.v1';
export function decodeLayout(raw: string | null, bounds: Bounds): DesktopState {
  try {
    if (!raw || raw.length > 12000) throw Error();
    const data = JSON.parse(raw);
    if (data.version !== 1 || !Array.isArray(data.windows) || data.windows.length > apps.length) throw Error();
    const ids = new Set();
    const windows: WindowState[] = data.windows.map((w: WindowState) => {
      if (!apps.some(a => a.id === w.id) || ids.has(w.id) || typeof w.minimized !== 'boolean' || typeof w.maximized !== 'boolean' || !w.rect || !['x','y','width','height'].every(k => Number.isFinite(w.rect[k as keyof Rect]))) throw Error();
      ids.add(w.id);
      return { id: w.id, minimized: w.minimized, maximized: w.maximized, rect: clamp(w.rect, bounds) };
    });
    return { windows, active: windows.filter(w => !w.minimized).at(-1)?.id ?? null };
  } catch { return reduce(initialState, { type: 'bounds' }, bounds); }
}
export function encodeLayout(state: DesktopState): string { return JSON.stringify({ version: 1, windows: state.windows }); }
