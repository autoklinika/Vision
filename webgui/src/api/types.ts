/** Client presentation boundary v1; NOT an agreed Vision wire/API contract. */
export type Snapshot = Readonly<{
  schema: 'client-view-v1';
  source: 'demo' | 'real';
  connection: 'DEMO' | 'UNAVAILABLE' | 'API_AVAILABLE';
  readiness: 'UNKNOWN';
  observedAt: null;
  reportTime: string | null;
  reason: string;
  components: readonly Readonly<{ name: string; status: 'UNKNOWN'; reason: string }>[];
}>;
export interface ReadOnlyVisionClient {
  readonly mode: 'demo' | 'real';
  readonly canRefresh?: boolean;
  readSnapshot(): Promise<Snapshot>;
}
