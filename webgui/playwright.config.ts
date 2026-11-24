import { defineConfig } from '@playwright/test';

const integration = process.env.VISION_API_INTEGRATION === '1';
const web = {
  command: process.env.GUI_BUILD_SMOKE === '1'
    ? 'npm run preview -- --port 4173 --strictPort'
    : 'npm run dev -- --port 4173 --strictPort',
  url: 'http://127.0.0.1:4173',
  reuseExistingServer: false,
  ...(integration ? {env: {VISION_API_LAB_PORT: '18491'}} : {}),
};
export default defineConfig({
  testDir: './tests/browser',
  use: {baseURL: 'http://127.0.0.1:4173', viewport: {width:1280,height:800}},
  webServer: integration ? [
    {
      command: 'cd .. && PYTHONPATH=src python3 -B -m vision_api.server --port 18491',
      url: 'http://127.0.0.1:18491/api/v1/status',
      reuseExistingServer: false,
    },
    web,
  ] : web,
  workers: 1,
});
