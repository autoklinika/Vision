export const navigationGroups = [
  {id: 'workspace', title: 'Workspace'},
  {id: 'devices', title: 'Devices'},
  {id: 'preferences', title: 'Preferences'},
] as const;

export const apps = [
  {id: 'status', title: 'System Status', group: 'workspace', description: 'Station connection, readiness and current activity.'},
  {id: 'ecu', title: 'ECU Library', group: 'workspace', description: 'Create, edit and review ECU reference profiles.'},
  {id: 'inspection', title: 'Inspection Manager', group: 'workspace', description: 'Follow the current specimen and inspection session.'},
  {id: 'images', title: 'Images', group: 'workspace', description: 'Browse inspection images and reference material.'},
  {id: 'events', title: 'Event Viewer', group: 'workspace', description: 'Review the events reported for the current session.'},
  {id: 'luxonis', title: 'Luxonis', group: 'devices', description: 'Camera, depth and point-cloud reports.'},
  {id: 'nero', title: 'NERO', group: 'devices', description: 'Robot, scene and motion-planning reports.'},
  {id: 'sony', title: 'Sony', group: 'devices', description: 'Camera acquisition and photograph reports.'},
  {id: 'control', title: 'Control Panel', group: 'preferences', description: 'Choose how this workspace opens in your browser.'},
  {id: 'settings', title: 'Settings', group: 'preferences', description: 'Manage your account and password.'},
] as const;

export type AppId = typeof apps[number]['id'];
export const storageKey = 'vision.workspace.v2';

export function readActiveApp(serialized: string | null): AppId {
  if (typeof serialized !== 'string' || serialized.length > 1024) return 'status';
  try {
    const value: unknown = JSON.parse(serialized);
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return 'status';
    const record = value as Record<string, unknown>;
    if (Object.keys(record).length !== 2 || record.schema !== storageKey) return 'status';
    return apps.find(app => app.id === record.activeApp)?.id ?? 'status';
  } catch {
    return 'status';
  }
}

export function encodeActiveApp(activeApp: AppId): string {
  return JSON.stringify({schema: storageKey, activeApp});
}
