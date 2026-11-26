/** Station transport reports; no client-side readiness or workflow decisions. */
export type IdentityReport = Readonly<{
  schema: 'vision.api.identity.v1'; authenticated: true; username: string;
  role: 'reader' | 'operator'; expiresAt: string;
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
    value.authenticated === true && (value.role === 'reader' || value.role === 'operator') && usernameValid(value.username) && utc(value.expiresAt);
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

export type DeviceId = 'luxonis' | 'nero' | 'moveit' | 'sony';
export type HardwareConnection = 'USB_DETECTED' | 'USB_NOT_DETECTED' | 'USB_CAN_DETECTED' | 'USB_CAN_NOT_DETECTED' | 'UNKNOWN' | 'NOT_APPLICABLE';
export const readinessReasons = {
  SERVICE_INACTIVE:'NOT_READY', SERVICE_UNKNOWN:'UNKNOWN', USB_MISSING:'NOT_READY', OBSERVER_UNAVAILABLE:'UNKNOWN',
  AMBIGUOUS_SCENE:'NOT_READY', JOINT_FEEDBACK_UNVERIFIED:'UNKNOWN', ARM_STATUS_UNVERIFIED:'UNKNOWN',
  ARM_BRAKE_NOT_RELEASED:'NOT_READY', ARM_FAULT:'NOT_READY', MOTOR_STATUS_UNVERIFIED:'UNKNOWN',
  MOTORS_NOT_ENABLED:'NOT_READY', NERO_TELEMETRY_OK:'READY', RGBD_UNVERIFIED:'UNKNOWN',
  RGBD_STREAMS_OK:'READY', SCENE_UNVERIFIED:'UNKNOWN', ROBOT_TF_UNVERIFIED:'UNKNOWN',
  PLANNING_DATA_OK:'READY', SONY_UNVERIFIED:'UNKNOWN',
} as const;
export type ReadinessReason = keyof typeof readinessReasons;
const commonReasons: readonly ReadinessReason[] = ['SERVICE_INACTIVE','SERVICE_UNKNOWN','USB_MISSING','OBSERVER_UNAVAILABLE'];
const deviceReasons: Readonly<Record<DeviceId,readonly ReadinessReason[]>> = {
  nero:['JOINT_FEEDBACK_UNVERIFIED','ARM_STATUS_UNVERIFIED','ARM_BRAKE_NOT_RELEASED','ARM_FAULT','MOTOR_STATUS_UNVERIFIED','MOTORS_NOT_ENABLED','NERO_TELEMETRY_OK'],
  luxonis:['RGBD_UNVERIFIED','RGBD_STREAMS_OK','AMBIGUOUS_SCENE'],
  moveit:['JOINT_FEEDBACK_UNVERIFIED','SCENE_UNVERIFIED','ROBOT_TF_UNVERIFIED','PLANNING_DATA_OK','AMBIGUOUS_SCENE'],
  sony:['SONY_UNVERIFIED'],
};
export type DeviceReport = Readonly<{device: DeviceId; availability: 'ACTIVE' | 'INACTIVE' | 'UNKNOWN'; readiness: 'READY' | 'NOT_READY' | 'UNKNOWN'; observedAt: string; hardwareConnection?: HardwareConnection; readinessReason?: ReadinessReason}>;
export type InspectionSelection = Readonly<{selectionId: string; family: string; variant: string; revision: string; physicalState: string; recipe: string}>;
const deviceIds = ['luxonis', 'nero', 'moveit', 'sony'] as const;
const blockerIds = ['COMPOSITION_UNCONFIGURED', 'NO_APPROVED_SELECTION', 'DEVICES_NOT_VERIFIED', 'SESSION_ACTIVE', 'RECOVERY_REQUIRED'] as const;
export type InspectionBlocker = typeof blockerIds[number];
export type InspectionReport = Readonly<{
  schema: 'vision.api.inspection.v1'; source: 'STATION'; instanceId: string; capturedAt: string;
  sessionId: string | null; intentToken: string; devices: readonly DeviceReport[]; selections: readonly InspectionSelection[];
  blockers: readonly InspectionBlocker[]; startAllowed: boolean; closeAllowed: boolean;
}>;
function identifier(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(value);
}
function isDevice(value: unknown, device: DeviceId): value is DeviceReport {
  const legacyKeys = ['device','availability','readiness','observedAt'];
  return (record(value, legacyKeys) || record(value, [...legacyKeys,'hardwareConnection']) ||
    record(value,[...legacyKeys,'readinessReason']) || record(value,[...legacyKeys,'hardwareConnection','readinessReason'])) && value.device === device &&
    (!Object.hasOwn(value,'readinessReason') || (typeof value.readinessReason === 'string' &&
      Object.hasOwn(readinessReasons,value.readinessReason) && readinessReasons[value.readinessReason as ReadinessReason]===value.readiness &&
      (commonReasons.includes(value.readinessReason as ReadinessReason)||deviceReasons[device].includes(value.readinessReason as ReadinessReason)))) &&
    (!Object.hasOwn(value,'hardwareConnection') || value.hardwareConnection === 'UNKNOWN' ||
      ((device === 'luxonis' || device === 'sony') && (value.hardwareConnection === 'USB_DETECTED' || value.hardwareConnection === 'USB_NOT_DETECTED')) ||
      (device === 'nero' && (value.hardwareConnection === 'USB_CAN_DETECTED' || value.hardwareConnection === 'USB_CAN_NOT_DETECTED')) ||
      (device === 'moveit' && value.hardwareConnection === 'NOT_APPLICABLE')) &&
    ['ACTIVE','INACTIVE','UNKNOWN'].includes(String(value.availability)) && typeof value.availability === 'string' &&
    ['READY','NOT_READY','UNKNOWN'].includes(String(value.readiness)) && typeof value.readiness === 'string' &&
    (value.readiness !== 'READY' || value.availability === 'ACTIVE') && utc(value.observedAt);
}
function isSelection(value: unknown): value is InspectionSelection {
  return record(value, ['selectionId','family','variant','revision','physicalState','recipe']) && Object.values(value).every(identifier);
}
export function isInspectionReport(value: unknown): value is InspectionReport {
  if (!record(value, ['schema','source','instanceId','capturedAt','sessionId','intentToken','devices','selections','blockers','startAllowed','closeAllowed'])
      || value.schema !== 'vision.api.inspection.v1' || value.source !== 'STATION' || !hex32(value.instanceId) || !hex32(value.intentToken) || !utc(value.capturedAt)
      || (value.sessionId !== null && (typeof value.sessionId !== 'string' || !/^[A-Za-z0-9_.:-]{1,128}$/.test(value.sessionId)))
      || typeof value.startAllowed !== 'boolean' || typeof value.closeAllowed !== 'boolean'
      || !Array.isArray(value.devices) || value.devices.length !== deviceIds.length
      || !deviceIds.every((device, index) => isDevice((value.devices as unknown[])[index], device))
      || !Array.isArray(value.selections) || value.selections.length > 16 || !value.selections.every(isSelection)
      || new Set(value.selections.map(s => s.selectionId)).size !== value.selections.length
      || !Array.isArray(value.blockers) || !value.blockers.every(b => typeof b === 'string' && (blockerIds as readonly string[]).includes(b))
      || new Set(value.blockers).size !== value.blockers.length
      || value.startAllowed !== (value.blockers.length === 0) || (value.closeAllowed && value.sessionId === null)) return false;
  return !value.startAllowed || (value.sessionId === null && value.selections.length > 0 && value.devices.every(d => d.readiness === 'READY' && !Object.hasOwn(d,'readinessReason')));
}
