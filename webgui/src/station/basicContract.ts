/** Authoring-only V2 declaration. Never a Runtime recipe or readiness receipt. */
import {record} from './contract';

export const basicStates = ['closed','pcb_top','pcb_bottom'] as const;
export type BasicStateId=typeof basicStates[number];
export const basicStateLabels:Record<BasicStateId,string>={closed:'Closed ECU',pcb_top:'Exposed PCB top',pcb_bottom:'Exposed PCB bottom'};
export const photoRoles=['label','housing','connectors','pcb_top','pcb_bottom','other'] as const;
export type PhotoRole=typeof photoRoles[number];
export const photoRoleLabels:Record<PhotoRole,string>={label:'ECU label',housing:'Housing',connectors:'Connectors',pcb_top:'PCB top',pcb_bottom:'PCB bottom',other:'Other reference photo'};
export type BasicState={stateId:BasicStateId;dimensionsMm:[number|null,number|null,number|null]};
export type BasicPhoto={sha256:string;mime:'image/jpeg'|'image/png';bytes:number;stateId:BasicStateId;role:PhotoRole};
export type InspectionPreference={template:null|'standard_pcb';overview:boolean;oblique:boolean;details:boolean;customRoi:boolean;notes:string};
export type BasicDeclaration={schema:'vision.ecu-declaration.v2';familyLabel:string;variantLabel:string;states:BasicState[];photos:BasicPhoto[];inspection:InspectionPreference};
export type BasicIdentity={manufacturer:string|null;manufacturer_part_numbers:string[];oem_part_numbers:string[];aliases:string[];displayName:string};
export type BasicPayload={identity:BasicIdentity;declaration:BasicDeclaration};
export const basicMaxPhotos=32;
export function emptyDeclaration(familyLabel='',variantLabel=''):BasicDeclaration{
  return {schema:'vision.ecu-declaration.v2',familyLabel,variantLabel,states:[],photos:[],inspection:{template:null,overview:false,oblique:false,details:false,customRoi:false,notes:''}};
}
export function validIdentityLabel(value:unknown):value is string{
  return typeof value==='string'&&value.length<=64&&/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(value.trim().replace(/ +/g,'_'));
}
function stateId(value:unknown):value is BasicStateId {return basicStates.some(s=>s===value);}
function photoRole(value:unknown):value is PhotoRole {return photoRoles.some(r=>r===value);}
function isText(value:unknown,max:number):value is string{return typeof value==='string'&&Array.from(value).length<=max&&!/\p{C}/u.test(value);}
export function isBasicDeclaration(value:unknown):value is BasicDeclaration{
  if(!record(value,['schema','familyLabel','variantLabel','states','photos','inspection'])||value.schema!=='vision.ecu-declaration.v2'||
    !validIdentityLabel(value.familyLabel)||!validIdentityLabel(value.variantLabel)||!Array.isArray(value.states)||value.states.length>basicStates.length||
    !Array.isArray(value.photos)||value.photos.length>basicMaxPhotos)return false;
  const ids=new Set<BasicStateId>();
  for(const state of value.states){
    if(!record(state,['stateId','dimensionsMm'])||!stateId(state.stateId)||ids.has(state.stateId)||!Array.isArray(state.dimensionsMm)||state.dimensionsMm.length!==3||
       !state.dimensionsMm.every(x=>x===null||(typeof x==='number'&&Number.isFinite(x)&&x>0&&x<=1000000)))return false;
    ids.add(state.stateId);
  }
  const hashes=new Set<string>();
  for(const photo of value.photos){
    if(!record(photo,['sha256','mime','bytes','stateId','role'])||typeof photo.sha256!=='string'||!/^[a-f0-9]{64}$/.test(photo.sha256)||hashes.has(photo.sha256)||
      (photo.mime!=='image/jpeg'&&photo.mime!=='image/png')||typeof photo.bytes!=='number'||!Number.isInteger(photo.bytes)||photo.bytes<1||photo.bytes>2*1024*1024||
      !stateId(photo.stateId)||!ids.has(photo.stateId)||!photoRole(photo.role))return false;
    hashes.add(photo.sha256);
  }
  const i=value.inspection;
  return record(i,['template','overview','oblique','details','customRoi','notes'])&&(i.template===null||i.template==='standard_pcb')&&
    ['overview','oblique','details','customRoi'].every(k=>typeof i[k]==='boolean')&&typeof i.notes==='string'&&i.notes.length<=1024&&isText(i.notes.replace(/\n/g,''),1024);
}
