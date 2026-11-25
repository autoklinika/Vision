import type { ReadOnlyVisionClient, Snapshot } from './types';

export function connectionLabel(snapshot: Snapshot | null): string {
  return snapshot?.connection === 'API_AVAILABLE' ? 'API AVAILABLE (last report)' : snapshot?.connection ?? 'UNKNOWN';
}

export function modeLabel(mode: ReadOnlyVisionClient['mode'], snapshot: Snapshot | null): string {
  if (mode === 'demo') return 'DEMO';
  if (snapshot === null) return 'REAL · WAITING';
  return snapshot.connection === 'API_AVAILABLE' ? 'REAL · API REPORT' : 'REAL · UNAVAILABLE';
}

export function modeDescription(mode: ReadOnlyVisionClient['mode'], snapshot: Snapshot | null): string {
  if (mode === 'demo') return 'Synthetic fixtures only · No connection to Vision or hardware';
  if (snapshot?.connection === 'API_AVAILABLE') return 'API-only last report · Core UNKNOWN';
  return 'Read-only client · No verified system status';
}
