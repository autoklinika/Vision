import {Badge,Button,Select,Switch,MessageBar,MessageBarBody,Table,TableHeader,TableHeaderCell,TableBody,TableRow,TableCell} from '@fluentui/react-components';
import {VideoRegular,PlayRegular,StopRegular,ImageRegular} from '@fluentui/react-icons';
import {useEffect,useRef,useState} from 'react';
import type {StationPresentation} from './client';
import {readLuxonis,setLuxonisIR} from './transport';
import {parameterGroups,level} from './luxonisContract';
import type {LuxonisReport,PreviewFrame,IRResult,IRChannel} from './luxonisContract';
import {useTranslation} from '../i18n/LanguageProvider';

type Timed={report:LuxonisReport;received:number;owner:string};
const profiles={rgbd_lab:'Saved RGB-D profile',stereo800_lab:'Saved stereo 800p diagnostic profile'} as const;

export function DevicesContent({station,active}:{station:StationPresentation;active:boolean}){
  const {t}=useTranslation();
  const [visible,setVisible]=useState(!document.hidden);
  const [preview,setPreview]=useState(false);
  const [sample,setSample]=useState<Timed|null>(null);
  const [failure,setFailure]=useState(false);
  const [tick,setTick]=useState(()=>performance.now());
  const [badFrames,setBadFrames]=useState<{rgb:number|null;depth:number|null}>({rgb:null,depth:null});
  const [irBusy,setIrBusy]=useState(false);
  const irRunning=useRef(false);
  const [irReply,setIrReply]=useState<{report:IRResult;received:number;owner:string}|null>(null);
  const [irMessage,setIrMessage]=useState('');
  const [selected,setSelected]=useState<keyof typeof profiles|'live'|null>(null);
  const owner=[station.report.instanceId,station.identity.username,station.identity.role].join(':');
  const enabled=active&&visible&&!station.accountBusy&&station.report.coreConnection==='CONNECTED';
  const permitted=enabled&&station.identity.role==='operator'&&station.report.state==='NO_ACTIVE_SESSION';
  const [scope,setScope]=useState({enabled,permitted,owner});
  if(scope.enabled!==enabled||scope.permitted!==permitted||scope.owner!==owner){
    setScope({enabled,permitted,owner});
    setSample(null);setFailure(false);setBadFrames({rgb:null,depth:null});
    setIrReply(null);setIrMessage('');
    if(!permitted||scope.owner!==owner)setPreview(false);
  }
  const viewing=preview&&permitted;
  useEffect(()=>{
    const update=()=>setVisible(!document.hidden);
    document.addEventListener('visibilitychange',update);
    return()=>document.removeEventListener('visibilitychange',update);
  },[]);
  useEffect(()=>{
    if(!enabled)return;
    let cancelled=false,timer:ReturnType<typeof setTimeout>,lastCaptured=0;
    const clock=setInterval(()=>setTick(performance.now()),250);
    async function poll(){
      try{
        const result=await readLuxonis(viewing);
        if(cancelled)return;
        if(result.status==='AVAILABLE'&&result.report.instanceId===station.report.instanceId){
          if(result.report.capturedAt>lastCaptured){
            lastCaptured=result.report.capturedAt;
            const received=performance.now();setSample({report:result.report,received,owner});setTick(received);setFailure(false);
          }else if(result.report.capturedAt<lastCaptured){
            setSample(null);setFailure(true);
          } // A replayed identical observation never resets display age.
        }else{setSample(null);setFailure(true);}
      }catch{if(!cancelled){setSample(null);setFailure(true);}}
      if(!cancelled)timer=setTimeout(()=>{void poll();},viewing?750:2000);
    }
    void poll();
    return()=>{cancelled=true;clearTimeout(timer);clearInterval(clock);};
  },[enabled,viewing,owner,station.report.instanceId]);
  const current=enabled&&sample?.owner===owner&&Math.max(0,tick-sample.received)<=4500?sample:null;
  const report=current?.report;
  const elapsed=current?Math.max(0,tick-current.received)/1000:Infinity;
  const liveFrame=(key:'rgb'|'depth'):PreviewFrame|null=>{
    const f=report?.frames[key];
    return viewing&&f&&report&&badFrames[key]!==f.stamp&&elapsed+report.capturedAt-f.stamp<=2.5?f:null;
  };
  const frameRgb=liveFrame('rgb'),frameDepth=liveFrame('depth');
  const available=report?.hardwareConnection==='USB_DETECTED';
  const graph=report?.graph??'UNKNOWN';
  const source=selected==='live'||(selected&&report?.profiles[selected])?selected:
    graph==='ACTIVE'?'live':report?.profiles.rgbd_lab?'rgbd_lab':report?.profiles.stereo800_lab?'stereo800_lab':'live';
  const data=source==='live'?(report?.settingsAt!==null&&report?.settingsAt!==undefined&&elapsed+report.capturedAt-report.settingsAt<=8?report.settings:{}):report?.profiles[source]??{};
  const liveSettings=report?.settingsAt!==null&&report?.settingsAt!==undefined&&elapsed+report.capturedAt-report.settingsAt<=8?report.settings:{};
  const newerReply=report?.irControlAvailable&&irReply?.owner===owner&&
    tick-irReply.received<=8000&&irReply.report.capturedAt>(report.settingsAt??0)?irReply.report:null;
  const dot=newerReply?.dot??liveSettings['driver.r_laser_dot_intensity'];
  const flood=newerReply?.flood??liveSettings['driver.r_floodlight_intensity'];
  const known=liveSettings['driver.i_enable_ir']===true&&level(dot)&&level(flood);
  const canIR=permitted&&report?.irControlAvailable===true&&known&&!irBusy;
  async function toggleIR(channel:IRChannel,value:boolean){
    if(!canIR||irRunning.current)return;
    irRunning.current=true;setIrBusy(true);setIrMessage('');
    try{
      const result=await setLuxonisIR(station.report.instanceId,channel,value);
      if(result.status==='AVAILABLE'){
        setIrReply({report:result.report,received:performance.now(),owner});
        setIrMessage('IR change confirmed by driver.');
      }else{
        setIrReply(null);
        setIrMessage(result.status==='IR_REJECTED'||result.status==='OPERATOR_REQUIRED'?'IR change rejected by Core.':'IR change not confirmed. Check current values before retrying.');
      }
    }catch{setIrReply(null);setIrMessage('IR change not confirmed. Check current values before retrying.');}
    finally{irRunning.current=false;setIrBusy(false);}
  }
  const irLevel=(value:unknown)=>known&&level(value)?Math.round(value*100)+'%':'—';
  const describe=(stream:'rgb'|'depth')=>t(report?.endpoints[stream]==='AVAILABLE'?'Topic available':report?.endpoints[stream]==='UNAVAILABLE'?'Topic unavailable':report?.endpoints[stream]==='AMBIGUOUS'?'Ambiguous source':'Unknown');
  const badgeColor=(v:boolean)=>v?'success':'informative';
  const renderPreview=(key:'rgb'|'depth',frame:PreviewFrame|null)=>{
    const label=key==='rgb'?'RGB preview':'Depth preview';
    return <section className="luxonis-preview-card" aria-label={t(label)}>
      <div className="luxonis-preview-heading"><h3>{t(label)}</h3><Badge appearance="tint" color={frame?'success':'informative'}>{t(frame?'Live frame':!viewing?'Preview paused':'No fresh frame')}</Badge></div>
      <div className="luxonis-image-viewport">
        {frame?<img src={'data:image/jpeg;base64,'+frame.jpeg} alt={t(label)} onError={()=>setBadFrames(old=>({...old,[key]:frame.stamp}))}/>:<div className="luxonis-empty-frame"><ImageRegular fontSize={36}/><span>{t(!viewing?'Enable preview to view images':graph==='NO_NODE'?'ROS 2 camera node not detected':graph==='AMBIGUOUS'?'Ambiguous camera sources':'Waiting for current image')}</span></div>}
      </div>
      <div className="luxonis-frame-meta">{frame?<><span>{frame.sourceWidth} × {frame.sourceHeight} · {frame.encoding}</span><time dateTime={new Date(frame.stamp*1000).toISOString()}>{new Date(frame.stamp*1000).toLocaleTimeString()}</time></>:<span>{describe(key)}</span>}</div>
      {key==='depth'&&<div className="luxonis-depth-scale"><div className="luxonis-depth-gradient"/><div><span>0 mm</span><span>≥ 2000 mm</span></div><small>{t('Black: invalid depth. Fixed display scale, not a metric image.')}</small></div>}
    </section>;
  };
  return <div className="vision-devices">
    <div className="luxonis-device-header"><div className="luxonis-device-title"><span aria-hidden="true" className="luxonis-device-icon"><VideoRegular fontSize={26}/></span><div><h2>Luxonis OAK-D Pro AF</h2><p>DepthAI ROS v3 · RGB-D</p></div></div>
    </div>
    <div className="luxonis-facts" aria-label={t('Device availability')}>
      <div><span>{t('Hardware connection')}</span><Badge appearance="tint" color={badgeColor(available)}>{t(available?'USB detected':report?.hardwareConnection==='USB_NOT_DETECTED'?'USB not detected':'Hardware unknown')}</Badge></div>
      <div><span>{t('ROS 2 camera node')}</span><Badge appearance="tint" color={graph==='ACTIVE'?'success':graph==='NO_NODE'||graph==='AMBIGUOUS'?'warning':'informative'}>{t(graph==='ACTIVE'?'Detected':graph==='NO_NODE'?'Not detected':graph==='AMBIGUOUS'?'Ambiguous source':'Unknown')}</Badge>{report?.node&&<small>{report.node.name} · ROS {report.node.domain}</small>}</div>
      <div><span>RGB</span><Badge appearance="tint" color={badgeColor(report?.endpoints.rgb==='AVAILABLE')}>{describe('rgb')}</Badge></div>
      <div><span>Depth</span><Badge appearance="tint" color={badgeColor(report?.endpoints.depth==='AVAILABLE')}>{describe('depth')}</Badge></div>
    </div>
    {(!report||report.observer==='UNAVAILABLE')&&<MessageBar intent="warning"><MessageBarBody>{t(failure?'Device report unavailable.':'No current Luxonis observer report.')}</MessageBarBody></MessageBar>}
    {graph==='NO_NODE'&&<MessageBar intent="info"><MessageBarBody>{t('The camera node is not running in the monitored ROS domains. Saved settings are not active parameters.')}</MessageBarBody></MessageBar>}
    {graph==='AMBIGUOUS'&&<MessageBar intent="warning"><MessageBarBody>{t('Multiple camera sources detected. Live settings and preview are withheld.')}</MessageBarBody></MessageBar>}
    <section className="luxonis-ir-card" aria-label={t('IR illumination')}>
      <div className="luxonis-section-heading"><div><h2>{t('IR illumination')}</h2><p>{t('Manual control · 60% when enabled · off at camera startup.')}</p></div></div>
      <div className="luxonis-ir-controls">
        <div><Switch label={t('IR dot projector')} checked={known&&level(dot)&&dot>0} disabled={!canIR} onChange={(_,d)=>{void toggleIR('dot',d.checked);}}/><span>{irLevel(dot)}</span></div>
        <div><Switch label={t('IR flood illuminator')} checked={known&&level(flood)&&flood>0} disabled={!canIR} onChange={(_,d)=>{void toggleIR('flood',d.checked);}}/><span>{irLevel(flood)}</span></div>
      </div>
      {irBusy?<p role="status">{t('Applying IR setting…')}</p>:irMessage?<p role="status">{t(irMessage)}</p>:!canIR?<p className="fine-print">{t('IR control requires the standalone camera, fresh parameters and an idle operator session.')}</p>:null}
    </section>
    <section className="luxonis-preview-section" aria-label={t('Live preview')}>
      <div className="luxonis-section-heading"><div><h2>{t('Live preview')}</h2><p>{t('Read-only preview of existing ROS 2 streams.')}</p></div>
        <Button appearance={viewing?'secondary':'primary'} icon={viewing?<StopRegular/>:<PlayRegular/>} disabled={!permitted||report?.observer!=='ACTIVE'||report.previewAllowed===false} onClick={()=>{setPreview(!viewing);setSample(old=>old?{...old,report:{...old.report,frames:{rgb:null,depth:null}}}:null);}}>{t(viewing?'Stop preview':'Enable preview')}</Button>
      </div>
      {!permitted&&enabled&&<p className="fine-print">{t('Preview requires an operator and an idle station.')}</p>}
      <div className="luxonis-preview-grid">{renderPreview('rgb',frameRgb)}{renderPreview('depth',frameDepth)}</div>
      <p className="fine-print">{t('Preview is reduced for display and is not inspection evidence. Closing or leaving this tab stops the preview request.')}</p>
    </section>
    <section className="luxonis-settings" aria-label={t('Camera settings')}>
      <div className="luxonis-section-heading"><div><h2>{t('Camera settings')}</h2><p>{t('Read-only parameter overview. Use IR controls above to change illumination.')}</p></div>
        <label className="luxonis-settings-source"><span>{t('Settings source')}</span><Select value={source} onChange={e=>setSelected(e.target.value as typeof selected)}><option value="live">{t('Live ROS 2 parameters')}</option>{Object.keys(profiles).filter(k=>report?.profiles[k as keyof typeof profiles]).map(k=><option key={k} value={k}>{t(profiles[k as keyof typeof profiles])}</option>)}</Select></label>
      </div>
      {source!=='live'&&<p className="fine-print">{t('Saved diagnostic configuration — not applied or approved by this view.')}</p>}
      {source==='live'&&!Object.keys(data).length&&<p className="fine-print">{t('No current camera parameter values received.')}</p>}
      <div className="luxonis-settings-grid">
        {parameterGroups.filter(group=>source==='live'||group.rows.some(([key])=>Object.hasOwn(data,key))).map(group=><section key={group.title} className="luxonis-settings-card"><h3>{t(group.title)}</h3>
          <Table size="small" aria-label={t(group.title)}><TableHeader><TableRow><TableHeaderCell>{t('Parameter')}</TableHeaderCell><TableHeaderCell>{t('Value')}</TableHeaderCell></TableRow></TableHeader><TableBody>
            {group.rows.filter(([key])=>source==='live'||Object.hasOwn(data,key)).map(([key,label])=><TableRow key={key}><TableCell>{t(label)}<small title={key}>{key}</small></TableCell><TableCell>{Object.hasOwn(data,key)?typeof data[key]==='boolean'?t(data[key]?'Yes':'No'):String(data[key]):'—'}</TableCell></TableRow>)}
          </TableBody></Table>
        </section>)}
      </div>
      {source==='live'&&report?.settingsAt&&Object.keys(data).length>0&&<p className="fine-print">{t('Last parameter read:')} {new Date(report.settingsAt*1000).toLocaleTimeString()}</p>}
    </section>
  </div>;
}
