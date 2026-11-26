import {record} from './contract';

export const parameterGroups = [
  {title:'RGB camera',rows:[
    ['rgb.i_width','RGB width'],['rgb.i_height','RGB height'],['rgb.i_resolution','RGB resolution'],
    ['rgb.i_fps','RGB configured FPS'],['rgb.i_publish_topic','RGB publication'],
    ['rgb.r_set_man_focus','Manual focus mode'],['rgb.r_focus','Focus setting'],
    ['rgb.r_set_man_exposure','Manual exposure mode'],['rgb.r_exposure','Exposure (µs)'],['rgb.r_iso','ISO'],
  ]},
  {title:'Stereo depth',rows:[
    ['stereo.i_width','Depth width'],['stereo.i_height','Depth height'],['stereo.i_fps','Depth configured FPS'],
    ['stereo.i_publish_topic','Depth publication'],['stereo.i_depth_preset','Depth preset'],
    ['stereo.i_aligned','RGB alignment'],['stereo.i_subpixel','Subpixel'],['stereo.i_lr_check','Left-right check'],
    ['stereo.i_extended_disp','Extended disparity'],['left.i_width','Left sensor width'],
    ['left.i_height','Left sensor height'],['left.i_fps','Left sensor FPS'],['left.i_resolution','Left sensor resolution'],
    ['right.i_width','Right sensor width'],['right.i_height','Right sensor height'],
    ['right.i_fps','Right sensor FPS'],['right.i_resolution','Right sensor resolution'],
  ]},
  {title:'Pipeline and illumination',rows:[
    ['pipeline_gen.i_pipeline_type','Pipeline type'],['pipeline_gen.i_enable_rgbd','RGB-D pipeline'],
    ['driver.i_enable_ir','IR control enabled in driver'],['driver.r_laser_dot_intensity','IR dot intensity'],
    ['driver.r_floodlight_intensity','IR flood intensity'],
    ['driver.i_pipeline_auto_calibration_mode','Auto-calibration mode'],
  ]},
] as const;
const boolKeys=new Set<string>(['driver.i_enable_ir','pipeline_gen.i_enable_rgbd','rgb.i_publish_topic','rgb.r_set_man_focus','rgb.r_set_man_exposure','stereo.i_publish_topic','stereo.i_aligned','stereo.i_subpixel','stereo.i_lr_check','stereo.i_extended_disp']);
const enumKeys=new Set<string>(['pipeline_gen.i_pipeline_type','driver.i_pipeline_auto_calibration_mode','stereo.i_depth_preset','rgb.i_resolution','left.i_resolution','right.i_resolution']);
const keys=new Set<string>(parameterGroups.flatMap(g=>g.rows.map(r=>r[0])));
export type Settings=Readonly<Record<string,string|number|boolean>>;
export type PreviewFrame=Readonly<{stamp:number;sourceWidth:number;sourceHeight:number;encoding:string;width:number;height:number;jpeg:string}>;
export type LuxonisReport=Readonly<{
  schema:'vision.api.luxonis.v1';source:'STATION';instanceId:string;capturedAt:number;model:'OAK-D Pro AF';
  hardwareConnection:'USB_DETECTED'|'USB_NOT_DETECTED'|'UNKNOWN';observer:'ACTIVE'|'UNAVAILABLE';
  graph:'UNKNOWN'|'NO_NODE'|'ACTIVE'|'AMBIGUOUS';node:{domain:181|186;name:'/oak'|'/oak800'}|null;
  endpoints:{rgb:Endpoint;depth:Endpoint};settings:Settings;settingsAt:number|null;
  profiles:Partial<Record<'rgbd_lab'|'stereo800_lab',Settings>>;frames:{rgb:PreviewFrame|null;depth:PreviewFrame|null};previewAllowed:boolean;irControlAvailable?:boolean;
}>;
type Endpoint='UNKNOWN'|'AVAILABLE'|'UNAVAILABLE'|'AMBIGUOUS';
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const number=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value);
const fresh=(v:unknown,now:number,age:number)=>number(v)&&v>0&&v<=now&&now-v<=age;
function settings(v:unknown):v is Settings{
  return object(v)&&Object.entries(v).every(([k,x])=>keys.has(k)&&
    (boolKeys.has(k)?typeof x==='boolean':enumKeys.has(k)?typeof x==='string'&&/^[A-Za-z0-9_-]{1,48}$/.test(x):number(x)&&x>=0&&x<=1e8));
}
function frame(v:unknown,stream:string,now:number):v is PreviewFrame|null{
  if(v===null)return true;
  if(!record(v,['stamp','sourceWidth','sourceHeight','encoding','width','height','jpeg'])||
    !fresh(v.stamp,now,2.5)||!((stream==='rgb'?['rgb8','bgr8']:['16UC1','32FC1']).includes(String(v.encoding))))return false;
  const dims=[v.width,v.height,v.sourceWidth,v.sourceHeight];
  if(!dims.every(x=>typeof x==='number'&&Number.isSafeInteger(x)&&x>=1&&x<=4096))return false;
  if(Number(v.width)>Math.min(640,Number(v.sourceWidth))||Number(v.height)>Math.min(480,Number(v.sourceHeight)))return false;
  if(typeof v.jpeg!=='string'||v.jpeg.length>4*Math.ceil(40960/3)||v.jpeg.length%4!==0||!/^[A-Za-z0-9+/]+={0,2}$/.test(v.jpeg))return false;
  try{const raw=atob(v.jpeg);return raw.length>=4&&raw.length<=40960&&raw.startsWith('\xff\xd8')&&raw.endsWith('\xff\xd9')&&btoa(raw)===v.jpeg;}catch{return false;}
}
export function isLuxonisReport(v:unknown):v is LuxonisReport{
  if(!record(v,['schema','source','instanceId','capturedAt','model','hardwareConnection','observer','graph','node','endpoints','settings','settingsAt','profiles','frames','previewAllowed',...(object(v)&&Object.hasOwn(v,'irControlAvailable')?['irControlAvailable']:[])])||
    v.schema!=='vision.api.luxonis.v1'||v.source!=='STATION'||v.model!=='OAK-D Pro AF'||typeof v.instanceId!=='string'||!/^[a-f0-9]{32}$/.test(v.instanceId)||
    !number(v.capturedAt)||v.capturedAt<=0||v.capturedAt>=253402300800||!['USB_DETECTED','USB_NOT_DETECTED','UNKNOWN'].includes(String(v.hardwareConnection))||
    !['ACTIVE','UNAVAILABLE'].includes(String(v.observer))||!['UNKNOWN','NO_NODE','ACTIVE','AMBIGUOUS'].includes(String(v.graph))||
    typeof v.previewAllowed!=='boolean'||!settings(v.settings)||!object(v.profiles)||
    !Object.entries(v.profiles).every(([k,x])=>['rgbd_lab','stereo800_lab'].includes(k)&&settings(x))||
    !record(v.endpoints,['rgb','depth'])||!Object.values(v.endpoints).every(x=>['UNKNOWN','AVAILABLE','UNAVAILABLE','AMBIGUOUS'].includes(String(x)))||
    !record(v.frames,['rgb','depth'])||!frame(v.frames.rgb,'rgb',v.capturedAt)||!frame(v.frames.depth,'depth',v.capturedAt))return false;
  if(v.graph==='ACTIVE'){
    if(!record(v.node,['domain','name'])||!((v.node.domain===181&&['/oak','/oak800'].includes(String(v.node.name)))||(v.node.domain===186&&v.node.name==='/oak')))return false;
  }else{
    const expected=v.graph==='NO_NODE'?'UNAVAILABLE':v.graph==='AMBIGUOUS'?'AMBIGUOUS':'UNKNOWN';
    if(v.node!==null||Object.keys(v.settings).length||v.settingsAt!==null||Object.values(v.frames).some(x=>x!==null)||Object.values(v.endpoints).some(x=>x!==expected))return false;
  }
  if(v.settingsAt===null?Object.keys(v.settings).length>0:!fresh(v.settingsAt,v.capturedAt,8))return false;
  if(v.observer==='UNAVAILABLE'&&(v.graph!=='UNKNOWN'||Object.keys(v.profiles).length>0))return false;
  for(const stream of ['rgb','depth'] as const){
    if(v.frames[stream]!==null&&(!v.previewAllowed||v.endpoints[stream]!=='AVAILABLE'))return false;
  }
  if(Object.hasOwn(v,'irControlAvailable')){
    const can=v.previewAllowed&&v.observer==='ACTIVE'&&v.graph==='ACTIVE'&&
      v.node!==null&&object(v.node)&&v.node.domain===186&&v.node.name==='/oak'&&
      v.hardwareConnection==='USB_DETECTED'&&Object.values(v.endpoints).every(s=>s==='AVAILABLE')&&
      v.settings['driver.i_enable_ir']===true&&level(v.settings['driver.r_laser_dot_intensity'])&&
      level(v.settings['driver.r_floodlight_intensity']);
    if(typeof v.irControlAvailable!=='boolean'||v.irControlAvailable!==can)return false;
  }
  return true;
}

export type IRChannel='dot'|'flood';
export type IRResult=Readonly<{schema:'vision.api.luxonis-ir.v1';source:'STATION';instanceId:string;channel:IRChannel;enabled:boolean;dot:number;flood:number;capturedAt:number}>;
export function level(v:unknown):v is number{return number(v)&&v>=0&&v<=1;}
export function isIRResult(v:unknown):v is IRResult{
  return record(v,['schema','source','instanceId','channel','enabled','dot','flood','capturedAt'])&&
    v.schema==='vision.api.luxonis-ir.v1'&&v.source==='STATION'&&typeof v.instanceId==='string'&&/^[a-f0-9]{32}$/.test(v.instanceId)&&
    (v.channel==='dot'||v.channel==='flood')&&typeof v.enabled==='boolean'&&level(v.dot)&&level(v.flood)&&
    number(v.capturedAt)&&v.capturedAt>0&&v.capturedAt<253402300800&&Math.abs((v.channel==='dot'?v.dot:v.flood)-(v.enabled?0.6:0))<1e-6;
}
