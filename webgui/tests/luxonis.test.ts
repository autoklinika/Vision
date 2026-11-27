import {expect,it,vi,afterEach} from 'vitest';
import {isLuxonisReport} from '../src/station/luxonisContract';
import {readLuxonis} from '../src/station/transport';
import {luxonisFixture} from './fixtures/luxonis';

it('validates live observations and rejects stale, mixed and private settings',()=>{
 const r=luxonisFixture(true,true,100);
 expect(isLuxonisReport(r)).toBe(true);
 expect(isLuxonisReport(luxonisFixture(false,false,100))).toBe(true);
 expect(isLuxonisReport({...r,node:{domain:1,name:'/oak'}})).toBe(false);
 expect(isLuxonisReport({...r,graph:'NO_NODE'})).toBe(false);
 expect(isLuxonisReport({...r,settings:{serial:'private'}})).toBe(false);
 expect(isLuxonisReport({...r,settingsAt:90})).toBe(false);
 expect(isLuxonisReport({...r,previewAllowed:false})).toBe(false);
 expect(isLuxonisReport({...r,frames:{...r.frames,rgb:{...r.frames.rgb,stamp:96.1}}})).toBe(true);
 expect(isLuxonisReport({...r,frames:{...r.frames,rgb:{...r.frames.rgb,stamp:95.9}}})).toBe(false);
 expect(isLuxonisReport({...r,frames:{...r.frames,rgb:{...r.frames.rgb,stamp:90}}})).toBe(false);
 expect(isLuxonisReport({...r,frames:{...r.frames,rgb:{...r.frames.rgb,jpeg:'bad'}}})).toBe(false);
});
afterEach(()=>vi.unstubAllGlobals());
it('never returns image data through the status endpoint',async()=>{
 const origin='http://127.0.0.1:18491';
 vi.stubGlobal('location',new URL(origin));vi.stubGlobal('isSecureContext',true);
 const make=(preview:boolean)=>{
   const r=new Response(JSON.stringify(luxonisFixture(true,true,100)),{headers:{'Content-Type':'application/json; charset=utf-8'}});
   Object.defineProperty(r,'url',{value:origin+'/api/v1/devices/luxonis'+(preview?'/preview':'')});return r;
 };
 const fetch=vi.fn().mockResolvedValueOnce(make(false)).mockResolvedValueOnce(make(true));
 vi.stubGlobal('fetch',fetch);
 expect((await readLuxonis(false)).status).toBe('UNAVAILABLE');
 expect((await readLuxonis(true)).status).toBe('AVAILABLE');
 expect(fetch.mock.calls[0][1].method).toBe('GET');
 expect(fetch.mock.calls[1][1].method).toBe('GET');
});
