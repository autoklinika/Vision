import {record} from './contract';
export type JointLimitState='UNKNOWN'|'WITHIN_LIMITS'|'OUTSIDE_LIMITS';
export type JointLimitRow={joint:string;positionRad:number|null;sdkRad:[number,number];modelRad:[number,number];state:JointLimitState};
export type JointCheck={reference:'NERO_V121_5051114';stamp:number|null;state:JointLimitState;rows:JointLimitRow[]};
const finite=(x:unknown):x is number=>typeof x==='number'&&Number.isFinite(x);
const limits=(v:unknown):v is [number,number]=>Array.isArray(v)&&v.length===2&&finite(v[0])&&finite(v[1])&&v[0]<v[1]&&Math.max(...v.map(Math.abs))<=Math.PI;
export function isJointCheck(v:unknown,now:number):v is JointCheck{
 if(!record(v,['reference','stamp','state','rows'])||v.reference!=='NERO_V121_5051114'||
    !(v.stamp===null||finite(v.stamp)&&v.stamp>0&&v.stamp<=now&&now-v.stamp<=2.5)||
    !Array.isArray(v.rows)||v.rows.length!==7)return false;
 const rows=v.rows;
 for(let i=0;i<7;i++){
   const r:unknown=rows[i];
   if(!record(r,['joint','positionRad','sdkRad','modelRad','state'])||r.joint!=='joint'+(i+1)||!limits(r.sdkRad)||!limits(r.modelRad))return false;
   const q=r.positionRad;
   if(v.stamp===null?q!==null:!finite(q)||Math.abs(q)>100)return false;
   const expected=q===null?'UNKNOWN':finite(q)&&q>=Math.max(r.sdkRad[0],r.modelRad[0])&&q<=Math.min(r.sdkRad[1],r.modelRad[1])?'WITHIN_LIMITS':'OUTSIDE_LIMITS';
   if(r.state!==expected)return false;
 }
 return v.state===(rows.some(r=>r.state==='OUTSIDE_LIMITS')?'OUTSIDE_LIMITS':rows.some(r=>r.state==='UNKNOWN')?'UNKNOWN':'WITHIN_LIMITS');
}
