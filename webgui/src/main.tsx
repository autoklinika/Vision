import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
const root = createRoot(document.getElementById('root')!);
if (import.meta.env.VITE_VISION_DEPLOYMENT === 'station') {
  const { StationStartup } = await import('./station/StationStartup');
  root.render(<React.StrictMode><StationStartup/></React.StrictMode>);
} else {
  // The isolated LAB shell keeps its explicit demo/default behavior.
  const { createClient } = await import('./api/client');
  const { Startup } = await import('./startup/Startup');
  const { readClientReport } = await import('./startup/report');
  const modes = new URLSearchParams(window.location.search).getAll('mode');
  const mode = modes.length === 0 ? 'demo' : modes.length === 1 ? modes[0] : 'invalid';
  const client = await createClient(mode);
  const report = readClientReport(client);
  root.render(<React.StrictMode><Startup client={client} report={report}/></React.StrictMode>);
}
