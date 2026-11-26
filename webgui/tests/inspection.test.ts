import {afterEach, expect, it, vi} from 'vitest';
import {isInspectionReport, isIdentityReport} from '../src/station/contract';
import {readInspection, startInspection, closeInspection} from '../src/station/transport';
import {identityFixture, stationFixture} from './fixtures/station';
const origin = 'http://127.0.0.1:18491';
const instanceId = 'a'.repeat(32);
const intentToken = 'b'.repeat(32);
const timestamp = '2026-11-25T12:00:00Z';
const report = {
  schema:'vision.api.inspection.v1', source:'STATION', instanceId, intentToken,
  capturedAt:timestamp, sessionId:null, startAllowed:false, closeAllowed:false,
  devices:['luxonis','nero','moveit','sony'].map(device => ({device, availability:'UNKNOWN',readiness:'UNKNOWN',observedAt:timestamp})),
  selections:[], blockers:['COMPOSITION_UNCONFIGURED','NO_APPROVED_SELECTION','DEVICES_NOT_VERIFIED'],
};
function response(body:unknown,path:string,status=200) {
  const r=new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json; charset=utf-8'}});
  Object.defineProperty(r,'url',{value:origin+path}); return r;
}
function secure(){vi.stubGlobal('isSecureContext',true);vi.stubGlobal('location',new URL(origin));}
afterEach(()=>vi.unstubAllGlobals());

it('validates only exact reports and explicit reader or operator identity',()=>{
  expect(isInspectionReport(report)).toBe(true);
  expect(isIdentityReport({...identityFixture(),role:'operator'})).toBe(true);
  expect(isIdentityReport({...identityFixture(),role:'admin'})).toBe(false);
  for(const invalid of [
    {...report, extra:true},
    {...report, intentToken:'bad'},
    {...report, blockers:[], startAllowed:true},
    {...report, closeAllowed:true},
    {...report, devices:[...report.devices.slice(0,3),{...report.devices[3],readiness:'READY'}]},
    {...report, devices:[...report.devices.slice(0,3),report.devices[2]]},
  ]) expect(isInspectionReport(invalid)).toBe(false);
});

it('accepts the explicit hardware metadata extension, never interprets USB as readiness',()=>{
  const hardware = ['USB_DETECTED','UNKNOWN','NOT_APPLICABLE','USB_NOT_DETECTED'];
  const extended = {...report,devices:report.devices.map((d,i)=>({...d,hardwareConnection:hardware[i]}))};
  expect(isInspectionReport(extended)).toBe(true);
  expect(isInspectionReport(report)).toBe(true);
  expect(isInspectionReport({...extended,startAllowed:true,blockers:[]})).toBe(false);
  for(const [index,value] of [[0,'READY'],[1,'USB_DETECTED'],[2,'USB_DETECTED'],[3,'NOT_APPLICABLE'],[0,null]] as const){
    expect(isInspectionReport({...extended,devices:extended.devices.map((d,i)=>i===index?{...d,hardwareConnection:value}:d)})).toBe(false);
  }
  expect(isInspectionReport({...extended,devices:extended.devices.map(d=>({...d,extra:true}))})).toBe(false);
});

it('reads readiness and sends only the explicit selection and stale intent token', async()=>{
  secure();
  const network=vi.fn().mockResolvedValueOnce(response(report,'/api/v1/inspection'))
    .mockResolvedValueOnce(response({schema:'vision.api.error.v1',code:'INSPECTION_REJECTED'},'/api/v1/inspection/start',409))
    .mockResolvedValueOnce(response({schema:'vision.api.error.v1',code:'OPERATOR_REQUIRED'},'/api/v1/inspection/close',403));
  vi.stubGlobal('fetch',network);
  expect((await readInspection()).status).toBe('AVAILABLE');
  expect((await startInspection(instanceId,'etc3-photo',intentToken)).status).toBe('INSPECTION_REJECTED');
  expect((await closeInspection(instanceId,'inspection-example')).status).toBe('OPERATOR_REQUIRED');
  expect(JSON.parse(network.mock.calls[1][1].body)).toEqual({instanceId,selectionId:'etc3-photo',intentToken});
  expect(network.mock.calls[1][1]).toMatchObject({method:'POST',credentials:'same-origin',referrerPolicy:'same-origin',headers:{'X-Vision-Client':'webgui'}});
  expect(JSON.parse(network.mock.calls[2][1].body)).toEqual({instanceId,sessionId:'inspection-example'});
});

it('does not automatically retry an ambiguous session mutation',async()=>{
  secure();
  const network=vi.fn().mockRejectedValue(new Error('unconfirmed response'));
  vi.stubGlobal('fetch',network);
  expect(await startInspection(instanceId,'etc3-photo',intentToken)).toEqual({status:'UNAVAILABLE',report:null});
  expect(network).toHaveBeenCalledTimes(1);
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(stationFixture(),'/api/v1/inspection/start')));
  // Transport validates only the station report. The UI additionally pins the
  // instance and requires SESSION_ACTIVE before announcing start success.
  expect((await startInspection(instanceId,'etc3-photo',intentToken)).status).toBe('AVAILABLE');
});
