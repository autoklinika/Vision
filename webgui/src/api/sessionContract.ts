/** API-02 wire projection. These fields report Core; the client never advances it. */
export const stageStates = ['PENDING','READY','RUNNING','SUCCEEDED','FAILED','CANCELLED','BLOCKED','TIMED_OUT'] as const;
export type StageState = typeof stageStates[number];
export const eventKinds = ['config_pinned','transition','dispatch','ack','denied','context_invalidated','result_accepted','result_rejected','localization_accepted','module_verified','preparation_verified','planning_verified','motion_verified','capture_verified','capture_complete_verified','quality_verified','module_archive_verified','archive_verified','OTHER'] as const;
export type EventKind = typeof eventKinds[number];
export type ReportSource = 'SYNTHETIC_TEST' | 'STATION';
export type StageReport = Readonly<{
  id: string; state: StageState; historicalSuccess: boolean;
  lastTransitionSequence: number | null; lastAckSequence: number | null;
}>;
type ReportIdentity = Readonly<{
  scope: 'SESSION_READ_ONLY'; source: ReportSource; viewId: string;
  sessionId: string; capturedAt: string;
}>;
export type SessionReport = ReportIdentity & Readonly<{
  schema: 'vision.api.session.v1'; journalSequence: number;
  invalidated: boolean; stages: readonly StageReport[];
}>;
export type EventReport = Readonly<{
  sequence: number; stageId: string | null; kind: EventKind;
  timestamp: string; state: StageState | null;
}>;
export type EventsReport = ReportIdentity & Readonly<{
  schema: 'vision.api.events.v1'; throughSequence: number; afterSequence: number;
  nextAfterSequence: number | null; events: readonly EventReport[];
}>;

function record(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function integer(value: unknown): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0; }
function identifier(value: unknown, max: number): value is string { return typeof value === 'string' && value.length <= max && /^[A-Za-z0-9_.:-]+$/.test(value); }
function utc(value: unknown): value is string {
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(value) || value.startsWith('0000')) return false;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) && date.toISOString() === value.slice(0, -1) + '.000Z';
}
function state(value: unknown): value is StageState { return stageStates.some(s => s === value); }
function identity(value: Record<string, unknown>): boolean {
  return value.scope === 'SESSION_READ_ONLY' && (value.source === 'SYNTHETIC_TEST' || value.source === 'STATION') &&
    typeof value.viewId === 'string' && /^[a-f0-9]{32}$/.test(value.viewId) &&
    identifier(value.sessionId, 128) && utc(value.capturedAt);
}
function sequence(value: unknown, high: number): boolean { return value === null || (integer(value) && value > 0 && value <= high); }

export function isSessionReport(value: unknown): value is SessionReport {
  if (!record(value, ['schema','scope','source','viewId','sessionId','capturedAt','journalSequence','invalidated','stages']) ||
      value.schema !== 'vision.api.session.v1' || !identity(value) || !integer(value.journalSequence) ||
      typeof value.invalidated !== 'boolean' || !Array.isArray(value.stages) || value.stages.length < 11 || value.stages.length > 256) return false;
  const high = value.journalSequence;
  const ids = new Set<string>();
  for (const stage of value.stages) {
    if (!record(stage, ['id','state','historicalSuccess','lastTransitionSequence','lastAckSequence']) ||
        !identifier(stage.id, 64) || ids.has(stage.id) || !state(stage.state) || typeof stage.historicalSuccess !== 'boolean' ||
        !sequence(stage.lastTransitionSequence, high) || !sequence(stage.lastAckSequence, high)) return false;
    if ((value.invalidated && stage.state !== 'BLOCKED') || (stage.state === 'SUCCEEDED' && !stage.historicalSuccess)) return false;
    ids.add(stage.id);
  }
  return Array.from({length: 11}, (_, i) => `S${String(i + 1).padStart(2, '0')}`).every(id => ids.has(id));
}

export function isEventsReport(value: unknown): value is EventsReport {
  if (!record(value, ['schema','scope','source','viewId','sessionId','capturedAt','throughSequence','afterSequence','nextAfterSequence','events']) ||
      value.schema !== 'vision.api.events.v1' || !identity(value) || !integer(value.throughSequence) ||
      !integer(value.afterSequence) || value.afterSequence > value.throughSequence ||
      !Array.isArray(value.events) || value.events.length > 50) return false;
  let previous = value.afterSequence;
  for (const event of value.events) {
    if (!record(event, ['sequence','stageId','kind','timestamp','state']) || !integer(event.sequence) ||
        event.sequence <= previous || event.sequence > value.throughSequence ||
        !(event.stageId === null || identifier(event.stageId, 64)) || !eventKinds.some(kind => kind === event.kind) ||
        !utc(event.timestamp) || !(event.state === null || state(event.state))) return false;
    if (event.kind === 'transition' ? !state(event.state) :
        event.kind === 'localization_accepted' ? event.state !== 'SUCCEEDED' : event.state !== null) return false;
    previous = event.sequence;
  }
  return (value.nextAfterSequence === null && previous === value.throughSequence) ||
    (value.events.length === 50 && value.nextAfterSequence === previous && previous < value.throughSequence);
}

/** Reject a new owner or a mismatched cursor instead of combining two reports. */
export function matchesSession(page: EventsReport, session: SessionReport, after: number): boolean {
  return page.viewId === session.viewId && page.sessionId === session.sessionId && page.source === session.source &&
    page.throughSequence === session.journalSequence && page.afterSequence === after &&
    page.events.every(event => event.stageId === null || session.stages.some(stage => stage.id === event.stageId));
}
