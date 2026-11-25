import { librarySections } from '../../src/api/libraryContract';
import type { LibraryDetail, LibraryEntry, LibraryHistory, LibraryReport } from '../../src/api/libraryContract';

const identity = {scope: 'LIBRARY_READ_ONLY', source: 'SYNTHETIC_TEST', libraryId: 'synthetic-library', viewId: 'c'.repeat(64), capturedAt: '2026-11-25T01:02:03Z'} as const;
export const catalogEntry: LibraryEntry = {
  entryId: '1'.repeat(32), kind: 'CATALOG_RECORD', profileId: 'etc3_poc', family: 'ETC3', variant: 'provisional_3connector',
  revision: 'v1', displayName: 'ETC3', status: 'DRAFT', readiness: 'NOT_READY', reasonCode: 'CATALOG_ONLY', etag: null,
};
export const draftEntry: LibraryEntry = {
  entryId: '2'.repeat(32), kind: 'REFERENCE_DRAFT', profileId: 'api03_synthetic', family: 'ETC3', variant: 'provisional_3connector',
  revision: 'r1', displayName: 'API-03 synthetic reference', status: 'DRAFT', readiness: 'NOT_READY', reasonCode: 'UNSIGNED_DRAFT',
  etag: '"' + '53'.padStart(64, '0') + '"',
};
export function libraryFixture(totalCount = 2, after = 0): LibraryReport {
  const end = Math.min(after + 50, totalCount);
  return {...identity, schema: 'vision.api.library.v1', after, totalCount, nextAfter: end < totalCount ? end : null,
    entries: Array.from({length: end - after}, (_, offset) => {
      const i = after + offset;
      return i === 0 ? catalogEntry : i === 1 ? draftEntry : {...catalogEntry, entryId: String(i + 1).padStart(32, '0'), profileId: `catalog_${i}`, displayName: `Catalog ${i}`};
    })};
}
export function libraryDetailFixture(kind: 'catalog' | 'draft' = 'draft'): LibraryDetail {
  return kind === 'catalog' ? {...identity, schema: 'vision.api.library-entry.v1', entry: catalogEntry, profile: null,
    catalog: {connectors: [{id: 'black_1', color: 'black'}, {id: 'gray_1', color: 'gray'}], fieldNoteCount: 2, fieldNotesVerified: false, envelopePresent: false}}
    : {...identity, schema: 'vision.api.library-entry.v1', entry: draftEntry, catalog: null, profile: {
      sections: librarySections.map(name => ({name, rowCount: name === 'metadata' ? null : 0, status: 'NOT_EVALUATED'})),
      physicalStates: [{id: 'closed', displayName: 'Closed housing', declaredVerified: true}],
      workflows: [{id: 'browse', stateId: 'closed', scope: 'browse_and_select'}], historyCount: 53,
    }};
}
export function libraryHistoryFixture(detail = libraryDetailFixture(), after = 0): LibraryHistory {
  const totalCount = detail.profile!.historyCount;
  const end = Math.min(after + 50, totalCount);
  return {...identity, schema: 'vision.api.library-history.v1', entryId: detail.entry.entryId, profileId: detail.entry.profileId,
    revision: detail.entry.revision, etag: detail.entry.etag!, after, totalCount, nextAfter: end < totalCount ? end : null,
    items: Array.from({length: end - after}, (_, offset) => ({snapshotId: String(after + offset + 1).padStart(32, '0'),
      etag: '"' + String(after + offset + 1).padStart(64, '0') + '"', revision: detail.entry.revision}))};
}
