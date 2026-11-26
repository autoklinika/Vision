import React from 'react';
import { createRoot } from 'react-dom/client';
const root = createRoot(document.getElementById('root')!);
if (import.meta.env.VITE_VISION_DEPLOYMENT === 'station') {
  const { LanguageProvider } = await import('./i18n/LanguageProvider');
  const { StationStartup } = await import('./station/StationStartup');
  const { FluentProvider, webLightTheme } = await import('@fluentui/react-components');
  await import('./fluent/station-workspace.css');
  root.render(<React.StrictMode><FluentProvider theme={webLightTheme} className="vision-station-root"><LanguageProvider><StationStartup/></LanguageProvider></FluentProvider></React.StrictMode>);
} else {
  await import('98.css');
  await import('./style.css');
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
