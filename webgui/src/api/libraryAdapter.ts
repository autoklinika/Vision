import { requestProtected } from './protectedAdapter';
import type { ProtectedResult } from './protectedAdapter';
import { isLibraryDetail, isLibraryEntry, isLibraryHistory, isLibraryReport, matchesLibrary, matchesLibraryDetail, matchesLibraryHistory } from './libraryContract';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from './libraryContract';

export const libraryTimeoutMs = 15000;

const unavailable = {status: 'UNAVAILABLE', report: null} as const;
export async function readLibrary(prior?: LibraryReport, after = 0): Promise<ProtectedResult<LibraryReport>> {
  if (!Number.isSafeInteger(after) || after < 0 || after % 50 !== 0 || (prior ? !isLibraryReport(prior) || after >= prior.totalCount && !(after === 0 && prior.totalCount === 0) : after !== 0)) return unavailable;
  const path = prior ? `/api/v1/library?view=${prior.viewId}&after=${after}` : '/api/v1/library';
  return requestProtected(path, (value): value is LibraryReport => isLibraryReport(value) && (prior ? matchesLibrary(value, prior, after) : value.after === 0), libraryTimeoutMs);
}
export async function readLibraryEntry(library: LibraryReport, entry: LibraryEntry): Promise<ProtectedResult<LibraryDetail>> {
  if (!isLibraryReport(library) || !isLibraryEntry(entry) || !library.entries.some(item =>
    (Object.keys(entry) as (keyof LibraryEntry)[]).every(key => item[key] === entry[key]))) return unavailable;
  return requestProtected(`/api/v1/library/entries/${entry.entryId}?view=${library.viewId}`,
    (value): value is LibraryDetail => isLibraryDetail(value) && matchesLibraryDetail(value, library, entry), libraryTimeoutMs);
}
export async function readLibraryHistory(detail: LibraryDetail, after = 0): Promise<ProtectedResult<LibraryHistory>> {
  if (!isLibraryDetail(detail) || !detail.profile || !Number.isSafeInteger(after) || after < 0 || after % 50 !== 0 || after >= detail.profile.historyCount) return unavailable;
  return requestProtected(`/api/v1/library/entries/${detail.entry.entryId}/history?view=${detail.viewId}&after=${after}`,
    (value): value is LibraryHistory => isLibraryHistory(value) && matchesLibraryHistory(value, detail, after), libraryTimeoutMs);
}
