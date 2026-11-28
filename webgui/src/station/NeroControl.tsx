import {Badge,Button,Field,Input,MessageBar,MessageBarBody,Slider,Select} from '@fluentui/react-components';
import {useEffect,useRef,useState} from 'react';
import type {StationPresentation} from './client';
import {readNeroTcp} from './transport';
import {keyboardMap} from './neroTcpContract';
import type {TcpReport,TcpIntent,TcpFrame} from './neroTcpContract';
import {useTranslation} from '../i18n/LanguageProvider';
import {useNeroManual} from './useNeroManual';
import {manualSpeedLimits,displayedManualSpeed} from './neroManualContract';
import {NeroJointPreflight} from './NeroJointPreflight';

const controls=[
 {axis:'X',label:'X',minus:'ArrowDown',plus:'ArrowUp',minusKey:'↓',plusKey:'↑'},
 {axis:'Y',label:'Y',minus:'ArrowLeft',plus:'ArrowRight',minusKey:'←',plusKey:'→'},
 {axis:'Z',label:'Z',minus:'PageDown',plus:'PageUp',minusKey:'PgDn',plusKey:'PgUp'},
 {axis:'ROLL',label:'Roll',minus:'KeyQ',plus:'KeyE',minusKey:'Q',plusKey:'E'},
 {axis:'PITCH',label:'Pitch',minus:'KeyR',plus:'KeyF',minusKey:'R',plusKey:'F'},
 {axis:'YAW',label:'Yaw',minus:'KeyT',plus:'KeyG',minusKey:'T',plusKey:'G'},
] as const;
const presets=[{name:'Precision',linear:5,angular:2},{name:'Normal speed',linear:25,angular:10},{name:'Fast',linear:50,angular:20}];

export function NeroControl({station,active}:{station:StationPresentation;active:boolean}){
 const {t}=useTranslation();
 const owner=station.report.instanceId;
 const [sample,setSample]=useState<{report:TcpReport;received:number}|null>(null);
 const [tick,setTick]=useState(()=>performance.now());
 const [requestedLinear,setLinear]=useState(10);
 const [requestedAngular,setAngular]=useState(5);
 const [frame,setFrame]=useState<TcpFrame>('BASE');
 const [practice,setPractice]=useState(false);
 const [key,setKey]=useState<string|null>(null);
 const held=useRef<string|null>(null);
 const keyboard=useRef<HTMLDivElement>(null);
 const enabled=active&&!station.accountBusy&&station.report.coreConnection==='CONNECTED';
 const manual=useNeroManual(owner,enabled&&station.identity.role==='operator');
 const [physical,setPhysical]=useState(false);
 const stop=()=>{held.current=null;setKey(null);manual.release();};
 const reviewOnly=manual.status?.reason==='REVIEW_ONLY';
 const {linearMax,angularMax}=manualSpeedLimits(manual.status);
 const {linear,angular}=displayedManualSpeed(requestedLinear,requestedAngular,manual.status);
 useEffect(()=>{
  // A changed owner envelope must release input, not silently retarget a
  // held command. Displayed and submitted values use the same upper bounds.
  if(held.current!==null)stop();
  setLinear(v=>Math.min(v,linearMax));
  setAngular(v=>Math.min(v,angularMax));
 },[linearMax,angularMax]);

 useEffect(()=>{if(!manual.hasSession){setPhysical(false);held.current=null;setKey(null);}},[manual.hasSession]);
 useEffect(()=>{
  if(!enabled)return;
  let cancelled=false,timer:ReturnType<typeof setTimeout>;
  const clock=setInterval(()=>setTick(performance.now()),200);
  async function poll(){
   const result=await readNeroTcp();
   if(cancelled)return;
   const now=performance.now();setTick(now);
   setSample(result.status==='AVAILABLE'&&result.report.instanceId===owner?{report:result.report,received:now}:null);
   timer=setTimeout(()=>void poll(),750);
  }
  void poll();return()=>{cancelled=true;clearInterval(clock);clearTimeout(timer);};
 },[owner,enabled]);
 useEffect(()=>{
  if(!active||!(practice||physical))return;
  const reset=()=>{held.current=null;setKey(null);manual.release();};
  const hide=()=>{if(document.hidden)reset();};
  window.addEventListener('blur',reset);document.addEventListener('visibilitychange',hide);
  return()=>{window.removeEventListener('blur',reset);document.removeEventListener('visibilitychange',hide);};
 },[active,practice,physical]);
 const report=enabled&&sample?.report.instanceId===owner&&tick-sample.received<=2500?sample.report:null;
 const drives=report?.driveEnabled??Array<boolean|null>(7).fill(null);
 const check=report?.jointCheck??null;
 const known=drives.every(x=>x!==null);
 const enabledCount=drives.filter(x=>x===true).length;
 const available=!!report&&check?.state==='WITHIN_LIMITS'&&station.identity.role==='operator';
 const trial=(practice||physical&&manual.hasSession&&!!manual.status?.jogAvailable)&&active;
 const current:TcpIntent|null=trial&&key?keyboardMap[key]??null:null;
 const start=(code:string)=>{
  if(!trial||!keyboardMap[code]||held.current)return;
  if(physical&&!manual.start({frame,linearMmS:linear,angularDegS:angular},keyboardMap[code]))return;
  held.current=code;setKey(code);
 };
 function togglePractice(){
  stop();setPhysical(false);setPractice(!practice);
  if(!practice)requestAnimationFrame(()=>keyboard.current?.focus());
 }
 const label=(intent:TcpIntent)=>intent.axis+' '+(intent.direction===1?'+':'−');
 return <section aria-label={t('TCP control')} className="nero-tcp-control">
   <div className="luxonis-section-heading"><div><h2>{t('TCP control')}</h2><p>MoveIt Servo · Cartesian teleoperation</p></div><Badge appearance="tint" color={manual.status?.pipelineReady?'informative':'warning'}>{t(reviewOnly?'REVIEW_ONLY':manual.status?.state??'NOT_COMMISSIONED')}</Badge></div>
   {(!manual.status||reviewOnly)&&<MessageBar intent="warning"><MessageBarBody>{t('Physical control is not commissioned. The keyboard test does not send robot commands.')}</MessageBarBody></MessageBar>}
   {manual.status&&!reviewOnly&&<p className="fine-print">{t('Local maintenance session')} · {t(manual.status.reason)}</p>}
   {manual.notice&&<MessageBar intent="warning"><MessageBarBody>{t(manual.notice)}</MessageBarBody></MessageBar>}
   <NeroJointPreflight check={check}/>
   <section className="luxonis-settings-card">
     <h3>{t('Drives')}</h3>
     <div className="nero-tcp-drive-row">
       <div><Badge appearance="tint" color={known&&enabledCount===7?'success':'informative'}>{known?enabledCount+'/7 '+t('Enabled'):t('Drive status unknown')}</Badge><p className="fine-print">{t('Actual drive enable feedback')}</p></div>
       <Button appearance="primary" disabled={!available||!manual.status?.enableAvailable||manual.busy||manual.hasSession||!!manual.approval} onClick={manual.prepare}>{t('Enable drives')}</Button>
     </div>
     {manual.approval&&<div className="nero-clear-confirm"><p>{t('Confirm the manual session on the local VENTUNO console using the one-use approval tool. Then confirm here.')}</p><p><code>{manual.approval}</code></p><div className="nero-planned"><Button appearance="primary" disabled={manual.busy} onClick={()=>void manual.enable()}>{t('Confirm drive enable')}</Button><Button onClick={manual.cancelApproval}>{t('Cancel')}</Button></div></div>}
     {manual.hasSession&&<div className="nero-planned"><Button onClick={()=>{stop();setPhysical(false);manual.close();}}>{t('Close manual session')}</Button></div>}
     <div className="nero-tcp-axis-status">{drives.map((v,i)=><Badge key={i} appearance="tint" color={v===true?'success':'informative'}>J{i+1} · {t(v===null?'Unknown':v?'Enabled':'Disabled')}</Badge>)}</div>
   </section>
   <section className="luxonis-settings-card">
     <h3>{t('TCP speed declaration')}</h3>
     <div className="nero-tcp-speed-grid">
       <Field label={t('Linear speed (mm/s)')}>
         <div className="nero-tcp-speed"><Slider aria-label={t('Linear speed (mm/s)')} min={1} max={linearMax} disabled={linearMax===1} value={linear} onChange={(_,d)=>{stop();setLinear(d.value);}}/><Input aria-label={t('Linear speed value')} type="number" min={1} max={linearMax} value={String(linear)} onChange={(_,d)=>{const n=Number(d.value);if(Number.isInteger(n)&&n>=1&&n<=linearMax){stop();setLinear(n);}}}/></div>
       </Field>
       <Field label={t('Angular speed (°/s)')}>
         <div className="nero-tcp-speed"><Slider aria-label={t('Angular speed (°/s)')} min={1} max={angularMax} disabled={angularMax===1} value={angular} onChange={(_,d)=>{stop();setAngular(d.value);}}/><Input aria-label={t('Angular speed value')} type="number" min={1} max={angularMax} value={String(angular)} onChange={(_,d)=>{const n=Number(d.value);if(Number.isInteger(n)&&n>=1&&n<=angularMax){stop();setAngular(n);}}}/></div>
       </Field>
     </div>
     <div className="nero-planned">{presets.map(p=><Button key={p.name} disabled={p.linear>linearMax||p.angular>angularMax} appearance={linear===p.linear&&angular===p.angular?'primary':'secondary'} onClick={()=>{stop();setLinear(p.linear);setAngular(p.angular);}}>{t(p.name)}</Button>)}</div>
     <p className="fine-print">{manual.status?t(reviewOnly?'Review speed envelope':'Accepted speed envelope')+': '+manual.status.linearMax+' mm/s · '+manual.status.angularMax+' °/s':t('Draft speed limits for commissioning; declaration is not applied to the real robot.')}</p>
     <dl className="nero-details"><dt>{t('Actual linear TCP speed')}</dt><dd>— mm/s</dd><dt>{t('Actual angular TCP speed')}</dt><dd>— °/s</dd></dl>
   </section>
   <section className="luxonis-settings-card">
     <div className="nero-tcp-drive-row"><h3>{t('Cartesian keyboard control')}</h3><Button appearance={practice?'primary':'secondary'} onClick={togglePractice}>{t(practice?'End keyboard test':'Test keyboard')}</Button>{manual.hasSession&&<Button appearance={physical?'primary':'secondary'} disabled={!physical&&!manual.status?.jogAvailable} onClick={()=>{stop();setPractice(false);setPhysical(!physical);if(!physical)requestAnimationFrame(()=>keyboard.current?.focus());}}>{t(physical?'End manual keyboard':'Start manual keyboard')}</Button>}</div>
     <Field label={t('Reference frame')}><Select value={frame} onChange={(_,d)=>{stop();setFrame(d.value as TcpFrame);}}><option value="BASE">BASE · {t('Robot base')}</option><option value="TOOL">TOOL · TCP</option></Select></Field>
     <p className="fine-print">{t('Keyboard test is local only. Focus the test area; release the key, leave the area or press Esc to clear the preview.')}</p>
     <div ref={keyboard} role="group" aria-label={t('Keyboard test area')} tabIndex={practice||physical?0:-1} className="nero-tcp-keyboard"
       onKeyDown={e=>{if(!trial||e.altKey||e.ctrlKey||e.metaKey||e.shiftKey)return;if(e.code==='Escape'||e.code==='Space'){e.preventDefault();if(physical){manual.hold();setPhysical(false);}stop();return;}if(keyboardMap[e.code]){e.preventDefault();if(!e.repeat)start(e.code);}}}
       onKeyUp={e=>{if(held.current===e.code)stop();}}
       onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))stop();}}>
       <div className="nero-tcp-keys">{controls.map(c=><div key={c.axis} className="nero-tcp-key-row">
         <Button appearance={key===c.minus?'primary':'secondary'} disabled={!trial} aria-label={c.label+' −'} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);start(c.minus);}} onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={stop}>{c.minusKey} · −</Button>
         <strong>{c.label}</strong>
         <Button appearance={key===c.plus?'primary':'secondary'} disabled={!trial} aria-label={c.label+' +'} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);start(c.plus);}} onPointerUp={stop} onPointerCancel={stop} onLostPointerCapture={stop}>{c.plusKey} · +</Button>
       </div>)}</div>
       <div role="status" className="nero-tcp-intent"><Badge appearance="tint" color={current?'brand':'informative'}>{current?label(current):t('No input')}</Badge>{current&&<span>{frame} · {['X','Y','Z'].includes(current.axis)?linear+' mm/s':angular+' °/s'}</span>}</div>
     </div>
     <div className="nero-tcp-stop"><Button appearance="secondary" disabled={!manual.hasSession||!manual.status?.holdAvailable} onClick={()=>{manual.hold();stop();setPhysical(false);}}>{t('STOP / HOLD')}</Button><span className="fine-print">{t('Physical HOLD remains on Stream Deck.')}</span></div>
   </section>
 </section>;
}
