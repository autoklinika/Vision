import { realAdapter } from '../api/realAdapter';
import type { ReadOnlyVisionClient } from '../api/types';
import type { ProtectedResult } from '../api/protectedAdapter';
import type { IdentityReport, StationReport } from './contract';

export type StationPresentation = Readonly<{
  identity: IdentityReport; report: StationReport; refresh: () => void; logout: () => void;
}>;

/** Authenticated composition pins every projection to this station and owner. */
export function createStationClient(report: StationReport, denied: () => void): ReadOnlyVisionClient {
  async function checked<T>(pending: Promise<ProtectedResult<T>>, valid: (value: T) => boolean): Promise<ProtectedResult<T>> {
    const result = await pending;
    if (result.status === 'ACCESS_DENIED') denied();
    if (result.status === 'AVAILABLE' && !valid(result.report)) return {status: 'UNAVAILABLE', report: null};
    return result;
  }
  return Object.freeze({
    ...realAdapter,
    readSession: report.state === 'SESSION_ACTIVE' ? () => checked(realAdapter.readSession!(), session => session.source === 'STATION' && session.sessionId === report.sessionId && session.viewId === report.sessionViewId) : undefined,
    readEvents: report.state === 'SESSION_ACTIVE' ? (session, after) => checked(realAdapter.readEvents!(session, after), events => events.source === 'STATION' && events.sessionId === report.sessionId && events.viewId === report.sessionViewId) : undefined,
    readLibrary: (prior, after) => checked(realAdapter.readLibrary!(prior, after), library => library.source === 'STATION' && library.libraryId === report.libraryId),
    readLibraryEntry: (library, entry) => checked(realAdapter.readLibraryEntry!(library, entry), detail => detail.source === 'STATION' && detail.libraryId === report.libraryId),
    readLibraryHistory: (detail, after) => checked(realAdapter.readLibraryHistory!(detail, after), history => history.source === 'STATION' && history.libraryId === report.libraryId),
  } satisfies ReadOnlyVisionClient);
}
