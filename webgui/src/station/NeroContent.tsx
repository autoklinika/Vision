import {Badge,Tab,TabList,MessageBar,MessageBarBody,Table,TableHeader,TableHeaderCell,TableBody,TableRow,TableCell} from '@fluentui/react-components';
import {AppsRegular} from '@fluentui/react-icons';
import {useEffect,useState} from 'react';
import type {StationPresentation} from './client';
import {readNero} from './transport';
import {NeroDiagnostics,NeroFaultHistory} from './NeroDiagnostics';
import {NeroControl} from './NeroControl';
import {NERO_AGE,NERO_JOINTS,NERO_FAULTS} from './neroContract';
import type {NeroReport} from './neroContract';
import {useTranslation} from '../i18n/LanguageProvider';

const armNames:Record<number,string>={0:'Normal',1:'Emergency stop',2:'No solution',3:'Singularity',4:'Target exceeds limit',5:'Joint communication error',6:'Joint brakes not released',7:'Collision detected',8:'Teaching overspeed',9:'Joint status error',10:'Other arm error',11:'Teaching recording',12:'Teaching execution',13:'Teaching paused',14:'Main controller overtemperature',15:'Brake resistor overtemperature'};
const modeNames:Record<number,string>={0:'Standby',1:'CAN control',2:'Teaching mode',3:'WEB / Ethernet',4:'Wi-Fi control',5:'Remote control',6:'Linkage teaching',7:'Offline trajectory',8:'TCP control'};
const faultNames:Record<typeof NERO_FAULTS[number],string>={undervoltage:'Undervoltage',motor_overtemp:'Motor overtemperature',driver_overcurrent:'Driver overcurrent',driver_overtemp:'Driver overtemperature',collision_tripped:'Collision protection',driver_error:'Driver error',stall_tripped:'Stall protection'};
const toDegrees=(v:number|null|undefined)=>v==null?null:v*180/Math.PI;
const fmt=(v:number|null|undefined,d=1)=>v==null?'—':v.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const code=(v:number|undefined)=>v===undefined?'—':'0x'+v.toString(16).toUpperCase().padStart(2,'0');

export function NeroContent({station,active}:{station:StationPresentation;active:boolean}){
 const {t}=useTranslation();
 const [view,setView]=useState<"telemetry"|"diagnostics"|"history"|"control">("telemetry");
 const [visible,setVisible]=useState(!document.hidden);
 const [sample,setSample]=useState<{report:NeroReport;received:number;owner:string}|null>(null);
 const [tick,setTick]=useState(()=>performance.now());
 const [failed,setFailed]=useState(false);
 const owner=[station.report.instanceId,station.identity.username,station.identity.role].join(':');
 const enabled=active&&visible&&!station.accountBusy&&station.report.coreConnection==='CONNECTED';
 const [scope,setScope]=useState({owner,enabled});
 if(scope.owner!==owner||scope.enabled!==enabled){setScope({owner,enabled});setSample(null);setFailed(false);}
 useEffect(()=>{
   const update=()=>setVisible(!document.hidden);
   document.addEventListener('visibilitychange',update);
   return()=>document.removeEventListener('visibilitychange',update);
 },[]);
 useEffect(()=>{
   if(!enabled)return;
   let cancelled=false,last=0,timer:ReturnType<typeof setTimeout>;
   const clock=setInterval(()=>setTick(performance.now()),200);
   async function poll(){
    try{
      const r=await readNero();
      if(cancelled)return;
      if(r.status==='AVAILABLE'&&r.report.instanceId===station.report.instanceId&&r.report.capturedAt>last){
        last=r.report.capturedAt;
        const received=performance.now();
        setSample({report:r.report,received,owner});setTick(received);setFailed(false);
      }else if(r.status!=='AVAILABLE'||r.report.instanceId!==station.report.instanceId||r.report.capturedAt<last){
        setSample(null);setFailed(true);
      }
    }catch{if(!cancelled){setSample(null);setFailed(true);}}
    if(!cancelled)timer=setTimeout(()=>{void poll();},750);
   }
   void poll();return()=>{cancelled=true;clearInterval(clock);clearTimeout(timer);};
 },[enabled,owner,station.report.instanceId]);
 const current=enabled&&sample?.owner===owner&&Math.max(0,tick-sample.received)<=3000?sample:null;
 const report=current?.report;
 const age=current?Math.max(0,tick-current.received)/1000:Infinity;
 const fresh=<T extends {stamp:number}>(packet:T|null|undefined):T|null=>packet&&report&&age+report.capturedAt-packet.stamp<=NERO_AGE?packet:null;
 const arm=fresh(report?.arm),joints=fresh(report?.joints),motors=fresh(report?.motors),can=fresh(report?.can),parameters=fresh(report?.parameters);
 const graph=report?.graph??'UNKNOWN';
 const enableCount=motors?.rows.filter(m=>m.enabled===true).length??0;
 const knownCount=motors?.rows.filter(m=>m.enabled!==null).length??0;
 const driveText=knownCount!==7?t('Drive status unknown'):enableCount===7?t('All drives enabled'):enableCount===0?t('All drives disabled'):t('Drives enabled: {count}/7',{count:String(enableCount)});
 const yesNo=(v:boolean|null|undefined)=>v==null?'—':t(v?'Yes':'No');
 const armText=arm?t(armNames[arm.armStatus]??'Unknown')+' · '+code(arm.armStatus):'—';
 const formatCount=(v:number|undefined)=>v===undefined?'—':v.toLocaleString();
 const parameter=(name:'control_enabled'|'auto_enable'|'physical_hold_enabled')=>yesNo(parameters?.values[name]);
 const errorFlags=(i:number)=>{
   const m=motors?.rows[i];const entries=m?.faults?NERO_FAULTS.filter(k=>m.faults?.[k]).map(k=>t(faultNames[k])):[];
   if(arm?.angleLimit[i])entries.push(t('Joint angle limit'));
   if(arm?.communicationFault[i])entries.push(t('Joint communication error'));
   return entries;
 };
 const good=graph==='ACTIVE'&&joints!==null&&arm!==null;
 return <div className="vision-devices nero-device">
   <div className="luxonis-device-header"><div className="luxonis-device-title"><span aria-hidden="true" className="luxonis-device-icon"><AppsRegular fontSize={26}/></span><div><h2>AgileX NERO</h2><p>ROS 2 · CAN · 7 DOF</p></div></div>{report&&<p className="fine-print">{t('Last device report:')} {new Date(report.capturedAt*1000).toLocaleTimeString()}</p>}</div>
   <div className="luxonis-facts" aria-label={t('Device availability')}>
    <div><span>USB-CAN</span><Badge appearance="tint" color={report?.hardwareConnection==='USB_CAN_DETECTED'?'success':'informative'}>{t(report?.hardwareConnection==='USB_CAN_DETECTED'?'Detected':report?.hardwareConnection==='USB_CAN_NOT_DETECTED'?'Not detected':'Unknown')}</Badge></div>
    <div><span>{t('Robot feedback')}</span><Badge appearance="tint" color={good?'success':'warning'}>{t(good?'Live feedback':graph==='AMBIGUOUS'?'Ambiguous source':graph==='NO_NODE'?'Not detected':'Unverified feedback')}</Badge>{report?.node&&<small>ROS {report.node.domain}</small>}</div>
    <div><span>{t('Arm status')}</span><Badge appearance="tint" color={arm?arm.armStatus===0&&arm.errorCode===0?'success':'warning':'informative'}>{armText}</Badge></div>
    <div><span>{t('Control mode')}</span><Badge appearance="tint" color={arm?.controlMode===1?'success':arm?'warning':'informative'}>{arm?t(modeNames[arm.controlMode]??'Unknown')+' · '+code(arm.controlMode):t('Unknown')}</Badge></div>
    <div><span>{t('Drive enable feedback')}</span><Badge appearance="tint" color={knownCount===7&&enableCount===7?'success':'informative'}>{driveText}</Badge></div>
   </div>
   {(!report||report.observer==='UNAVAILABLE')&&<MessageBar intent="warning"><MessageBarBody>{t(failed?'Device report unavailable.':'No current NERO observer report.')}</MessageBarBody></MessageBar>}
   {report?.observer==='ACTIVE'&&!good&&<MessageBar intent="warning"><MessageBarBody>{t('Robot feedback is incomplete or stale. USB detection is not robot readiness.')}</MessageBarBody></MessageBar>}
   <TabList selectedValue={view} onTabSelect={(_,d)=>setView(d.value as typeof view)}>
     <Tab value="telemetry">{t('Telemetry')}</Tab>
     <Tab value="diagnostics">{t('Diagnostics')}</Tab>
     <Tab value="history">{t('Fault history')}</Tab>
     <Tab value="control">{t('Control')}</Tab>
   </TabList>
   {view==="diagnostics"&&<NeroDiagnostics key={owner} station={station} active={enabled}/>}
   {view==="history"&&<NeroFaultHistory key={owner} station={station} active={enabled}/>}
   {view==="control"&&<NeroControl key={owner+String(enabled)} station={station} active={enabled} controlMode={arm?.controlMode??null}/>}
   {view==="telemetry"&&<>
   <section aria-label={t('Joint telemetry')}>
    <div className="luxonis-section-heading"><div><h2>{t('Joint telemetry')}</h2><p>{t('Actual ROS 2 feedback · J1–J7 · read only')}</p></div></div>
    <div className="nero-table-scroll">
     <Table size="small" aria-label={t('Joint telemetry')}>
      <TableHeader><TableRow>{['Joint','Position (°)','Speed (°/s)','Torque (Nm)','Drive enabled','Voltage (V)','Current (A)','Driver (°C)','Motor (°C)','Faults'].map(k=><TableHeaderCell key={k}>{t(k)}</TableHeaderCell>)}</TableRow></TableHeader>
      <TableBody>{NERO_JOINTS.map((name,i)=>{
        const j=joints?.rows[i],m=motors?.rows[i],errors=errorFlags(i);
        return <TableRow key={name}><TableCell><strong>J{i+1}</strong></TableCell>
          <TableCell>{fmt(toDegrees(j?.positionRad),2)}</TableCell>
          <TableCell>{fmt(toDegrees(j?.velocityRadS),2)}</TableCell>
          <TableCell>{fmt(j?.torqueNm,2)}</TableCell>
          <TableCell>{m?.enabled==null?'—':<Badge appearance="tint" color={m.enabled?'success':'informative'}>{t(m.enabled?'Enabled':'Disabled')}</Badge>}</TableCell>
          <TableCell>{fmt(m?.voltageV)}</TableCell><TableCell>{fmt(m?.currentA,3)}</TableCell>
          <TableCell>{fmt(m?.driverTempC,0)}</TableCell><TableCell>{fmt(m?.motorTempC,0)}</TableCell>
          <TableCell>{errors.length?<span className="nero-fault">{errors.join(', ')}</span>:m?.faults&&arm?(m.level===0?t('None'):t('Diagnostic warning')):'—'}</TableCell></TableRow>;
      })}</TableBody>
     </Table>
    </div>
    <p className="fine-print">{t('Values expire independently after 2.5 s. Some joint models report zero current without a bus-current sensor. Velocity and torque share the joint-state timestamp.')}</p>
   </section>
   <div className="nero-detail-grid">
    <section className="luxonis-settings-card" aria-label={t('Arm diagnostics')}><h3>{t('Arm diagnostics')}</h3>
      <dl className="nero-details"><dt>{t('Control mode')}</dt><dd>{arm?t(modeNames[arm.controlMode]??'Unknown')+' · '+code(arm.controlMode):'—'}</dd><dt>{t('Arm status')}</dt><dd>{armText}</dd><dt>{t('Error code')}</dt><dd>{code(arm?.errorCode)}</dd><dt>{t('Mode feedback code')}</dt><dd>{code(arm?.modeFeedback)}</dd><dt>{t('Teaching status code')}</dt><dd>{code(arm?.teachStatus)}</dd><dt>{t('Motion status code')}</dt><dd>{code(arm?.motionStatus)}</dd><dt>{t('Trajectory number')}</dt><dd>{arm?.trajectoryNumber??'—'}</dd></dl>
    </section>
    <section className="luxonis-settings-card" aria-label={t('CAN diagnostics')}><h3>{t('CAN diagnostics')}</h3>
      <dl className="nero-details"><dt>{t('Interface')}</dt><dd>{can?.interface??'—'}</dd><dt>{t('Link up')}</dt><dd>{yesNo(can?.up)}</dd><dt>{t('CAN state')}</dt><dd>{can?.state??'—'}</dd><dt>{t('Bitrate')}</dt><dd>{can?.bitrate==null?'—':(can.bitrate/1000000).toLocaleString()+' Mbit/s'}</dd><dt>{t('RX / TX errors')}</dt><dd>{formatCount(can?.rxErrors)} / {formatCount(can?.txErrors)}</dd><dt>{t('RX / TX dropped')}</dt><dd>{formatCount(can?.rxDropped)} / {formatCount(can?.txDropped)}</dd><dt>{t('RX / TX packets')}</dt><dd>{formatCount(can?.rxPackets)} / {formatCount(can?.txPackets)}</dd></dl>
      <p className="fine-print">{t('CAN counters describe the interface since its initialization, not the readiness of the arm.')}</p>
    </section>
    <section className="luxonis-settings-card" aria-label={t('Driver configuration')}><h3>{t('Driver configuration')}</h3>
      <dl className="nero-details"><dt>{t('External control enabled')}</dt><dd>{parameter('control_enabled')}</dd><dt>{t('Automatic drive enable')}</dt><dd>{parameter('auto_enable')}</dd><dt>{t('Physical HOLD configured')}</dt><dd>{parameter('physical_hold_enabled')}</dd></dl>
      <p className="fine-print">{t('Configured driver parameters, not confirmation of HOLD or permission to move.')}</p>
    </section>
   </div>

   </>}
 </div>;
}
