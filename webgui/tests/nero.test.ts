import {expect,it,vi,afterEach} from 'vitest';
import {isNeroReport} from '../src/station/neroContract';
import {readNero} from '../src/station/transport';
import {neroFixture} from './fixtures/nero';

it('validates fixed seven-axis feedback and rejects stale or malformed packets',()=>{
 const r=neroFixture(true,100);
 expect(isNeroReport(r)).toBe(true);
 expect(isNeroReport(neroFixture(false,100))).toBe(true);
 expect(isNeroReport({...r,graph:'NO_NODE'})).toBe(false);
 expect(isNeroReport({...r,node:{domain:185,name:'/nero_guarded/agx_arm_ctrl_single_node'}})).toBe(false);
 expect(isNeroReport({...r,joints:{...r.joints,stamp:96}})).toBe(false);
 expect(isNeroReport({...r,joints:{...r.joints,rows:r.joints!.rows.slice(1)}})).toBe(false);
 expect(isNeroReport({...r,parameters:{stamp:99.9,values:{control_enabled:true,other:true}}})).toBe(false);
 expect(isNeroReport({...r,motors:{...r.motors,rows:r.motors!.rows.map((m,i)=>i===0?{...m,level:3}:m)}})).toBe(false);
});
afterEach(()=>vi.unstubAllGlobals());
it('uses only the closed read-only NERO endpoint',async()=>{
 const origin='http://127.0.0.1:18491';
 vi.stubGlobal('location',new URL(origin));vi.stubGlobal('isSecureContext',true);
 const r=new Response(JSON.stringify(neroFixture()),{headers:{'Content-Type':'application/json; charset=utf-8'}});
 Object.defineProperty(r,'url',{value:origin+'/api/v1/devices/nero'});
 const fetch=vi.fn().mockResolvedValueOnce(r);vi.stubGlobal('fetch',fetch);
 expect((await readNero()).status).toBe('AVAILABLE');
 expect(fetch.mock.calls[0][1].method).toBe('GET');
 expect(String(fetch.mock.calls[0][0])).toBe(origin+'/api/v1/devices/nero');
});
