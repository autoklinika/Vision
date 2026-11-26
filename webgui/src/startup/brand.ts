import reference from './brand-reference.json' with { type: 'json' };
export const originalSha256 = reference.sourceSha256;
export const introDuration = 3490;
export type Brand = { intro: string; logo: string };
export class InsecureBrandContext extends Error {}

async function readAsset(name: string, limit: number, signal: AbortSignal, directory: 'local-brand' | 'assets' = 'local-brand') {
  const url = new URL(`${import.meta.env.BASE_URL}${directory}/${name}`, location.href);
  if (url.origin !== location.origin) throw new Error('Cross-origin asset');
  const response = await fetch(url, { signal, cache: 'no-store', redirect: 'error', mode: 'same-origin' });
  if (!response.ok || !response.body) throw new Error('Missing local asset');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > limit) throw new Error('Oversized local asset');
      chunks.push(value);
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}

async function verifiedBlob(name: string, hash: string, type: string, signal: AbortSignal, directory: 'local-brand' | 'assets' = 'local-brand') {
  const bytes = await readAsset(name, 300_000, signal, directory);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const actual = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
  if (actual !== hash) throw new Error('Corrupt local asset');
  return new Blob([bytes], { type });
}

/** Manifest is metadata, never a trust anchor. No runtime verification override. */
export async function loadBrand(signal: AbortSignal): Promise<Brand> {
  if (!globalThis.isSecureContext || !crypto.subtle) throw new InsecureBrandContext('Secure context required');
  const manifest = JSON.parse(new TextDecoder().decode(await readAsset('manifest.json', 2048, signal)));
  if (manifest.sourceSha256 !== reference.sourceSha256 || manifest.durationMs !== introDuration ||
      manifest.introSha256 !== reference.introSha256 || manifest.logoSha256 !== reference.logoSha256) throw new Error('Unverified local brand');
  const [intro, logo] = await Promise.all([
    verifiedBlob('intro.gif', reference.introSha256, 'image/gif', signal),
    verifiedBlob('logo.png', reference.logoSha256, 'image/png', signal),
  ]);
  signal.throwIfAborted();
  return { intro: URL.createObjectURL(intro), logo: URL.createObjectURL(logo) };
}

export function releaseBrand(brand: Brand) {
  URL.revokeObjectURL(brand.intro);
  URL.revokeObjectURL(brand.logo);
}

/** Optional private station logo, installed locally after the standard build.
 * Verify the exact original-derived PNG independently; never ship a substitute.
 */
export async function loadStationLogo(signal: AbortSignal): Promise<string> {
  if (!globalThis.isSecureContext || !crypto.subtle) throw new InsecureBrandContext('Secure context required');
  const logo = await verifiedBlob('vision-logo-65f1e7f2.png', reference.logoSha256, 'image/png', signal, 'assets');
  signal.throwIfAborted();
  return URL.createObjectURL(logo);
}
