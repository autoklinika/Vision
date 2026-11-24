import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { copyFileSync } from 'node:fs';
export default defineConfig({
  plugins: [react(), {
    name: 'public-notices-only',
    closeBundle() { copyFileSync('public/THIRD_PARTY_NOTICES.txt', 'dist/THIRD_PARTY_NOTICES.txt'); },
    apply: 'build',
  }],
  build: { copyPublicDir: false },
  test: { include: ['tests/*.test.ts'] },
});
