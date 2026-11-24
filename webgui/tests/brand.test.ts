import { afterEach, expect, it, vi } from 'vitest';
import { loadBrand, InsecureBrandContext } from '../src/startup/brand';
import reference from '../src/startup/brand-reference.json';

afterEach(() => vi.unstubAllGlobals());
function setup() {
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('location', new URL('https://client.test/'));
}
it('rejects insecure context before any fetch or digest', async () => {
  vi.stubGlobal('isSecureContext', false);
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  await expect(loadBrand(new AbortController().signal)).rejects.toBeInstanceOf(InsecureBrandContext);
  expect(fetch).not.toHaveBeenCalled();
});
it('does not trust substituted hashes in manifest', async () => {
  setup();
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...reference, durationMs: 3490, logoSha256: '0'.repeat(64) })));
  vi.stubGlobal('fetch', fetch);
  await expect(loadBrand(new AbortController().signal)).rejects.toThrow('Unverified');
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('bounds streamed reads and forbids redirects/cross-origin requests', async () => {
  setup();
  const fetch = vi.fn().mockResolvedValue(new Response('x'.repeat(2049)));
  vi.stubGlobal('fetch', fetch);
  await expect(loadBrand(new AbortController().signal)).rejects.toThrow('Oversized');
  expect(fetch).toHaveBeenCalledWith(new URL('https://client.test/local-brand/manifest.json'), expect.objectContaining({ redirect: 'error', mode: 'same-origin' }));
});
