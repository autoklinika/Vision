import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { copyFileSync } from 'node:fs';
// Explicit lab-only same-origin proxy. No arbitrary URL/host configuration.
const apiPort = process.env.VISION_API_LAB_PORT;
if (apiPort !== undefined && (!/^[1-9][0-9]{0,4}$/.test(apiPort) || Number(apiPort) > 65535)) {
  throw new Error('VISION_API_LAB_PORT must be a valid loopback port');
}
const proxy = apiPort === undefined ? undefined : {
  '^/api/v1/status
  plugins: [react(), {
    name: 'public-notices-only',
    closeBundle() { copyFileSync('public/THIRD_PARTY_NOTICES.txt', 'dist/THIRD_PARTY_NOTICES.txt'); },
    apply: 'build',
  }],
  server: { host: '127.0.0.1', cors: false, proxy },
  preview: { host: '127.0.0.1', cors: false, proxy },
  build: { copyPublicDir: false },
  test: { include: ['tests/*.test.ts'] },
});
: { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
};
export default defineConfig({
  plugins: [react(), {
    name: 'public-notices-only',
    closeBundle() { copyFileSync('public/THIRD_PARTY_NOTICES.txt', 'dist/THIRD_PARTY_NOTICES.txt'); },
    apply: 'build',
  }],
  build: { copyPublicDir: false },
  test: { include: ['tests/*.test.ts'] },
});
