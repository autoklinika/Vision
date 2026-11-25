import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { createClient } from '../src/api/client';
import { readLibrary, readLibraryEntry, readLibraryHistory } from '../src/api/libraryAdapter';
import { isLibraryDetail, isLibraryEntry, isLibraryHistory, isLibraryReport, matchesLibrary, matchesLibraryDetail, matchesLibraryHistory } from '../src/api/libraryContract';
import { catalogEntry, draftEntry, libraryDetailFixture, libraryFixture, libraryHistoryFixture } from './fixtures/library';

const origin = 'http://127.0.0.1:4173';
const base = origin + '/api/v1/library';
function secure() { vi.stubGlobal('isSecureContext', true); vi.stubGlobal('location', new URL(origin)); }
function response(value: unknown, url = base, status = 200) {
  const result = new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json; charset=utf-8'}});
  Object.defineProperty(result, 'url', {value: url}); return result;
}
afterEach(() => { vi.unstubAllGlobals(); });

it('accepts the shared reports captured from the actual backend projection', () => {
  const shared = JSON.parse(readFileSync(new URL('../../contracts/vision-api/v1/library-fixtures.json', import.meta.url), 'utf8'));
  expect(isLibraryReport(shared.library)).toBe(true);
  expect(isLibraryDetail(shared.catalogEntry)).toBe(true);
  expect(isLibraryDetail(shared.profileEntry)).toBe(true);
  expect(isLibraryHistory(shared.history)).toBe(true);
  expect(matchesLibraryDetail(shared.profileEntry, shared.library, shared.profileEntry.entry)).toBe(true);
  expect(matchesLibraryHistory(shared.history, shared.profileEntry, 0)).toBe(true);
});

it('library projections preserve catalog/draft distinctions and exact pagination', () => {
  for (const value of [libraryFixture(), libraryFixture(0), libraryFixture(51), libraryFixture(51, 50)]) expect(isLibraryReport(value)).toBe(true);
  for (const value of [
    {...libraryFixture(), extra: 'private'}, {...libraryFixture(), scope: 'SESSION_READ_ONLY'}, {...libraryFixture(), source: 'demo'},
    {...libraryFixture(), libraryId: '../private'}, {...libraryFixture(), viewId: 'A'.repeat(64)}, {...libraryFixture(), capturedAt: '2026-02-30T01:02:03Z'},
    {...libraryFixture(), totalCount: 513}, {...libraryFixture(), totalCount: 2.5}, {...libraryFixture(), nextAfter: 2},
    {...libraryFixture(), entries: [draftEntry, draftEntry]}, {...libraryFixture(51), nextAfter: null}, {...libraryFixture(51), entries: [catalogEntry]},
    {...libraryFixture(51, 50), after: 49}, {...libraryFixture(), entries: [{...catalogEntry, readiness: 'READY'}, draftEntry]},
  ]) expect(isLibraryReport(value)).toBe(false);
  for (const value of [
    {...draftEntry, status: 'APPROVED'}, {...draftEntry, etag: null}, {...draftEntry, reasonCode: 'CATALOG_ONLY'},
    {...draftEntry, displayName: 'x'.repeat(161)}, {...draftEntry, displayName: 'bad\nlabel'}, {...draftEntry, profileId: 'a/b'},
    {...catalogEntry, etag: draftEntry.etag}, {...catalogEntry, reasonCode: 'UNSIGNED_DRAFT'}, {...catalogEntry, kind: 'SPECIMEN'},
    {...catalogEntry, status: ['DRAFT']}, {...draftEntry, displayName: 'control\u0085label'}, {...draftEntry, displayName: 'path/to/value'},
    {...draftEntry, displayName: 'path\\value'}, {...draftEntry, displayName: '\u200eformat'}, {...draftEntry, displayName: '\ud800'},
    {...draftEntry, profileId: 'draft\n'}, {...draftEntry, etag: draftEntry.etag + '\n'}, {...draftEntry, entryId: 'a'.repeat(31) + '\n'},
  ]) expect(isLibraryEntry(value)).toBe(false);
  expect(isLibraryEntry({...draftEntry, displayName: '😀'.repeat(160)})).toBe(true);
  expect(isLibraryEntry({...draftEntry, displayName: '😀'.repeat(161)})).toBe(false);
});

it('detail validators reject unprojected payloads, mixed record types and malformed section/state references', () => {
  const detail = libraryDetailFixture();
  const catalog = libraryDetailFixture('catalog');
  expect(isLibraryDetail(detail)).toBe(true); expect(isLibraryDetail(catalog)).toBe(true);
  for (const value of [
    {...detail, rawProfile: {}}, {...detail, catalog: catalog.catalog}, {...catalog, profile: detail.profile},
    {...catalog, catalog: {...catalog.catalog, fieldNotesVerified: true}}, {...catalog, catalog: {...catalog.catalog, connectors: [{id: 'x', color: 'gray', path: '/private'}]}},
    {...detail, profile: {...detail.profile, sections: detail.profile!.sections.slice(1)}},
    {...detail, profile: {...detail.profile, sections: [...detail.profile!.sections].reverse()}},
    {...detail, profile: {...detail.profile, sections: detail.profile!.sections.map(section => ({...section, status: 'VERIFIED'}))}},
    {...detail, profile: {...detail.profile, sections: detail.profile!.sections.map(section => ({...section, rowCount: -1}))}},
    {...detail, profile: {...detail.profile, physicalStates: [detail.profile!.physicalStates[0], detail.profile!.physicalStates[0]]}},
    {...detail, profile: {...detail.profile, workflows: [{id: 'browse', stateId: 'missing', scope: 'browse_and_select'}]}},
    {...detail, profile: {...detail.profile, historyCount: 0}},
  ]) expect(isLibraryDetail(value)).toBe(false);
});

it('history is bounded and ties the final generation to the current ETag without mixing views', () => {
  const library = libraryFixture(), detail = libraryDetailFixture(), first = libraryHistoryFixture(), last = libraryHistoryFixture(detail, 50);
  expect(isLibraryHistory(first)).toBe(true); expect(isLibraryHistory(last)).toBe(true);
  expect(matchesLibraryHistory(first, detail, 0)).toBe(true); expect(matchesLibraryDetail(detail, library, draftEntry)).toBe(true);
  expect(matchesLibrary(libraryFixture(51, 50), libraryFixture(51), 50)).toBe(true);
  for (const value of [
    {...first, nextAfter: null}, {...first, totalCount: 4097}, {...first, after: 1}, {...first, items: [first.items[0]]},
    {...first, items: [first.items[0], ...first.items.slice(0, 49)]}, {...last, etag: first.items[0].etag},
    {...last, items: last.items.map(item => ({...item, revision: 'another'}))},
    {...last, items: last.items.map(item => ({...item, profile: {private: true}}))},
  ]) expect(isLibraryHistory(value)).toBe(false);
  for (const delta of [{viewId: 'f'.repeat(64)}, {source: 'STATION' as const}, {libraryId: 'another'}]) {
    expect(matchesLibrary({...library, ...delta}, library, 0)).toBe(false);
    expect(matchesLibraryDetail({...detail, ...delta}, library, draftEntry)).toBe(false);
    expect(matchesLibraryHistory({...first, ...delta}, detail, 0)).toBe(false);
  }
  expect(matchesLibraryHistory({...first, etag: '"' + 'f'.repeat(64) + '"'}, detail, 0)).toBe(false);
  expect(matchesLibraryDetail({...detail, entry: {...draftEntry, revision: 'r2'}}, library, draftEntry)).toBe(false);
  expect(matchesLibraryHistory(first, detail, 50)).toBe(false);
});

it('library transport issues only explicit same-origin GETs with exact view and entry selectors', async () => {
  secure(); const library = libraryFixture(), detail = libraryDetailFixture();
  const detailUrl = `${base}/entries/${draftEntry.entryId}?view=${library.viewId}`;
  const historyUrl = `${base}/entries/${draftEntry.entryId}/history?view=${library.viewId}&after=0`;
  const network = vi.fn().mockResolvedValueOnce(response(library)).mockResolvedValueOnce(response(detail, detailUrl))
    .mockResolvedValueOnce(response(libraryHistoryFixture(), historyUrl));
  vi.stubGlobal('fetch', network);
  expect((await readLibrary()).status).toBe('AVAILABLE');
  expect((await readLibraryEntry(library, draftEntry)).status).toBe('AVAILABLE');
  expect((await readLibraryHistory(detail)).status).toBe('AVAILABLE');
  expect(network.mock.calls.map(call => String(call[0]))).toEqual([base, detailUrl, historyUrl]);
  for (const [, init] of network.mock.calls) expect(init).toMatchObject({method: 'GET', mode: 'same-origin', credentials: 'same-origin', cache: 'no-store', redirect: 'error'});
});

it('invalid selectors send nothing and wrong response identity is never presented', async () => {
  secure(); const library = libraryFixture(), detail = libraryDetailFixture();
  const network = vi.fn(); vi.stubGlobal('fetch', network);
  for (const after of [-1, 1, 51, NaN, Number.MAX_SAFE_INTEGER + 1]) {
    expect(await readLibrary(library, after)).toEqual({status: 'UNAVAILABLE', report: null});
    expect(await readLibraryHistory(detail, after)).toEqual({status: 'UNAVAILABLE', report: null});
  }
  expect(await readLibrary(undefined, 50)).toEqual({status: 'UNAVAILABLE', report: null});
  expect(await readLibraryEntry(library, {...draftEntry, entryId: 'f'.repeat(32)})).toEqual({status: 'UNAVAILABLE', report: null});
  expect(await readLibraryEntry(library, {...draftEntry, revision: 'r2'})).toEqual({status: 'UNAVAILABLE', report: null});
  expect(await readLibraryHistory(libraryDetailFixture('catalog'))).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network).not.toHaveBeenCalled();
  network.mockResolvedValueOnce(response({...libraryFixture(51, 50), viewId: 'f'.repeat(64)}, `${base}?view=${library.viewId}&after=50`));
  expect(await readLibrary(libraryFixture(51), 50)).toEqual({status: 'UNAVAILABLE', report: null});
  network.mockResolvedValueOnce(response({...detail, entry: {...draftEntry, revision: 'r2'}}, `${base}/entries/${draftEntry.entryId}?view=${library.viewId}`));
  expect(await readLibraryEntry(library, draftEntry)).toEqual({status: 'UNAVAILABLE', report: null});
});

it('unauthorized, stale, disconnected and malformed reports return no protected data', async () => {
  secure();
  for (const [status, outcome] of [[401, 'ACCESS_DENIED'], [403, 'ACCESS_DENIED'], [409, 'UNAVAILABLE'], [503, 'UNAVAILABLE']] as const) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({private: 'do not display'}, base, status)));
    expect(await readLibrary()).toEqual({status: outcome, report: null});
  }
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private transport detail')));
  expect(await readLibrary()).toEqual({status: 'UNAVAILABLE', report: null});
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({...libraryFixture(), rawProfile: {private: true}})));
  expect(await readLibrary()).toEqual({status: 'UNAVAILABLE', report: null});
});

it('demo and invalid modes have no library capability; insecure contexts send nothing', async () => {
  secure(); const network = vi.fn(); vi.stubGlobal('fetch', network);
  for (const mode of ['demo','invalid','','REAL']) {
    const client = await createClient(mode);
    expect(client.readLibrary).toBeUndefined(); expect(client.readLibraryEntry).toBeUndefined(); expect(client.readLibraryHistory).toBeUndefined();
  }
  vi.stubGlobal('isSecureContext', false);
  expect(await readLibrary()).toEqual({status: 'UNAVAILABLE', report: null});
  expect(network).not.toHaveBeenCalled();
});
