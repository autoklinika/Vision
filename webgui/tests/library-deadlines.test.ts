import {afterEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {readLibrary, libraryTimeoutMs} from '../src/api/libraryAdapter';
import {protectedTimeoutMs} from '../src/api/protectedAdapter';
import {editDraft, editorTimeoutMs, stationTimeoutMs} from '../src/station/transport';
import {libraryFixture} from './fixtures/library';

const origin='http://127.0.0.1:18492';
const document=JSON.parse(readFileSync(new URL('./fixtures/editor-profile.json',import.meta.url),'utf8'));
const draft={schema:'vision.api.ecu-draft.v1',source:'STATION',instanceId:'a'.repeat(32),
  key:document.metadata.profile_id,etag:'"'+'b'.repeat(64)+'"',document};
function delayed(value:unknown,delay?:number) {
  vi.useFakeTimers();
  vi.stubGlobal('isSecureContext',true);
  vi.stubGlobal('location',new URL(origin));
  const network=vi.fn((url:URL,options:RequestInit)=>new Promise<Response>((resolve,reject)=>{
    const timer=delay===undefined?undefined:setTimeout(()=>{
      const result=new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json; charset=utf-8'}});
      Object.defineProperty(result,'url',{value:String(url)});resolve(result);
    },delay);
    options.signal!.addEventListener('abort',()=>{clearTimeout(timer);reject(new Error('aborted'));},{once:true});
  }));
  vi.stubGlobal('fetch',network);
  return network;
}
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers();});

it('accepts an editor result after the ordinary station deadline without resending the request',async()=>{
  const network=delayed(draft,stationTimeoutMs+500);
  const pending=editDraft('open',{instanceId:draft.instanceId,key:draft.key});
  await vi.advanceTimersByTimeAsync(stationTimeoutMs+500);
  expect(await pending).toEqual({status:'AVAILABLE',report:draft});
  expect(network).toHaveBeenCalledTimes(1);
});

it('an unresponsive editor still has a bounded deadline and never retries',async()=>{
  const network=delayed(draft);
  const pending=editDraft('open',{instanceId:draft.instanceId,key:draft.key});
  await vi.advanceTimersByTimeAsync(editorTimeoutMs);
  expect(await pending).toEqual({status:'UNAVAILABLE',report:null});
  expect(network).toHaveBeenCalledTimes(1);
});

it('accepts verified library history beyond the ordinary session read deadline',async()=>{
  const report=libraryFixture();
  const network=delayed(report,protectedTimeoutMs+500);
  const pending=readLibrary();
  await vi.advanceTimersByTimeAsync(protectedTimeoutMs+500);
  expect(await pending).toEqual({status:'AVAILABLE',report});
  expect(network).toHaveBeenCalledTimes(1);
});

it('a stalled library read remains bounded',async()=>{
  delayed(libraryFixture());
  const pending=readLibrary();
  await vi.advanceTimersByTimeAsync(libraryTimeoutMs);
  expect(await pending).toEqual({status:'UNAVAILABLE',report:null});
});
