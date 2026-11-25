import { expect, it, vi } from 'vitest';
import { realAdapter } from '../src/api/realAdapter';
import { createStationClient } from '../src/station/client';
import { stationFixture } from './fixtures/station';
import { sessionFixture, eventsFixture } from './fixtures/session';
import { libraryFixture } from './fixtures/library';
vi.mock('../src/api/realAdapter', () => ({realAdapter: {mode: 'real', readSnapshot: vi.fn(), readSession: vi.fn(), readEvents: vi.fn(), readLibrary: vi.fn(), readLibraryEntry: vi.fn(), readLibraryHistory: vi.fn()}}));

it('idle station exposes no session request capability while its library remains available', async () => {
  const client = createStationClient(stationFixture(), vi.fn());
  expect(client.readSession).toBeUndefined(); expect(client.readEvents).toBeUndefined();
  expect(client.readLibrary).toBeTypeOf('function');
});
it('station composition rejects synthetic or mismatched owners and propagates revoked authorization', async () => {
  const denied = vi.fn(), station = stationFixture(true), client = createStationClient(station, denied);
  const session = {...sessionFixture(), source: 'STATION' as const, sessionId: station.sessionId!, viewId: station.sessionViewId!};
  vi.mocked(realAdapter.readSession!).mockResolvedValueOnce({status: 'AVAILABLE', report: sessionFixture()}).mockResolvedValueOnce({status: 'AVAILABLE', report: session}).mockResolvedValueOnce({status: 'ACCESS_DENIED', report: null});
  expect(await client.readSession!()).toEqual({status: 'UNAVAILABLE', report: null});
  expect((await client.readSession!()).status).toBe('AVAILABLE');
  expect((await client.readSession!()).status).toBe('ACCESS_DENIED'); expect(denied).toHaveBeenCalledTimes(1);
  vi.mocked(realAdapter.readEvents!).mockResolvedValueOnce({status: 'AVAILABLE', report: {...eventsFixture(session), sessionId: 'another'}});
  expect(await client.readEvents!(session, 0)).toEqual({status: 'UNAVAILABLE', report: null});
  vi.mocked(realAdapter.readLibrary!).mockResolvedValueOnce({status: 'AVAILABLE', report: libraryFixture()})
    .mockResolvedValueOnce({status: 'AVAILABLE', report: {...libraryFixture(), source: 'STATION', libraryId: station.libraryId}});
  expect(await client.readLibrary!()).toEqual({status: 'UNAVAILABLE', report: null});
  expect((await client.readLibrary!()).status).toBe('AVAILABLE');
});
