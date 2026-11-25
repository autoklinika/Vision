import {defineConfig} from '@playwright/test';

// Disposable operator, separate Core, library and HTTP port. Never use
// operational credentials, socket or station storage.
export default defineConfig({
  testDir:'./tests/editor',
  timeout:45000,
  use:{baseURL:'http://127.0.0.1:18492',viewport:{width:1280,height:800}},
  webServer:{
    command:'cd .. && exec env PYTHONPATH=src python3 -B tests/api/serve_station_fixture.py --port 18492 --auth-file .station-test-auth.json --editor-operator',
    url:'http://127.0.0.1:18492',reuseExistingServer:false,
    gracefulShutdown:{signal:'SIGTERM',timeout:5000},
  },
  workers:1,
});
