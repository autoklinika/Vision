import React from 'react';
import { createRoot } from 'react-dom/client';
import '98.css';
import './style.css';
import { createClient } from './api/client';
import { Startup } from './startup/Startup';
import { readClientReport } from './startup/report';
// Demo is the explicit default for this isolated shell. Any other mode fails closed.
const modes = new URLSearchParams(window.location.search).getAll('mode');
const mode = modes.length === 0 ? 'demo' : modes.length === 1 ? modes[0] : 'invalid';
const client = await createClient(mode);
const report = readClientReport(client);
createRoot(document.getElementById('root')!).render(<React.StrictMode><Startup client={client} report={report}/></React.StrictMode>);
