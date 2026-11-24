/** Client presentation boundary v1; NOT an agreed Vision wire/API contract. */
export type Snapshot = Readonly<{
  schema: 'client-view-v1';
  source: 'demo' | 'real';
  connection: 'DEMO' | 'UNAVAILABLE';
  readiness: 'UNKNOWN';
  observedAt: null;
  reason: string;
  components: readonly Readonly<{ name: string; status: 'UNKNOWN'; reason: string }>[];
}>;
export interface ReadOnlyVisionClient {
  readonly mode: 'demo' | 'real';
  readSnapshot(): Promise<Snapshot>;
}
