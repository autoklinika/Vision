import React from 'react';
import { createRoot } from 'react-dom/client';
import '98.css';
import './style.css';
import { createClient } from './api/client';
import { Desktop } from './shell/Desktop';
// Demo is the explicit default for this isolated shell. Any other mode fails closed.
const mode = new URLSearchParams(window.location.search).get('mode') ?? 'demo';
const client = await createClient(mode);
createRoot(document.getElementById('root')!).render(<React.StrictMode><Desktop client={client}/></React.StrictMode>);
