/** Narrow API-01 wire schema; an API response cannot claim device readiness. */
export type BootStatus = Readonly<{
  schema: 'vision.api.status.v1';
  scope: 'LAB_API_ONLY';
  api: 'AVAILABLE';
  reportTime: string;
  coreReadiness: 'UNKNOWN';
  observedAt: null;
  reasonCode: 'CORE_REPORT_NOT_CONNECTED';
  components: readonly [];
}>;

const keys = ['schema','scope','api','reportTime','coreReadiness','observedAt','reasonCode','components'];

export function isBootStatus(value: unknown): value is BootStatus {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const x = value as Record<string, unknown>;
  if (Object.keys(x).length !== keys.length || !keys.every(key => Object.hasOwn(x,key))) return false;
  if (typeof x.reportTime !== 'string' ||
      !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/.test(x.reportTime) ||
      x.reportTime.startsWith('0000')) return false;
  const parsed = new Date(x.reportTime);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== x.reportTime.slice(0,-1) + '.000Z') return false;
  return x.schema === 'vision.api.status.v1' && x.scope === 'LAB_API_ONLY' &&
    x.api === 'AVAILABLE' && x.coreReadiness === 'UNKNOWN' &&
    x.observedAt === null && x.reasonCode === 'CORE_REPORT_NOT_CONNECTED' &&
    Array.isArray(x.components) && x.components.length === 0;
}
