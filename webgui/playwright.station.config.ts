import { defineConfig } from '@playwright/test';

// Build first with VITE_VISION_DEPLOYMENT=station. The actual station WSGI
// stack serves that dist directory; no Vite proxy or browser auth bypass.
export default defineConfig({
  testDir: './tests/station',
  timeout: 45000,
  use: {baseURL: 'http://127.0.0.1:18491', viewport: {width: 1280, height: 800}},
  webServer: {
    command: 'cd .. && exec env PYTHONPATH=src python3 -B tests/api/serve_station_fixture.py --port 18491 --auth-file .station-test-auth.json',
    url: 'http://127.0.0.1:18491', reuseExistingServer: false,
    gracefulShutdown: {signal: 'SIGTERM', timeout: 5000},
  },
  workers: 1,
});
