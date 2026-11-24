import type { ReadOnlyVisionClient, Snapshot } from '../api/types';
const fixture: Snapshot = Object.freeze({
  schema: 'client-view-v1', source: 'demo', connection: 'DEMO', readiness: 'UNKNOWN', observedAt: null,
  reason: 'Synthetic presentation fixture. No system connection or readiness assessment.',
  components: Object.freeze(['Vision Core', 'Runtime', 'ROS 2 integration', 'Luxonis', 'NERO / MoveIt 2', 'Sony Camera'].map(name => Object.freeze({ name, status: 'UNKNOWN' as const, reason: 'Demo fixture — no telemetry' }))),
});
export const demoAdapter: ReadOnlyVisionClient = Object.freeze({mode: 'demo', readSnapshot: async () => fixture});
