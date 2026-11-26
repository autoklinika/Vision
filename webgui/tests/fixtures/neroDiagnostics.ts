import type {DiagnosticsReport,HistoryReport,AttemptReport,SourceFilter,HistoryFilter,ClearOperation,ClearScope} from '../../src/station/neroDiagnosticsContract';
import {sources} from '../../src/station/neroDiagnosticsContract';
export function diagnosticsFixture(clearAvailable=false,now=Date.now()/1000):DiagnosticsReport{
 const stamp=now-.1;
 return {schema:'vision.api.nero-diagnostics.v1',source:'STATION',instanceId:'f'.repeat(32),catalog:'nero-v121-vision-v1',capturedAt:now,
  historyAvailable:true,clearAvailable,
  current:[{source:'ARM',family:'ARM_STATUS',stamp,code:6,hex:'0x06',description:'Joint brakes not released',severity:'WARNING'},
           {source:'J5',family:'DRIVE_STATUS',stamp,code:32,hex:'0x20',description:'Driver error',severity:'FAULT'}],
  coverage:[{source:'ARM',family:'ARM_STATUS',stamp},...sources.map(source=>({source,family:'ARM_MASK' as const,stamp})),
            ...sources.filter(s=>s!=='ARM').map(source=>({source,family:'DRIVE_STATUS' as const,stamp}))]};
}
export function rejectedOperation(operationId:string,scope:ClearScope):ClearOperation{
 return {operationId,scope,result:'REJECTED',reason:'NO_LOCAL_CONFIRMATION',commandInvoked:false,sentAfter:null,before:null,after:null,
         axisResults:Array.from({length:7},(_,i)=>scope===255||scope===i+1?'REJECTED':'NOT_SELECTED')};
}
export function neroHistoryFixture(source:SourceFilter='ALL',status:HistoryFilter='ALL',before=0):HistoryReport{
 const e=diagnosticsFixture(false,100).current[1];
 const row={id:1,event:e,firstSeen:e.stamp-10,lastSeen:e.stamp,resolvedAt:null,status:'ACTIVE' as const,lastClear:rejectedOperation('b'.repeat(32),5)};
 return {schema:'vision.api.nero-history.v1',source:'STATION',instanceId:'f'.repeat(32),
         filterSource:source,filterStatus:status,before,nextBefore:null,events:(!before&&(source==='ALL'||source==='J5')&&(status==='ALL'||status==='ACTIVE'))?[row]:[]};
}
export function neroAttemptFixture(source:SourceFilter='ALL',before=0):AttemptReport{
 return {schema:'vision.api.nero-clear-history.v1',source:'STATION',instanceId:'f'.repeat(32),filterSource:source,before,nextBefore:null,
         events:!before&&(source==='ALL'||source==='J5')?[{id:1,startedAt:99,finishedAt:100,operation:rejectedOperation('b'.repeat(32),5)}]:[]};
}
