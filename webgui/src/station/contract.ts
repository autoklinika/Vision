/** Station transport reports; no client-side readiness or workflow decisions. */
export type IdentityReport = Readonly<{
  schema: 'vision.api.identity.v1'; authenticated: true; username: string;
  role: 'reader'; expiresAt: string;
}>;
export type LogoutReport = Readonly<{schema: 'vision.api.logout.v1'; loggedOut: true}>;
export type PasswordChangeReport = Readonly<{schema: 'vision.api.password-change.v1'; changed: true}>;
export type StationReport = Readonly<{
  schema: 'vision.api.station.v1'; source: 'STATION'; instanceId: string;
  stationId: 'VENTUNO'; capturedAt: string; state: 'NO_ACTIVE_SESSION' | 'SESSION_ACTIVE';
  coreConnection: 'NOT_CONNECTED' | 'CONNECTED'; coreReadiness: 'UNKNOWN';
  sessionId: string | null; sessionViewId: string | null; libraryId: 'vision-ecu-library';
}>;
export function record(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function hex32(value: unknown): value is string { return typeof value === 'string' && value.length === 32 && !/[^a-f0-9]/.test(value); }
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || value.length !== 20 || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value.slice(0, -1) + '.000Z';
}
export function usernameValid(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= 64 && /^[A-Za-z0-9]/.test(value) && !/[^A-Za-z0-9_.-]/.test(value);
}
export function isIdentityReport(value: unknown): value is IdentityReport {
  return record(value, ['schema','authenticated','username','role','expiresAt']) && value.schema === 'vision.api.identity.v1' &&
    value.authenticated === true && value.role === 'reader' && usernameValid(value.username) && utc(value.expiresAt);
}
export function isLogoutReport(value: unknown): value is LogoutReport {
  return record(value, ['schema','loggedOut']) && value.schema === 'vision.api.logout.v1' && value.loggedOut === true;
}
export function isPasswordChangeReport(value: unknown): value is PasswordChangeReport {
  return record(value, ['schema','changed']) && value.schema === 'vision.api.password-change.v1' && value.changed === true;
}
export function isStationReport(value: unknown): value is StationReport {
  if (!record(value, ['schema','source','instanceId','stationId','capturedAt','state','coreConnection','coreReadiness','sessionId','sessionViewId','libraryId']) ||
      value.schema !== 'vision.api.station.v1' || value.source !== 'STATION' || !hex32(value.instanceId) || value.stationId !== 'VENTUNO' || !utc(value.capturedAt) ||
      value.libraryId !== 'vision-ecu-library' || value.coreReadiness !== 'UNKNOWN' || (value.coreConnection !== 'NOT_CONNECTED' && value.coreConnection !== 'CONNECTED')) return false;
  // A running Core can be idle. Only an actual inspection has session IDs.
  return value.state === 'NO_ACTIVE_SESSION' ? value.sessionId === null && value.sessionViewId === null :
    value.state === 'SESSION_ACTIVE' && value.coreConnection === 'CONNECTED' && typeof value.sessionId === 'string' && value.sessionId.length >= 1 && value.sessionId.length <= 128 &&
    !/[^A-Za-z0-9_.:-]/.test(value.sessionId) && hex32(value.sessionViewId);
}
