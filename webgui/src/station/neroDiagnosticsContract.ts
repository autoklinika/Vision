import {record} from './contract';

export const sources=['ARM','J1','J2','J3','J4','J5','J6','J7'] as const;
export const families=['ARM_STATUS','ARM_MASK','DRIVE_STATUS'] as const;
export const severities=['INFO','WARNING','FAULT','UNKNOWN'] as const;
export const clearResults=['CLEARED','PARTIAL','STILL_ACTIVE','NO_ACTIVE_FAULTS','UNVERIFIED','REJECTED','FAILED'] as const;
const reasons=['OBSERVED','NO_ACTIVE_FAULTS','INVALID_REQUEST','NOT_COMMISSIONED','BUSY','DUPLICATE','NO_LOCAL_CONFIRMATION','INTERLOCK','STALE_FEEDBACK','TIMEOUT','SDK_EXCEPTION','SOURCE_CHANGED','TRANSPORT_UNAVAILABLE','HISTORY_UNAVAILABLE','INTERRUPTED'] as const;
export type Source=typeof sources[number];
export type SourceFilter=Source|'ALL';
export type HistoryFilter='ALL'|'ACTIVE'|'RESOLVED';
export type Family=typeof families[number];
export type Severity=typeof severities[number];
export type ClearResult=typeof clearResults[number];
export type ClearScope=1|2|3|4|5|6|7|255;
export type Coverage={source:Source;family:Family;stamp:number};
export type Diagnostic=Coverage&{code:number;hex:string;description:string;severity:Severity};
export type DiagnosticsReport={schema:'vision.api.nero-diagnostics.v1';source:'STATION';instanceId:string;catalog:'nero-v121-vision-v1';capturedAt:number;current:Diagnostic[];coverage:Coverage[];historyAvailable:boolean;clearAvailable:boolean};
export type Evidence={armStamp:number;armStatus:number;armMask:number;driveStatus:number[];driveStamps:number[]};
export type ClearOperation={operationId:string;scope:ClearScope;result:ClearResult;reason:typeof reasons[number];commandInvoked:boolean|null;axisResults:(ClearResult|'NOT_SELECTED')[];sentAfter:number|null;before:Evidence|null;after:Evidence|null};
export type ClearEnvelope={schema:'vision.api.nero-clear.v1';source:'STATION';instanceId:string;operation:ClearOperation};
export type HistoryEvent={id:number;event:Diagnostic;firstSeen:number;lastSeen:number;resolvedAt:number|null;status:'ACTIVE'|'RESOLVED';lastClear:ClearOperation|null};
export type ClearAttempt={id:number;startedAt:number;finishedAt:number;operation:ClearOperation};
export type HistoryReport={schema:'vision.api.nero-history.v1';source:'STATION';instanceId:string;filterSource:SourceFilter;filterStatus:HistoryFilter;before:number;nextBefore:number|null;events:HistoryEvent[]};
export type AttemptReport={schema:'vision.api.nero-clear-history.v1';source:'STATION';instanceId:string;filterSource:SourceFilter;before:number;nextBefore:number|null;events:ClearAttempt[]};
const isOne=<T extends string>(value:unknown,choices:readonly T[]):value is T=>typeof value==='string'&&(choices as readonly string[]).includes(value);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
const int=(v:unknown,max=Number.MAX_SAFE_INTEGER):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max;
const stamp=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>0&&v<=253402300800;
const scope=(v:unknown):v is ClearScope=>int(v,255)&&((v>=1&&v<=7)||v===255);
const src=(v:unknown):v is SourceFilter=>v==='ALL'||isOne(v,sources);
const familyFor=(s:Source,f:Family)=>f==='ARM_STATUS'?s==='ARM':f==='DRIVE_STATUS'?s!=='ARM':true;
function cov(v:unknown):v is Coverage{
 return record(v,['source','family','stamp'])&&isOne(v.source,sources)&&isOne(v.family,families)&&familyFor(v.source,v.family)&&stamp(v.stamp);
}
function event(v:unknown):v is Diagnostic{
 if(!record(v,['source','family','code','hex','description','severity','stamp'])||!isOne(v.source,sources)||!isOne(v.family,families)||!familyFor(v.source,v.family)||!stamp(v.stamp)||!int(v.code,v.family==='ARM_MASK'?65535:255)||!isOne(v.severity,severities)||typeof v.description!=='string'||v.description.length<1||v.description.length>100||/[\x00-\x1f\x7f]/.test(v.description))return false;
 return v.hex==='0x'+v.code.toString(16).toUpperCase().padStart(v.family==='ARM_MASK'?4:2,'0');
}
export function isDiagnosticsReport(v:unknown):v is DiagnosticsReport{
 if(!record(v,['schema','source','instanceId','catalog','capturedAt','current','coverage','historyAvailable','clearAvailable'])||v.schema!=='vision.api.nero-diagnostics.v1'||v.source!=='STATION'||!id(v.instanceId)||v.catalog!=='nero-v121-vision-v1'||!stamp(v.capturedAt)||typeof v.historyAvailable!=='boolean'||typeof v.clearAvailable!=='boolean'||!Array.isArray(v.current)||v.current.length>66||!Array.isArray(v.coverage)||v.coverage.length>16)return false;
 const now=v.capturedAt;
 if(!v.coverage.every(c=>cov(c)&&c.stamp<=now&&now-c.stamp<=2.5)||new Set(v.coverage.map(c=>c.source+':'+c.family)).size!==v.coverage.length)return false;
 const coverage=v.coverage as Coverage[];
 return v.current.every(e=>event(e)&&coverage.some(c=>c.source===e.source&&c.family===e.family&&c.stamp===e.stamp));
}
function evidence(v:unknown):v is Evidence{
 return record(v,['armStamp','armStatus','armMask','driveStatus','driveStamps'])&&stamp(v.armStamp)&&int(v.armStatus,255)&&int(v.armMask,65535)&&Array.isArray(v.driveStatus)&&v.driveStatus.length===7&&v.driveStatus.every(x=>int(x,255))&&Array.isArray(v.driveStamps)&&v.driveStamps.length===7&&v.driveStamps.every(stamp);
}
export function isClearOperation(v:unknown):v is ClearOperation{
 if(!record(v,['operationId','scope','result','reason','commandInvoked','axisResults','sentAfter','before','after'])||!id(v.operationId)||!scope(v.scope)||!isOne(v.result,clearResults)||!isOne(v.reason,reasons)||!(typeof v.commandInvoked==='boolean'||v.commandInvoked===null&&v.result==='UNVERIFIED')||!(v.sentAfter===null||stamp(v.sentAfter))||!(v.before===null||evidence(v.before))||!(v.after===null||evidence(v.after))||!Array.isArray(v.axisResults)||v.axisResults.length!==7)return false;
 const target=v.scope;
 if(!v.axisResults.every((a,i)=>target!==255&&target!==i+1?a==='NOT_SELECTED':isOne(a,clearResults)))return false;
 if(['CLEARED','PARTIAL','STILL_ACTIVE'].includes(v.result))return v.commandInvoked===true&&v.reason==='OBSERVED'&&v.before!==null&&v.after!==null&&v.sentAfter!==null&&Math.max(v.before.armStamp,...v.before.driveStamps)<=v.sentAfter&&Math.min(v.after.armStamp,...v.after.driveStamps)>v.sentAfter;
 if(v.result==='NO_ACTIVE_FAULTS')return v.commandInvoked===false&&v.before!==null&&v.after===null;
 return v.after===null;
}
export function isClearEnvelope(v:unknown):v is ClearEnvelope{
 return record(v,['schema','source','instanceId','operation'])&&v.schema==='vision.api.nero-clear.v1'&&v.source==='STATION'&&id(v.instanceId)&&isClearOperation(v.operation);
}
function historyEvent(v:unknown):v is HistoryEvent{
 return record(v,['id','event','firstSeen','lastSeen','resolvedAt','status','lastClear'])&&int(v.id)&&v.id>0&&event(v.event)&&v.event.severity!=='INFO'&&stamp(v.firstSeen)&&stamp(v.lastSeen)&&v.lastSeen>=v.firstSeen&&v.event.stamp===v.lastSeen&&((v.status==='ACTIVE'&&v.resolvedAt===null)||(v.status==='RESOLVED'&&stamp(v.resolvedAt)&&v.resolvedAt>=v.lastSeen))&&(v.lastClear===null||isClearOperation(v.lastClear));
}
function attempt(v:unknown):v is ClearAttempt{
 return record(v,['id','startedAt','finishedAt','operation'])&&int(v.id)&&v.id>0&&stamp(v.startedAt)&&stamp(v.finishedAt)&&v.finishedAt>=v.startedAt&&isClearOperation(v.operation);
}
function paging<T extends {id:number}>(rows:T[],before:number,next:unknown,max:number){
 let prev=before||Number.MAX_SAFE_INTEGER+1;
 for(const row of rows){if(row.id>=prev)return false;prev=row.id;}
 return next===null||rows.length===max&&next===prev;
}
export function isHistoryReport(v:unknown):v is HistoryReport{
 if(!record(v,['schema','source','instanceId','filterSource','filterStatus','before','nextBefore','events'])||v.schema!=='vision.api.nero-history.v1'||v.source!=='STATION'||!id(v.instanceId)||!src(v.filterSource)||!isOne(v.filterStatus,['ALL','ACTIVE','RESOLVED'])||!int(v.before)||!Array.isArray(v.events)||v.events.length>50||!v.events.every(historyEvent))return false;
 const {filterSource,filterStatus}=v;
 return v.events.every(e=>(filterSource==='ALL'||e.event.source===filterSource)&&(filterStatus==='ALL'||e.status===filterStatus))&&paging(v.events,v.before,v.nextBefore,50);
}
export function isAttemptReport(v:unknown):v is AttemptReport{
 if(!record(v,['schema','source','instanceId','filterSource','before','nextBefore','events'])||v.schema!=='vision.api.nero-clear-history.v1'||v.source!=='STATION'||!id(v.instanceId)||!src(v.filterSource)||!int(v.before)||!Array.isArray(v.events)||v.events.length>20||!v.events.every(attempt))return false;
 const {filterSource}=v;
 return v.events.every(e=>filterSource==='ALL'||filterSource!=='ARM'&&(e.operation.scope===255||e.operation.scope===Number(filterSource.slice(1))))&&paging(v.events,v.before,v.nextBefore,20);
}
