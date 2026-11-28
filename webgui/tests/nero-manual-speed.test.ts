import {expect,it} from 'vitest';
import {manualSpeedLimits,displayedManualSpeed} from '../src/station/neroManualContract';
import type {ManualStatus} from '../src/station/neroManualContract';

const status:ManualStatus={state:'IDLE',reason:'NO_SESSION',driveEnabled:Array(7).fill(false),
 pipelineReady:false,enableAvailable:false,jogAvailable:false,holdAvailable:false,
 linearMax:5,angularMax:2};

it('uses owner limits rather than the old draft limits',()=>{
 expect(manualSpeedLimits(status)).toEqual({linearMax:5,angularMax:2});
 expect(displayedManualSpeed(10,5,status)).toEqual({linear:5,angular:2});
 expect(displayedManualSpeed(3,1,status)).toEqual({linear:3,angular:1});
});
it('supports a minimum-only envelope without expanding it',()=>{
 expect(displayedManualSpeed(10,5,{...status,linearMax:1,angularMax:1})).toEqual({linear:1,angular:1});
});
it('retains the declared keyboard practice range without an owner',()=>{
 expect(manualSpeedLimits(null)).toEqual({linearMax:100,angularMax:30});
 expect(displayedManualSpeed(25,10,null)).toEqual({linear:25,angular:10});
});
