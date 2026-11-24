import { describe, expect, it } from 'vitest';
import { clamp, decodeLayout, encodeLayout, initialState, reduce } from '../src/shell/model';
const bounds = { width: 1000, height: 700 };
describe('window manager', () => {
  it('opens one instance, focuses to front and selects next window after minimize/close', () => {
    let s = reduce(initialState, { type: 'open', id: 'ecu' }, bounds);
    s = reduce(s, { type: 'open', id: 'ecu' }, bounds);
    expect(s.windows).toHaveLength(2);
    s = reduce(s, { type: 'focus', id: 'status' }, bounds);
    expect(s.windows.at(-1)?.id).toBe('status');
    s = reduce(s, { type: 'minimize', id: 'status' }, bounds);
    expect(s.active).toBe('ecu');
    s = reduce(s, { type: 'close', id: 'ecu' }, bounds);
    expect(s.active).toBeNull();
    s = reduce(s, { type: 'focus', id: 'status' }, bounds);
    expect(s.windows[0].minimized).toBe(false);
  });
  it('preserves restore geometry and ignores resize while maximized', () => {
    const s = reduce(initialState, { type: 'maximize', id: 'status' }, bounds);
    const moved = reduce(s, { type: 'rect', id: 'status', rect: { x: 0, y: 0, width: 300, height: 300 } }, bounds);
    expect(moved.windows[0].rect).toEqual(initialState.windows[0].rect);
    expect(reduce(moved, { type: 'maximize', id: 'status' }, bounds).windows[0].maximized).toBe(false);
  });
  it('clamps moves, resizes and restored preferences to small viewport', () => {
    expect(clamp({ x: -300, y: 999, width: 900, height: 800 }, { width: 240, height: 200 })).toEqual({ x: 0, y: 0, width: 240, height: 200 });
    const state = decodeLayout(encodeLayout(initialState), { width: 320, height: 400 });
    expect(state.windows[0].rect).toEqual({ x: 0, y: 0, width: 320, height: 400 });
  });
  it('recovers from malformed, oversized, duplicate, unknown and incompatible preferences', () => {
    for (const raw of ['{', 'x'.repeat(13000), JSON.stringify({version: 2, windows: []}), JSON.stringify({version: 1, windows: [...initialState.windows, ...initialState.windows]}), JSON.stringify({version: 1, windows: [{...initialState.windows[0], id: 'hardware'}]}), JSON.stringify({version: 1, windows: [{...initialState.windows[0], rect: {x: null}}]})]) expect(decodeLayout(raw, bounds)).toEqual(initialState);
    expect(decodeLayout(encodeLayout({ windows: [], active: null }), bounds).windows).toEqual([]);
  });
});
