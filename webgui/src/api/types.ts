import type { ProtectedResult } from './protectedAdapter';
import type { EventsReport, SessionReport } from './sessionContract';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from './libraryContract';
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
  readonly readSession?: () => Promise<ProtectedResult<SessionReport>>;
  readonly readEvents?: (session: SessionReport, after: number) => Promise<ProtectedResult<EventsReport>>;
  readonly readLibrary?: (prior?: LibraryReport, after?: number) => Promise<ProtectedResult<LibraryReport>>;
  readonly readLibraryEntry?: (library: LibraryReport, entry: LibraryEntry) => Promise<ProtectedResult<LibraryDetail>>;
  readonly readLibraryHistory?: (detail: LibraryDetail, after?: number) => Promise<ProtectedResult<LibraryHistory>>;
}
