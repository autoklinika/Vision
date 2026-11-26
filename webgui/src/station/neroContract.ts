import {record} from './contract';

export const NERO_AGE=2.5;
export const NERO_JOINTS=['joint1','joint2','joint3','joint4','joint5','joint6','joint7'] as const;
export const NERO_FAULTS=['undervoltage','motor_overtemp','driver_overcurrent','driver_overtemp','collision_tripped','driver_error','stall_tripped'] as const;
export const NERO_PARAMS=['control_enabled','auto_enable','physical_hold_enabled'] as const;
const armCodes=['controlMode','armStatus','modeFeedback','teachStatus','motionStatus','trajectoryNumber','errorCode'] as const;
export type Joint=typeof NERO_JOINTS[number];
export type JointRow={joint:Joint;positionRad:number;velocityRadS:number|null;torqueNm:number|null};
export type MotorRow={joint:Joint;level:0|1|2|3;enabled:boolean|null;faults:Record<typeof NERO_FAULTS[number],boolean>|null;rawStatus:number|null;voltageV:number|null;driverTempC:number|null;motorTempC:number|null;currentA:number|null};
export type ArmPacket={stamp:number;level:0|1|2;angleLimit:boolean[];communicationFault:boolean[]}&Record<typeof armCodes[number],number>;
export type CanPacket={stamp:number;interface:'can0';up:boolean;state:string;bitrate:number|null;rxErrors:number;txErrors:number;rxDropped:number;txDropped:number;rxPackets:number;txPackets:number};
export type NeroReport={
 schema:'vision.api.nero.v1';source:'STATION';instanceId:string;capturedAt:number;model:'AgileX NERO';
 hardwareConnection:'USB_CAN_DETECTED'|'USB_CAN_NOT_DETECTED'|'UNKNOWN';
 observer:'ACTIVE'|'UNAVAILABLE';graph:'ACTIVE'|'NO_NODE'|'AMBIGUOUS'|'UNKNOWN';
 node:{domain:181;name:'/nero_guarded/agx_arm_ctrl_single_node'}|null;
 joints:{stamp:number;rows:JointRow[]}|null;arm:ArmPacket|null;motors:{stamp:number;rows:MotorRow[]}|null;
 parameters:{stamp:number;values:Partial<Record<typeof NERO_PARAMS[number],boolean>>}|null;can:CanPacket|null;
};
const num=(v:unknown,lo=-1e6,hi=1e6):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
const int=(v:unknown,hi=Number.MAX_SAFE_INTEGER):v is number=>num(v,0,hi)&&Number.isSafeInteger(v);
const timestamp=(v:unknown,now:number)=>num(v,0,253402300800)&&v>0&&v<=now&&now-v<=NERO_AGE;
const bools=(v:unknown)=>Array.isArray(v)&&v.length===7&&v.every(x=>typeof x==='boolean');
const nullable=(v:unknown)=>v===null||num(v);
function jointRows(v:unknown,now:number):boolean{
 return v===null||(record(v,['stamp','rows'])&&timestamp(v.stamp,now)&&Array.isArray(v.rows)&&v.rows.length===7&&
  v.rows.every((r,i)=>record(r,['joint','positionRad','velocityRadS','torqueNm'])&&r.joint===NERO_JOINTS[i]&&num(r.positionRad,-100,100)&&nullable(r.velocityRadS)&&nullable(r.torqueNm)));
}
const motorNumbers=['voltageV','driverTempC','motorTempC','currentA'] as const;
function motorRows(v:unknown,now:number):boolean{
 return v===null||(record(v,['stamp','rows'])&&timestamp(v.stamp,now)&&Array.isArray(v.rows)&&v.rows.length===7&&
  v.rows.every((r,i)=>record(r,['joint','level','enabled','faults','rawStatus',...motorNumbers])&&r.joint===NERO_JOINTS[i]&&int(r.level,3)&&
    (r.level===3?[r.enabled,r.faults,r.rawStatus,...motorNumbers.map(k=>r[k])].every(x=>x===null):
     typeof r.enabled==='boolean'&&int(r.rawStatus,255)&&record(r.faults,[...NERO_FAULTS])&&Object.values(r.faults).every(x=>typeof x==='boolean')&&motorNumbers.every(k=>nullable(r[k])))));
}
function arm(v:unknown,now:number):boolean{
 return v===null||(record(v,['stamp','level',...armCodes,'angleLimit','communicationFault'])&&timestamp(v.stamp,now)&&int(v.level,2)&&
  armCodes.every(k=>int(v[k],k==='errorCode'||k==='trajectoryNumber'?65535:255))&&bools(v.angleLimit)&&bools(v.communicationFault));
}
function parameters(v:unknown,now:number):boolean{
 return v===null||(record(v,['stamp','values'])&&timestamp(v.stamp,now)&&v.values!==null&&typeof v.values==='object'&&!Array.isArray(v.values)&&
  Object.entries(v.values).every(([k,x])=>(NERO_PARAMS as readonly string[]).includes(k)&&typeof x==='boolean'));
}
function can(v:unknown,now:number):boolean{
 const counts=['rxErrors','txErrors','rxDropped','txDropped','rxPackets','txPackets'] as const;
 return v===null||(record(v,['stamp','interface','up','state','bitrate',...counts])&&timestamp(v.stamp,now)&&v.interface==='can0'&&typeof v.up==='boolean'&&
  ['ERROR-ACTIVE','ERROR-WARNING','ERROR-PASSIVE','BUS-OFF','STOPPED','SLEEPING','UNKNOWN'].includes(String(v.state))&&
  (v.bitrate===null||int(v.bitrate,10000000))&&counts.every(k=>int(v[k])));
}
export function isNeroReport(v:unknown):v is NeroReport{
 if(!record(v,['schema','source','instanceId','capturedAt','model','hardwareConnection','observer','graph','node','joints','arm','motors','parameters','can'])||
 v.schema!=='vision.api.nero.v1'||v.source!=='STATION'||v.model!=='AgileX NERO'||typeof v.instanceId!=='string'||!/^[a-f0-9]{32}$/.test(v.instanceId)||
 !num(v.capturedAt,1,253402300800)||!['USB_CAN_DETECTED','USB_CAN_NOT_DETECTED','UNKNOWN'].includes(String(v.hardwareConnection))||
 !['ACTIVE','UNAVAILABLE'].includes(String(v.observer))||!['ACTIVE','NO_NODE','AMBIGUOUS','UNKNOWN'].includes(String(v.graph)))return false;
 if(v.graph==='ACTIVE'){
  if(!record(v.node,['domain','name'])||v.node.domain!==181||v.node.name!=='/nero_guarded/agx_arm_ctrl_single_node')return false;
 }else if(v.node!==null||[v.joints,v.arm,v.motors,v.parameters].some(x=>x!==null))return false;
 if(v.observer==='UNAVAILABLE'&&(v.graph!=='UNKNOWN'||v.can!==null))return false;
 return jointRows(v.joints,v.capturedAt)&&motorRows(v.motors,v.capturedAt)&&arm(v.arm,v.capturedAt)&&parameters(v.parameters,v.capturedAt)&&can(v.can,v.capturedAt);
}
