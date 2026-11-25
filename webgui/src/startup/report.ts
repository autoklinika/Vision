import type { ReadOnlyVisionClient, Snapshot } from '../api/types';

export async function readClientReport(client: ReadOnlyVisionClient): Promise<Snapshot> {
  try {
    const snapshot = await client.readSnapshot();
    if (snapshot.source !== client.mode) throw new Error('Source mismatch');
    return snapshot;
  } catch {
    return {
      schema: 'client-view-v1', source: client.mode, connection: 'UNAVAILABLE',
      readiness: 'UNKNOWN', observedAt: null, reportTime: null, components: [],
      reason: 'Snapshot unavailable: selected adapter failed or returned a mismatched source. System state is UNKNOWN.',
    };
  }
}
