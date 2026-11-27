import {record} from './contract';
import {isJointCheck} from './neroJointLimitsContract';
import type {JointCheck} from './neroJointLimitsContract';
export type TcpFrame='BASE'|'TOOL';
export type TcpAxis='X'|'Y'|'Z'|'ROLL'|'PITCH'|'YAW';
export type TcpDeclaration={frame:TcpFrame;linearMmS:number;angularDegS:number};
export type TcpIntent={axis:TcpAxis;direction:-1|1};
export type TcpReport={
 schema:'vision.api.nero-tcp.v1';source:'STATION';instanceId:string;capturedAt:number;
 driveEnabled:(boolean|null)[];jointCheck:JointCheck;mode:'LOCKED';reason:'NOT_COMMISSIONED';servoState:'NOT_CONNECTED';
 capabilities:{enable:false;jog:false;hold:false};
 speedLimits:{linearMin:1;linearMax:100;angularMin:1;angularMax:30};
 defaults:{linearMmS:10;angularDegS:5};frames:['BASE','TOOL'];actualTcp:null;
};
export const keyboardMap:Readonly<Record<string,TcpIntent>>={
 ArrowUp:{axis:'X',direction:1},ArrowDown:{axis:'X',direction:-1},
 ArrowLeft:{axis:'Y',direction:-1},ArrowRight:{axis:'Y',direction:1},
 PageUp:{axis:'Z',direction:1},PageDown:{axis:'Z',direction:-1},
 KeyQ:{axis:'ROLL',direction:-1},KeyE:{axis:'ROLL',direction:1},
 KeyR:{axis:'PITCH',direction:-1},KeyF:{axis:'PITCH',direction:1},
 KeyT:{axis:'YAW',direction:-1},KeyG:{axis:'YAW',direction:1},
};
export function isTcpReport(v:unknown):v is TcpReport{
 return record(v,['schema','source','instanceId','capturedAt','driveEnabled','mode','reason','servoState','capabilities','speedLimits','defaults','frames','actualTcp','jointCheck'])
 &&v.schema==='vision.api.nero-tcp.v1'&&v.source==='STATION'&&typeof v.instanceId==='string'&&/^[a-f0-9]{32}$/.test(v.instanceId)
 &&typeof v.capturedAt==='number'&&Number.isFinite(v.capturedAt)&&v.capturedAt>0&&v.capturedAt<=253402300800
 &&Array.isArray(v.driveEnabled)&&v.driveEnabled.length===7&&v.driveEnabled.every(x=>x===null||typeof x==='boolean')
 &&isJointCheck(v.jointCheck,v.capturedAt)
 &&v.mode==='LOCKED'&&v.reason==='NOT_COMMISSIONED'&&v.servoState==='NOT_CONNECTED'
 &&record(v.capabilities,['enable','jog','hold'])&&v.capabilities.enable===false&&v.capabilities.jog===false&&v.capabilities.hold===false
 &&record(v.speedLimits,['linearMin','linearMax','angularMin','angularMax'])&&v.speedLimits.linearMin===1&&v.speedLimits.linearMax===100&&v.speedLimits.angularMin===1&&v.speedLimits.angularMax===30
 &&record(v.defaults,['linearMmS','angularDegS'])&&v.defaults.linearMmS===10&&v.defaults.angularDegS===5
 &&Array.isArray(v.frames)&&v.frames.length===2&&v.frames[0]==='BASE'&&v.frames[1]==='TOOL'&&v.actualTcp===null;
}
