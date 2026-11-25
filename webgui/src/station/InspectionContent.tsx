import { useEffect, useRef, useState } from 'react';
import type { StationPresentation } from './client';
import type { InspectionBlocker, InspectionReport } from './contract';
import { readInspection, startInspection, closeInspection } from './transport';

const blockerText: Record<InspectionBlocker, string> = {
  COMPOSITION_UNCONFIGURED: 'Trusted Runtime composition is not configured.',
  NO_APPROVED_SELECTION: 'No approved ECU inspection recipe is available.',
  DEVICES_NOT_VERIFIED: 'Required device readiness is not verified.',
  SESSION_ACTIVE: 'An inspection session is already active.',
  RECOVERY_REQUIRED: 'A previous session needs backend reconciliation.',
};
const deviceLabel = {luxonis: 'Luxonis RGB-D', nero: 'AgileX NERO', moveit: 'MoveIt 2', sony: 'Sony capture'};

export function InspectionContent({station}: {station: StationPresentation}) {
  const [inspection, setInspection] = useState<InspectionReport | null>(null);
  const [selection, setSelection] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const operation = useRef(false);
  const instanceId = station.report.instanceId;
  const sessionId = station.report.sessionId;
  const connected = station.report.coreConnection === 'CONNECTED';
  const accountBusy = station.accountBusy;
  const refresh = useRef(station.refresh);
  useEffect(() => { refresh.current = station.refresh; }, [station.refresh]);
  useEffect(() => {
    let live = true, inFlight = false;
    async function read() {
      if (inFlight || operation.current || !live || !connected || accountBusy) return;
      inFlight = true;
      try {
        const result = await readInspection();
        if (!live || operation.current) return;
        if (result.status === 'AVAILABLE' && result.report.instanceId === instanceId && result.report.sessionId === sessionId) {
          setInspection(result.report);
        } else {
          setInspection(null);
          if (result.status === 'ACCESS_DENIED' || result.status === 'AVAILABLE') refresh.current();
        }
      } finally { inFlight = false; }
    }
    if (connected && !accountBusy) void read();
    const timer = window.setInterval(() => { void read(); }, 5000);
    return () => { live = false; window.clearInterval(timer); };
  }, [instanceId, sessionId, connected, accountBusy]);
  const current = connected && !accountBusy && inspection?.instanceId === instanceId && inspection.sessionId === sessionId ? inspection : null;
  const chosen = current?.selections.find(item => item.selectionId === selection);
  const isOperator = station.identity.role === 'operator';

  async function command(kind: 'start' | 'close') {
    if (operation.current || !isOperator || !current || accountBusy) return;
    if (kind === 'start' && (!current.startAllowed || !chosen)) return;
    if (kind === 'close' && (!current.closeAllowed || !current.sessionId)) return;
    if (kind === 'close' && !window.confirm('Close this inspection session? No device movement will be requested.')) return;
    operation.current = true;
    setBusy(true);
    setMessage('');
    try {
      const result = kind === 'start'
        ? await startInspection(instanceId, chosen!.selectionId, current.intentToken)
        : await closeInspection(instanceId, current.sessionId!);
      const consistent = result.status === 'AVAILABLE' && result.report.instanceId === instanceId &&
        result.report.coreConnection === 'CONNECTED' &&
        (kind === 'start' ? result.report.state === 'SESSION_ACTIVE' : result.report.state === 'NO_ACTIVE_SESSION');
      setMessage(consistent
        ? kind === 'start' ? 'Session created. Review the verified S01/S02 results in the Core report.' : 'Session closed.'
        : result.status === 'INSPECTION_REJECTED' ? 'Core rejected the request. Review the current blockers.'
        : result.status === 'OPERATOR_REQUIRED' ? 'Inspection operator permission is required.'
        : 'Outcome not confirmed. Refresh the station before issuing another request.');
      setInspection(null);
      refresh.current();
    } finally { operation.current = false; setBusy(false); }
  }

  return <section aria-label="Inspection orchestration">
    <h3>Inspection readiness</h3>
    {current ? <>
      <div className="sunken-panel report"><table>
        <thead><tr><th scope="col">Device</th><th scope="col">Availability</th><th scope="col">Readiness</th></tr></thead>
        <tbody>{current.devices.map(d => <tr key={d.device}><th scope="row">{deviceLabel[d.device]}</th><td>{d.availability}</td><td>{d.readiness}</td></tr>)}</tbody>
      </table></div>
      <p className="fine-print">Live service availability is not physical readiness. Last report: {current.capturedAt} UTC.</p>
      {current.blockers.length > 0 && <ul>{current.blockers.map(b => <li key={b}>{blockerText[b]}</li>)}</ul>}
      {isOperator ? <>
        <label htmlFor="inspection-selection">Declared ECU and recipe</label>{' '}
        <select id="inspection-selection" value={chosen?.selectionId ?? ''} onChange={e => setSelection(e.target.value)} disabled={busy || current.sessionId !== null || current.selections.length === 0}>
          <option value="">Select an approved recipe</option>
          {current.selections.map(item => <option value={item.selectionId} key={item.selectionId}>{item.family} / {item.variant} / {item.revision} / {item.physicalState} / {item.recipe}</option>)}
        </select>
        <div className="startup-actions"><button disabled={!current.startAllowed || !chosen || busy} onClick={() => { void command('start'); }}>Start inspection session</button>
        <button disabled={!current.closeAllowed || busy} onClick={() => { void command('close'); }}>Close session</button></div>
      </> : <p>Read-only account. Starting or closing a session requires operator permission.</p>}
    </> : <p>Inspection readiness report unavailable. No session command is enabled.</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
