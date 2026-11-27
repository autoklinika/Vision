import {record} from './contract';
import type {TcpDeclaration,TcpAxis} from './neroTcpContract';
export const actions=['ENABLE','JOG','RELEASE','HOLD','CLOSE'] as const;
export const states=['IDLE','ENABLING','READY','JOGGING','STOPPING','HOLD','FAULT'] as const;
export type ManualAction=typeof actions[number];
export type ManualState=typeof states[number];
export type ManualIntent={instanceId:string;operationId:string;action:ManualAction;sequence:number;sentAt:number;
 declaration:TcpDeclaration|null;axis:TcpAxis|null;direction:-1|1|null};
export type ManualStatus={state:ManualState;reason:string;driveEnabled:(boolean|null)[];pipelineReady:boolean;
 enableAvailable:boolean;jogAvailable:boolean;holdAvailable:boolean;linearMax:number;angularMax:number};
export type ManualReport={schema:'vision.api.nero-manual.v1';source:'STATION';instanceId:string;status:ManualStatus|null};
export type ManualResult={schema:'vision.api.nero-manual-command.v1';source:'STATION';instanceId:string;
 result:{operationId:string;action:ManualAction;sequence:number;accepted:boolean;reason:string;state:ManualState|'LOCKED'}};
const id=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
const one=<T extends string>(v:unknown,a:readonly T[]):v is T=>typeof v==='string'&&(a as readonly string[]).includes(v);
const range=(v:unknown,min:number,max:number):v is number=>typeof v==='number'&&Number.isInteger(v)&&v>=min&&v<=max;
const reason=(v:unknown)=>typeof v==='string'&&v.length>0&&v.length<=80;
function status(v:unknown):v is ManualStatus{
 return record(v,['state','reason','driveEnabled','pipelineReady','enableAvailable','jogAvailable','holdAvailable','linearMax','angularMax'])
 &&one(v.state,states)&&reason(v.reason)&&Array.isArray(v.driveEnabled)&&v.driveEnabled.length===7&&v.driveEnabled.every(x=>x===null||typeof x==='boolean')
 &&typeof v.pipelineReady==='boolean'&&typeof v.enableAvailable==='boolean'&&typeof v.jogAvailable==='boolean'&&typeof v.holdAvailable==='boolean'
 &&range(v.linearMax,1,100)&&range(v.angularMax,1,30);
}
export function isManualReport(v:unknown):v is ManualReport{
 return record(v,['schema','source','instanceId','status'])&&v.schema==='vision.api.nero-manual.v1'&&v.source==='STATION'&&id(v.instanceId)&&(v.status===null||status(v.status));
}
export function isManualResult(v:unknown):v is ManualResult{
 if(!record(v,['schema','source','instanceId','result'])||v.schema!=='vision.api.nero-manual-command.v1'||v.source!=='STATION'||!id(v.instanceId))return false;
 const r=v.result;
 return record(r,['operationId','action','sequence','accepted','reason','state'])&&id(r.operationId)&&one(r.action,actions)
 &&range(r.sequence,0,2147483647)&&typeof r.accepted==='boolean'&&reason(r.reason)&&(one(r.state,states)||r.state==='LOCKED'&&!r.accepted);
}
