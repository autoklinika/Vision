import {record} from './contract';
export type CanConnectionReport={schema:'vision.api.nero-can-connection.v1';source:'STATION';instanceId:string;status:{mode:0|1|3|null;available:boolean}};
export type CanConnectionIntent={instanceId:string;operationId:string;sentAt:number};
export type CanConnectionResult={schema:'vision.api.nero-can-connection-result.v1';source:'STATION';instanceId:string;result:{operationId:string;accepted:boolean;reason:string}};
const id=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
export function isCanConnectionReport(v:unknown):v is CanConnectionReport{
 if(!record(v,['schema','source','instanceId','status'])||v.schema!=='vision.api.nero-can-connection.v1'||v.source!=='STATION'||!id(v.instanceId))return false;
 const s=v.status;
 return record(s,['mode','available'])&&[null,0,1,3].includes(s.mode as number|null)&&typeof s.available==='boolean'&&(!s.available||s.mode===0||s.mode===3);
}
export function isCanConnectionResult(v:unknown):v is CanConnectionResult{
 if(!record(v,['schema','source','instanceId','result'])||v.schema!=='vision.api.nero-can-connection-result.v1'||v.source!=='STATION'||!id(v.instanceId))return false;
 const r=v.result;
 return record(r,['operationId','accepted','reason'])&&id(r.operationId)&&typeof r.accepted==='boolean'&&typeof r.reason==='string'&&
 ['CAN_CONNECTED','ALREADY_CAN','INTERLOCK','STALE','REPLAY','CAN_CONNECT_UNVERIFIED','NOT_COMMISSIONED','BUSY'].includes(r.reason)&&
 r.accepted===['CAN_CONNECTED','ALREADY_CAN'].includes(r.reason);
}
