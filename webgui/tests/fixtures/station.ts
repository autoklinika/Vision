import type { IdentityReport, StationReport } from '../../src/station/contract';
export function identityFixture(username = 'operator'): IdentityReport {
  return {schema: 'vision.api.identity.v1', authenticated: true, username, role: 'reader', expiresAt: '2026-11-25T20:00:00Z'};
}
export function stationFixture(active = false): StationReport {
  return {schema: 'vision.api.station.v1', source: 'STATION', instanceId: 'e'.repeat(32), stationId: 'VENTUNO',
    capturedAt: '2026-11-25T12:00:00Z', state: active ? 'SESSION_ACTIVE' : 'NO_ACTIVE_SESSION',
    coreConnection: active ? 'CONNECTED' : 'NOT_CONNECTED', coreReadiness: 'UNKNOWN',
    sessionId: active ? 'station-session' : null, sessionViewId: active ? 'a'.repeat(32) : null, libraryId: 'vision-ecu-library'};
}
