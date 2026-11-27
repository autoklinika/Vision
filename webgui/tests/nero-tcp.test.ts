import {jointCheckFixture} from './fixtures/neroJointCheck';
import {expect,it} from 'vitest';
import {isTcpReport,keyboardMap} from '../src/station/neroTcpContract';
it('accepts only the locked real-feedback contract and rejects claimed hardware capabilities',()=>{
 const d={schema:'vision.api.nero-tcp.v1',source:'STATION',instanceId:'a'.repeat(32),capturedAt:100,
 driveEnabled:[null,false,false,false,false,false,true],jointCheck:jointCheckFixture(100),mode:'LOCKED',reason:'NOT_COMMISSIONED',servoState:'NOT_CONNECTED',
 capabilities:{enable:false,jog:false,hold:false},speedLimits:{linearMin:1,linearMax:100,angularMin:1,angularMax:30},
 defaults:{linearMmS:10,angularDegS:5},frames:['BASE','TOOL'],actualTcp:null};
 expect(isTcpReport(d)).toBe(true);
 expect(isTcpReport({...d,jointCheck:jointCheckFixture(100,true)})).toBe(true);
 expect(isTcpReport({...d,jointCheck:{...jointCheckFixture(100,true),state:'WITHIN_LIMITS'}})).toBe(false);
 expect(isTcpReport({...d,capabilities:{enable:true,jog:false,hold:false}})).toBe(false);
 expect(isTcpReport({...d,driveEnabled:Array(6).fill(false)})).toBe(false);
 expect(isTcpReport({...d,actualTcp:{linear:0,angular:0}})).toBe(false);
 expect(isTcpReport({...d,speedLimits:{...d.speedLimits,linearMax:1000}})).toBe(false);
});
it('maps both directions of each Cartesian axis once',()=>{
 const intents=Object.values(keyboardMap).map(x=>x.axis+':'+x.direction);
 expect(new Set(intents).size).toBe(12);
 expect(keyboardMap.ArrowUp).toEqual({axis:'X',direction:1});
 expect(keyboardMap.KeyQ).toEqual({axis:'ROLL',direction:-1});
});
