import type { ReadOnlyVisionClient, Snapshot } from './types';
/** No transport until a versioned backend contract has been reviewed. No demo import. */
export const realAdapter: ReadOnlyVisionClient = Object.freeze({
  mode: 'real',
  readSnapshot: async (): Promise<Snapshot> => ({ schema: 'client-view-v1', source: 'real', connection: 'UNAVAILABLE', readiness: 'UNKNOWN', observedAt: null, reason: 'Real adapter unavailable: Vision API contract and transport are not integrated.', components: [] }),
});
