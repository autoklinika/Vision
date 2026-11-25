import type { ReadOnlyVisionClient, Snapshot } from './types';
import { realAdapter } from './realAdapter';

const invalidAdapter: ReadOnlyVisionClient = Object.freeze({
  mode: 'real',
  readSnapshot: async (): Promise<Snapshot> => ({
    schema: 'client-view-v1', source: 'real', connection: 'UNAVAILABLE', readiness: 'UNKNOWN',
    observedAt: null, reportTime: null, components: [],
    reason: 'Real adapter unavailable: invalid client mode. API was not contacted.',
  }),
});

/** Explicit selection only. Invalid modes never request API or fall back to demo. */
export async function createClient(mode: string): Promise<ReadOnlyVisionClient> {
  if (mode === 'demo') return (await import('../demo/adapter')).demoAdapter;
  return mode === 'real' ? realAdapter : invalidAdapter;
}
