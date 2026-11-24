import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { createClient } from '../src/api/client';
afterEach(() => vi.unstubAllGlobals());
it('demo reads have no network and never report readiness', async () => {
  const network = vi.fn(() => { throw Error('Network forbidden'); });
  vi.stubGlobal('fetch', network); vi.stubGlobal('WebSocket', network); vi.stubGlobal('XMLHttpRequest', network);
  const client = await createClient('demo');
  const a = await client.readSnapshot();
  expect(a).toEqual(await client.readSnapshot());
  expect(a.source).toBe('demo'); expect(a.readiness).toBe('UNKNOWN'); expect(a.observedAt).toBeNull();
  expect(Object.keys(client).sort()).toEqual(['mode','readSnapshot']);
  expect(network).not.toHaveBeenCalled();
});
it('real and invalid selections fail closed without demo fallback or network', async () => {
  const network = vi.fn(); vi.stubGlobal('fetch', network); vi.stubGlobal('WebSocket', network); vi.stubGlobal('XMLHttpRequest', network);
  for (const mode of ['real', 'invalid', '']) {
    const client = await createClient(mode); const s = await client.readSnapshot();
    expect(client.mode).toBe('real'); expect(s.source).toBe('real'); expect(s.connection).toBe('UNAVAILABLE'); expect(s.components).toEqual([]);
  }
  expect(network).not.toHaveBeenCalled();
  expect(readFileSync(new URL('../src/api/realAdapter.ts', import.meta.url), 'utf8')).not.toMatch(/from\s+['"].*demo/);
});
