import {expect,it,vi,afterEach} from 'vitest';
import {isDiagnosticsReport,isHistoryReport,isAttemptReport,isClearOperation} from '../src/station/neroDiagnosticsContract';
import {readNeroDiagnostics,readNeroHistory,clearNero} from '../src/station/transport';
import {diagnosticsFixture,neroHistoryFixture,neroAttemptFixture,rejectedOperation} from './fixtures/neroDiagnostics';

it('validates source-specific codes and rejects stale, mismatched or forged reports',()=>{
 const d=diagnosticsFixture(false,100);
 expect(isDiagnosticsReport(d)).toBe(true);
 expect(isDiagnosticsReport({...d,coverage:[]})).toBe(false);
 expect(isDiagnosticsReport({...d,current:[{...d.current[0],stamp:90}]})).toBe(false);
 expect(isDiagnosticsReport({...d,current:[{...d.current[0],hex:'0xFF'}]})).toBe(false);
 expect(isDiagnosticsReport({...d,coverage:[...d.coverage,d.coverage[0]]})).toBe(false);
 expect(isHistoryReport(neroHistoryFixture())).toBe(true);
 expect(isHistoryReport({...neroHistoryFixture(),filterSource:'J1'})).toBe(false);
 expect(isAttemptReport(neroAttemptFixture())).toBe(true);
 expect(isAttemptReport({...neroAttemptFixture(),filterSource:'J2'})).toBe(false);
 const rejected=rejectedOperation('b'.repeat(32),5);
 expect(isClearOperation(rejected)).toBe(true);
 expect(isClearOperation({...rejected,result:'CLEARED'})).toBe(false);
 expect(isClearOperation({...rejected,axisResults:Array(7).fill('REJECTED')})).toBe(false);
});
afterEach(()=>vi.unstubAllGlobals());
it('uses fixed authenticated routes and matches response operation IDs',async()=>{
 const origin='http://127.0.0.1:18491';
 vi.stubGlobal('location',new URL(origin));vi.stubGlobal('isSecureContext',true);
 const reply=(path:string,data:unknown)=>{
  const r=new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json; charset=utf-8'}});
  Object.defineProperty(r,'url',{value:origin+path});return r;
 };
 const fetch=vi.fn()
   .mockResolvedValueOnce(reply('/api/v1/devices/nero/diagnostics',diagnosticsFixture()))
   .mockResolvedValueOnce(reply('/api/v1/devices/nero/history?source=J5&status=ACTIVE&before=0',neroHistoryFixture('J5','ACTIVE')))
   .mockResolvedValueOnce(reply('/api/v1/devices/nero/clear',{schema:'vision.api.nero-clear.v1',source:'STATION',instanceId:'f'.repeat(32),operation:rejectedOperation('b'.repeat(32),5)}));
 vi.stubGlobal('fetch',fetch);
 expect((await readNeroDiagnostics()).status).toBe('AVAILABLE');
 expect((await readNeroHistory('J5','ACTIVE',0)).status).toBe('AVAILABLE');
 expect((await clearNero('f'.repeat(32),'c'.repeat(32),5)).status).toBe('UNAVAILABLE');
 expect(fetch.mock.calls.map(x=>x[1].method)).toEqual(['GET','GET','POST']);
 expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({instanceId:'f'.repeat(32),operationId:'c'.repeat(32),scope:5});
});
