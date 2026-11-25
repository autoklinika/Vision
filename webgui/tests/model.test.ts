import { describe, expect, it } from 'vitest';
import { apps, encodeActiveApp, readActiveApp, storageKey } from '../src/shell/model';

describe('workspace navigation preferences', () => {
  it('remembers each supported page without storing form or station data', () => {
    expect(storageKey).toBe('vision.workspace.v2');
    for (const app of apps) {
      const encoded = encodeActiveApp(app.id);
      expect(readActiveApp(encoded)).toBe(app.id);
      expect(JSON.parse(encoded)).toEqual({schema: 'vision.workspace.v2', activeApp: app.id});
    }
  });

  it('starts safely when preferences are absent, malformed or from the old window manager', () => {
    for (const raw of [null, '', '{', 'x'.repeat(13000), 'null', '[]', '42',
      JSON.stringify({version: 1, windows: [{id: 'ecu', rect: {x: 0, y: 0, width: 810, height: 610}}]}),
      JSON.stringify({schema: 'vision.workspace.v1', activeApp: 'ecu'}),
      JSON.stringify({schema: 'vision.workspace.v2', activeApp: 'unknown'}),
      JSON.stringify({schema: 'vision.workspace.v2', activeApp: null}),
      JSON.stringify({schema: 'vision.workspace.v2', activeApp: 'ecu', document: 'must not restore'})]) {
      expect(readActiveApp(raw)).toBe('status');
    }
  });
});
