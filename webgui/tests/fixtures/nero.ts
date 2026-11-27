import {NERO_JOINTS,NERO_FAULTS} from '../../src/station/neroContract';
import type {NeroReport} from '../../src/station/neroContract';
export function neroFixture(active=true,now=Date.now()/1000):NeroReport{
 const stamp=now-.1;
 return {schema:'vision.api.nero.v1',source:'STATION',instanceId:'f'.repeat(32),capturedAt:now,model:'AgileX NERO',
  hardwareConnection:'USB_CAN_DETECTED',observer:'ACTIVE',graph:active?'ACTIVE':'NO_NODE',
  node:active?{domain:181,name:'/nero_guarded/agx_arm_ctrl_single_node'}:null,
  joints:active?{stamp,rows:NERO_JOINTS.map((joint,i)=>({joint,positionRad:i*Math.PI/18,velocityRadS:0,torqueNm:.1}))}:null,
  arm:active?{stamp,level:2,controlMode:1,armStatus:6,modeFeedback:1,teachStatus:0,motionStatus:0,trajectoryNumber:0,errorCode:0,
   angleLimit:Array(7).fill(false),communicationFault:Array(7).fill(false)}:null,
  motors:active?{stamp,rows:NERO_JOINTS.map(joint=>({joint,level:0,enabled:false,
   faults:Object.fromEntries(NERO_FAULTS.map(k=>[k,false])) as Record<typeof NERO_FAULTS[number],boolean>,
   rawStatus:0,voltageV:24.1,driverTempC:31,motorTempC:25,currentA:0.1}))}:null,
  parameters:active?{stamp,values:{control_enabled:false,auto_enable:false,physical_hold_enabled:true}}:null,
  can:{stamp,interface:'can0',up:true,state:'ERROR-ACTIVE',bitrate:1000000,rxErrors:0,txErrors:0,rxDropped:0,txDropped:0,rxPackets:100,txPackets:0}};
}
