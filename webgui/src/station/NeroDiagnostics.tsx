import {Badge,Button,Field,MessageBar,MessageBarBody,Select,Table,TableBody,TableCell,TableHeader,TableHeaderCell,TableRow} from '@fluentui/react-components';
import {useEffect,useState} from 'react';
import type {StationPresentation} from './client';
import {clearNero,readNeroDiagnostics,readNeroHistory,readNeroClearHistory} from './transport';
import {sources} from './neroDiagnosticsContract';
import type {AttemptReport,ClearOperation,ClearScope,Diagnostic,DiagnosticsReport,HistoryFilter,HistoryReport,SourceFilter} from './neroDiagnosticsContract';
import {useTranslation} from '../i18n/LanguageProvider';

const timeLabel=(v:number|null)=>v===null?'—':new Date(v*1000).toLocaleString();
const scopeLabel=(scope:ClearScope)=>scope===255?'All joints':'J'+scope;
const color=(v:Diagnostic['severity'])=>v==='FAULT'?'danger':v==='WARNING'?'warning':'informative';
const outcomeColor=(v:ClearOperation['result'])=>v==='CLEARED'?'success':v==='FAILED'||v==='STILL_ACTIVE'?'danger':v==='NO_ACTIVE_FAULTS'?'informative':'warning';

export function NeroDiagnostics({station,active}:{station:StationPresentation;active:boolean}){
 const {t}=useTranslation();
 const [sample,setSample]=useState<{report:DiagnosticsReport;received:number}|null>(null);
 const [tick,setTick]=useState(()=>performance.now());
 const [scope,setScope]=useState<ClearScope>(255);
 const [intent,setIntent]=useState<{operationId:string;scope:ClearScope}|null>(null);
 const [busy,setBusy]=useState(false);
 const [outcome,setOutcome]=useState<ClearOperation|null>(null);
 const [unknown,setUnknown]=useState(false);
 const owner=station.report.instanceId;
 const identity=station.identity.username+':'+station.identity.role;
 const enabled=active&&!station.accountBusy&&station.report.coreConnection==='CONNECTED';
 useEffect(()=>{
   if(!enabled)return;
   let cancelled=false,timer:ReturnType<typeof setTimeout>;
   const clock=setInterval(()=>setTick(performance.now()),200);
   async function poll(){
     const r=await readNeroDiagnostics();
     if(cancelled)return;
     const now=performance.now();setTick(now);
     setSample(r.status==='AVAILABLE'&&r.report.instanceId===owner?{report:r.report,received:now}:null);
     timer=setTimeout(()=>void poll(),1000);
   }
   void poll();return()=>{cancelled=true;clearTimeout(timer);clearInterval(clock);};
 },[enabled,owner,identity]);
 const report=enabled&&sample?.report.instanceId===owner&&tick-sample.received<=2500?sample.report:null;
 const current=report?.current??[];
 const faults=current.filter(e=>e.severity==='FAULT').length;
 const warnings=current.filter(e=>e.severity==='WARNING').length;
 const complete=report?.coverage.length===16;
 const permitted=!!report?.clearAvailable&&station.identity.role==='operator'&&enabled&&!busy;
 function prepare(){
   if(!permitted||intent)return;
   setOutcome(null);setUnknown(false);
   setIntent({scope,operationId:crypto.randomUUID().replaceAll('-','')});
 }
 async function execute(){
   if(!permitted||!intent)return;
   const selected=intent;
   setIntent(null);setBusy(true);setUnknown(false);
   try{
     const r=await clearNero(owner,selected.operationId,selected.scope);
     if(r.status==='AVAILABLE')setOutcome(r.report.operation);
     else setUnknown(true);
   }finally{setBusy(false);}
 }
 return <section aria-label={t('NERO diagnostics')}>
  <div className="luxonis-section-heading"><div><h2>{t('NERO diagnostics')}</h2><p>{t('Live manufacturer codes · Vision severity policy')}</p></div></div>
  {!report&&<MessageBar intent="warning"><MessageBarBody>{t('NERO diagnostic report unavailable.')}</MessageBarBody></MessageBar>}
  {report&&!complete&&<MessageBar intent="warning"><MessageBarBody>{t('Diagnostic coverage incomplete; missing feedback is not a cleared fault.')}</MessageBarBody></MessageBar>}
  <div className="luxonis-facts">
   <div><span>{t('Active faults')}</span><Badge appearance="tint" color={faults?'danger':'informative'}>{report?faults:'—'}</Badge></div>
   <div><span>{t('Warnings')}</span><Badge appearance="tint" color={warnings?'warning':'informative'}>{report?warnings:'—'}</Badge></div>
   <div><span>{t('Diagnostic coverage')}</span><Badge appearance="tint" color={complete?'success':'warning'}>{report?report.coverage.length+'/16':'—'}</Badge></div>
  </div>
  <p className="fine-print">{t('Diagnostic status does not authorize motion.')}</p>
  <div className="nero-table-scroll"><Table size="small" aria-label={t('Current diagnostic codes')}>
   <TableHeader><TableRow>{['Source','Code family','HEX code','Description','Severity'].map(k=><TableHeaderCell key={k}>{t(k)}</TableHeaderCell>)}</TableRow></TableHeader>
   <TableBody>{sources.flatMap(source=>{
     const entries=current.filter(e=>e.source===source);
     const expected=source==='ARM'?['ARM_STATUS','ARM_MASK']:['DRIVE_STATUS','ARM_MASK'];
     const missing=expected.filter(f=>!report?.coverage.some(c=>c.source===source&&c.family===f));
     const known=missing.length===0;
     const rows=entries.map(e=>{
       const normal=known&&source==='ARM'&&e.family==='ARM_STATUS'&&e.code===0&&entries.length===1;
       return <TableRow key={source+e.family+e.hex}><TableCell><strong>{source}</strong></TableCell><TableCell>{e.family}</TableCell><TableCell>{e.hex}</TableCell><TableCell>{t(e.description)}</TableCell><TableCell><Badge appearance="tint" color={normal?'success':color(e.severity)}>{t(normal?'Normal':e.severity)}</Badge></TableCell></TableRow>;
     });
     // An absent fault is normal only with both independently validated code
     // families. 0x00 is the drive fault mask, not the raw enable bit.
     if(!entries.length&&known)return [<TableRow key={source}><TableCell><strong>{source}</strong></TableCell><TableCell>{source==='ARM'?'ARM_MASK':t('Joint fault mask')}</TableCell><TableCell>{source==='ARM'?'0x0000':'0x00'}</TableCell><TableCell>{t('No active fault flags')}</TableCell><TableCell><Badge appearance="tint" color="success">{t('Normal')}</Badge></TableCell></TableRow>];
     return [...rows,...missing.map(f=><TableRow key={source+f+'missing'}><TableCell><strong>{source}</strong></TableCell><TableCell>{f}</TableCell><TableCell>—</TableCell><TableCell>{t('No current diagnostic data')}</TableCell><TableCell><Badge appearance="tint" color="informative">{t('Unknown')}</Badge></TableCell></TableRow>)];
   })}</TableBody>
  </Table></div>
  <p className="fine-print">{t("Joint fault mask 0x00 means no active diagnostic faults, not that the drive is enabled or ready for motion.")}</p>
  <div className="luxonis-settings-card nero-clear-panel">
    <h3>{t('Clear joint errors')}</h3>
    <p>{t('Clearing is separate from motion reset and never enables the drives.')}</p>
    {!report?.clearAvailable&&<MessageBar intent="warning"><MessageBarBody>{t('Clear is unavailable: commissioning or admission conditions are not satisfied.')}</MessageBarBody></MessageBar>}
    <div className="nero-planned">
     <Field label={t('Clear scope')}><Select value={String(scope)} disabled={!permitted||!!intent} onChange={(_,d)=>setScope(Number(d.value) as ClearScope)}><option value="255">{t('All joints')}</option>{sources.slice(1).map((s,i)=><option key={s} value={i+1}>{s}</option>)}</Select></Field>
     <Button disabled={!permitted||!!intent} onClick={prepare}>{t('Prepare clear')}</Button>
    </div>
    {intent&&<div className="nero-clear-confirm">
      <p>{t('On the local VENTUNO console, confirm this operation ID and scope with the configured approval tool. The grant lasts 60 seconds.')}</p>
      <p><code>{intent.operationId}</code> · {t(scopeLabel(intent.scope))} ({intent.scope})</p>
      <div className="nero-planned"><Button appearance="primary" disabled={!permitted} onClick={()=>void execute()}>{t('Execute confirmed clear')}</Button><Button onClick={()=>setIntent(null)}>{t('Cancel')}</Button></div>
    </div>}
    {busy&&<p>{t('Awaiting diagnostic readback…')}</p>}
    {unknown&&<MessageBar intent="warning"><MessageBarBody>{t('Clear outcome unverified. Do not retry automatically; inspect the fault and clear history.')}</MessageBarBody></MessageBar>}
    {outcome&&<OperationSummary operation={outcome}/>}
  </div>
 </section>;
}

function OperationSummary({operation}:{operation:ClearOperation}){
 const {t}=useTranslation();
 return <div className="nero-operation-result">
  <Badge appearance="tint" color={outcomeColor(operation.result)}>{t(operation.result)}</Badge> <span>{t(operation.reason)} · {t(scopeLabel(operation.scope))}</span>
  <div className="nero-axis-results">{operation.axisResults.map((v,i)=>v==='NOT_SELECTED'?null:<span key={i}>J{i+1}: {t(v)}</span>)}</div>
 </div>;
}

export function NeroFaultHistory({station,active}:{station:StationPresentation;active:boolean}){
 const {t}=useTranslation();
 const [source,setSource]=useState<SourceFilter>('ALL');
 const [status,setStatus]=useState<HistoryFilter>('ALL');
 const [before,setBefore]=useState(0);
 const [attemptBefore,setAttemptBefore]=useState(0);
 const [history,setHistory]=useState<HistoryReport|null>(null);
 const [attempts,setAttempts]=useState<AttemptReport|null>(null);
 const owner=station.report.instanceId;
 const enabled=active&&!station.accountBusy&&station.report.coreConnection==='CONNECTED';
 useEffect(()=>{
   if(!enabled)return;
   let cancelled=false,timer:ReturnType<typeof setTimeout>;
   async function poll(){
     const [h,a]=await Promise.all([readNeroHistory(source,status,before),readNeroClearHistory(source,attemptBefore)]);
     if(cancelled)return;
     setHistory(h.status==='AVAILABLE'&&h.report.instanceId===owner?h.report:null);
     setAttempts(a.status==='AVAILABLE'&&a.report.instanceId===owner?a.report:null);
     timer=setTimeout(()=>void poll(),2000);
   }
   void poll();return()=>{cancelled=true;clearTimeout(timer);};
 },[enabled,owner,source,status,before,attemptBefore,station.identity.username,station.identity.role]);
 const h=enabled&&history?.instanceId===owner&&history.filterSource===source&&history.filterStatus===status&&history.before===before?history:null;
 const a=enabled&&attempts?.instanceId===owner&&attempts.filterSource===source&&attempts.before===attemptBefore?attempts:null;
 return <section aria-label={t('Fault history')}>
   <div className="luxonis-section-heading"><div><h2>{t('Fault history')}</h2><p>{t('Vision observations stored on NVMe; not internal NERO DTC memory.')}</p></div></div>
   <div className="nero-planned">
    <Field label={t('Source')}><Select value={source} onChange={(_,d)=>{setSource(d.value as SourceFilter);setBefore(0);setAttemptBefore(0);}}><option value="ALL">{t('All sources')}</option>{sources.map(s=><option key={s}>{s}</option>)}</Select></Field>
    <Field label={t('Status')}><Select value={status} onChange={(_,d)=>{setStatus(d.value as HistoryFilter);setBefore(0);}}><option value="ALL">{t('All statuses')}</option><option value="ACTIVE">{t('ACTIVE')}</option><option value="RESOLVED">{t('RESOLVED')}</option></Select></Field>
   </div>
   <p className="fine-print">{t('Active means last observed active, including communication gaps. Resolved means observed disappearance, not necessarily a clear command.')}</p>
   {!h?<MessageBar intent="warning"><MessageBarBody>{t('Fault history unavailable.')}</MessageBarBody></MessageBar>:<>
    <div className="nero-table-scroll"><Table size="small" aria-label={t('Fault episodes')}>
     <TableHeader><TableRow>{['First seen','Last seen','Source','HEX code','Description','Status','Last clear result'].map(k=><TableHeaderCell key={k}>{t(k)}</TableHeaderCell>)}</TableRow></TableHeader>
     <TableBody>{h.events.map(e=><TableRow key={e.id}><TableCell>{timeLabel(e.firstSeen)}</TableCell><TableCell>{timeLabel(e.lastSeen)}</TableCell><TableCell>{e.event.source}</TableCell><TableCell>{e.event.hex}<small> {e.event.family}</small></TableCell><TableCell>{t(e.event.description)} <Badge appearance="tint" color={color(e.event.severity)}>{t(e.event.severity)}</Badge></TableCell><TableCell>{t(e.status)}{e.resolvedAt&&<small> {timeLabel(e.resolvedAt)}</small>}</TableCell><TableCell>{e.lastClear?t(e.lastClear.axisResults[Number(e.event.source.slice(1))-1]??e.lastClear.result):'—'}</TableCell></TableRow>)}</TableBody>
    </Table></div>
    {!h.events.length&&<p>{t('No matching fault episodes.')}</p>}
    <div className="nero-planned"><Button disabled={!before} onClick={()=>setBefore(0)}>{t('Newest')}</Button><Button disabled={h.nextBefore===null} onClick={()=>setBefore(h.nextBefore??0)}>{t('Older')}</Button></div>
   </>}
   <h3>{t('Clear attempts')}</h3>
   {!a?<p>{t('Clear history unavailable.')}</p>:<>
    {a.events.map(e=><div className="luxonis-settings-card" key={e.id}><p className="fine-print">{timeLabel(e.startedAt)} · {e.operation.operationId}</p><OperationSummary operation={e.operation}/></div>)}
    {!a.events.length&&<p>{t('No clear attempts recorded.')}</p>}
    <div className="nero-planned"><Button disabled={!attemptBefore} onClick={()=>setAttemptBefore(0)}>{t('Newest')}</Button><Button disabled={a.nextBefore===null} onClick={()=>setAttemptBefore(a.nextBefore??0)}>{t('Older')}</Button></div>
   </>}
 </section>;
}
