import type {JointCheck,JointLimitRow} from '../../src/station/neroJointLimitsContract';
const sdk=[[-2.705261,2.705261],[-1.74533,1.74533],[-2.757621,2.757621],[-1.012291,2.146755],[-2.757621,2.757621],[-.733039,.872665],[-1.570797,1.570797]];
const model=[[-2.70526,2.70526],[-1.74,1.74],[-2.75,2.75],[-1.01,2.14],[-2.75,2.75],[-.7330383,.8726646],[-1.5707963,1.5707963]];
export function jointCheckFixture(stamp:number,outside=false):JointCheck{
 const rows:JointLimitRow[]=sdk.map((s,i)=>({joint:'joint'+(i+1),positionRad:outside&&i===3?126.322*Math.PI/180:0,sdkRad:s as [number,number],modelRad:model[i] as [number,number],state:outside&&i===3?'OUTSIDE_LIMITS':'WITHIN_LIMITS'}));
 return {reference:'NERO_V121_5051114',stamp,state:outside?'OUTSIDE_LIMITS':'WITHIN_LIMITS',rows};
}
