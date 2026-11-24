import { expect, it, vi } from 'vitest';
import { readClientReport } from '../src/startup/report';
import { realAdapter } from '../src/api/realAdapter';
import { demoAdapter } from '../src/demo/adapter';

it('starts snapshot acquisition immediately and preserves the adapter report', async () => {
  const snapshot = await demoAdapter.readSnapshot();
  const readSnapshot = vi.fn().mockResolvedValue(snapshot);
  const pending = readClientReport({ mode: 'demo', readSnapshot });
  expect(readSnapshot).toHaveBeenCalledTimes(1);
  expect(await pending).toBe(snapshot);
});
it('rejected and synchronously throwing snapshots stay UNKNOWN in selected mode', async () => {
  for (const mode of ['real', 'demo'] as const) {
    for (const readSnapshot of [() => Promise.reject(new Error('private detail')), () => { throw new Error('private detail'); }]) {
      const snapshot = await readClientReport({ mode, readSnapshot });
      expect(snapshot).toMatchObject({ source: mode, readiness: 'UNKNOWN', connection: 'UNAVAILABLE', components: [] });
      expect(snapshot.reason).toContain('adapter failed');
      expect(snapshot.reason).not.toContain('private detail');
    }
  }
});
it('rejects a demo snapshot from the real adapter without fallback', async () => {
  const snapshot = await readClientReport({ ...realAdapter, readSnapshot: demoAdapter.readSnapshot });
  expect(snapshot.source).toBe('real');
  expect(snapshot.components).toEqual([]);
  expect(snapshot.reason).toContain('mismatched source');
});
