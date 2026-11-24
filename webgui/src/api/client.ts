import type { ReadOnlyVisionClient } from './types';
import { realAdapter } from './realAdapter';
/** Explicit selection only. Unknown modes fail closed; never fall back to demo. */
export async function createClient(mode: string): Promise<ReadOnlyVisionClient> {
  if (mode === 'demo') return (await import('../demo/adapter')).demoAdapter;
  return realAdapter;
}
