import { useTranslation } from '../i18n/LanguageProvider';
import { Badge, Button, Label, MessageBar, MessageBarBody, MessageBarTitle, Select, Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow } from '@fluentui/react-components';
import { useEffect, useRef, useState } from 'react';
import type { StationPresentation } from './client';
import type { DeviceReport, InspectionBlocker, InspectionReport } from './contract';
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
  const {t}=useTranslation();
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
    if (kind === 'close' && !window.confirm(t('Close this inspection session? No device movement will be requested.'))) return;
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

  const labels = {ACTIVE:'Active',INACTIVE:'Inactive',READY:'Ready',NOT_READY:'Not ready',UNKNOWN:'Unknown'} as const;
  const statusBadge = (value: DeviceReport['availability'] | DeviceReport['readiness']) =>
    <Badge appearance="tint" color={value==='ACTIVE'||value==='READY'?'success':value==='NOT_READY'||value==='INACTIVE'?'warning':'informative'} title={value} data-reported-state={value}>{t(labels[value])}</Badge>;
  return <section className="station-device-section" aria-label={t("Inspection orchestration")}>
    <div className="station-section-heading"><div><h2>{t("Devices and services")}</h2><span>{t("Monitored service availability does not establish physical connectivity or device readiness.")}</span></div>
      {current&&<div className="station-device-report-meta"><Badge appearance="tint" color={current.startAllowed?'success':'warning'}>{t(current.startAllowed?"Core permits session start":"Session start blocked")}</Badge><span className="station-report-time">{t("Last report:")} <time dateTime={current.capturedAt}>{current.capturedAt}</time></span></div>}
    </div>
    {current ? <>
      <div className="station-device-table">
        <Table aria-label={t("Devices and services")}>
          <TableHeader><TableRow><TableHeaderCell>{t("Device")}</TableHeaderCell><TableHeaderCell>{t("Availability")}</TableHeaderCell><TableHeaderCell>{t("Readiness")}</TableHeaderCell><TableHeaderCell>{t("Last observation (UTC)")}</TableHeaderCell></TableRow></TableHeader>
          <TableBody>{current.devices.map(d=><TableRow key={d.device} data-device={d.device}>
            <TableCell className="station-device-name">{t(deviceLabel[d.device])}</TableCell>
            <TableCell>{statusBadge(d.availability)}</TableCell>
            <TableCell>{statusBadge(d.readiness)}</TableCell>
            <TableCell><time dateTime={d.observedAt}>{d.observedAt}</time></TableCell>
          </TableRow>)}</TableBody>
        </Table>
      </div>
      <div className="station-readiness-heading"><h3>{t("Inspection readiness")}</h3></div>
      {current.blockers.length>0&&<MessageBar intent="warning" className="station-blocker-message"><MessageBarBody><MessageBarTitle>{t("Conditions reported by Core")}</MessageBarTitle><ul className="station-blocker-list">{current.blockers.map(b=><li key={b}>{t(blockerText[b])}</li>)}</ul></MessageBarBody></MessageBar>}
      {isOperator ? <div className="station-inspection-actions">
        <div className="station-inspection-selection">
          <Label htmlFor="inspection-selection">{t("Declared ECU and recipe")}</Label>
          <Select id="inspection-selection" value={chosen?.selectionId??''} onChange={e=>setSelection(e.target.value)} disabled={busy||current.sessionId!==null||current.selections.length===0}>
            <option value="">{t("Select an approved recipe")}</option>
            {current.selections.map(item=><option value={item.selectionId} key={item.selectionId}>{item.family} / {item.variant} / {item.revision} / {item.physicalState} / {item.recipe}</option>)}
          </Select>
        </div>
        <div className="station-inspection-buttons">
          <Button appearance="primary" disabled={!current.startAllowed||!chosen||busy} onClick={()=>{void command('start');}}>{t("Start inspection session")}</Button>
          <Button disabled={!current.closeAllowed||busy} onClick={()=>{void command('close');}}>{t("Close session")}</Button>
        </div>
      </div> : <p className="fine-print">{t("Read-only account. Starting or closing a session requires operator permission.")}</p>}
    </> : <MessageBar intent="warning"><MessageBarBody>{t("Inspection readiness report unavailable. No session command is enabled.")}</MessageBarBody></MessageBar>}
    {message&&<p role="status">{t(message)}</p>}
  </section>;
}
