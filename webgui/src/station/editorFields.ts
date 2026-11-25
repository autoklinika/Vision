/** Presentation schema for the accepted reference V1 wire document.
 * This describes controls/labels, not execution or approval rules.
 * Core's load_json, reference checks and readiness remain authoritative.
 */
import type {LibrarySectionName} from '../api/libraryContract';
import {libraryScopes,librarySections} from '../api/libraryContract';
import type {DraftDocument} from './draftContract';
import {identifier,referenceIdentifier} from './draftContract';

export type RefKind = 'state'|'source'|'geometry'|'feature'|'asset'|'board'|'roi'|'policy'|'recipe'|'view'|'calibration';
type Base={label:string;optional?:boolean;help?:string};
export type Field = Base & (
  {kind:'text';placeholder?:string;max?:number;id?:'reference'|'library'} |
  {kind:'number';unit?:string;positive?:boolean;integer?:boolean} |
  {kind:'bool'} |
  {kind:'enum';options:readonly string[]} |
  {kind:'ref';target:RefKind} |
  {kind:'list';item:Field} |
  {kind:'vector';components:readonly string[];unit?:string;positive?:boolean} |
  {kind:'object';fields:Fields} |
  {kind:'rows';fields:Fields;title:string} |
  {kind:'thresholds'} |
  {kind:'locked';initial?:unknown}
);
export type Fields=Record<string,Field>;
type Section={title:string;description:string;field:Field};
const text=(label:string,options:Omit<Extract<Field,{kind:'text'}>,'kind'|'label'>={}):Field=>({kind:'text',label,...options});
const id=(label:string,optional=false):Field=>text(label,{id:'reference',optional,max:128,placeholder:'Stable identifier'});
const libraryId=(label:string):Field=>text(label,{id:'library',max:64,placeholder:'Stable identifier',help:'Up to 64 ASCII letters, digits, _ or -; start with a letter or digit.'});
const num=(label:string,unit?:string,positive=false,optional=false,integer=false):Field=>({kind:'number',label,unit,positive,optional,integer});
const bool=(label:string,help?:string):Field=>({kind:'bool',label,help});
const locked=(label:string,initial?:unknown,help?:string):Field=>({kind:'locked',label,initial,help});
const choice=(label:string,options:readonly string[],optional=false):Field=>({kind:'enum',label,options,optional});
const ref=(label:string,target:RefKind,optional=false):Field=>({kind:'ref',label,target,optional});
const list=(label:string,item:Field):Field=>({kind:'list',label,item});
const refs=(label:string,target:RefKind):Field=>list(label,ref('Reference',target));
const strings=(label:string):Field=>list(label,text('Value'));
const obj=(label:string,fields:Fields):Field=>({kind:'object',label,fields});
const rows=(label:string,title:string,fields:Fields):Field=>({kind:'rows',label,title,fields});
const xyz=(label:string,optional=false,positive=false):Field=>({kind:'vector',label,components:['X','Y','Z'],unit:'mm',optional,positive});
const quat=(label:string):Field=>({kind:'vector',label,components:['X','Y','Z','W'],help:'Quaternion in XYZW order; Core checks normalization.'});
const uncertainty=(optional=false)=>num('Measurement uncertainty','mm',true,optional);
const source=(optional=false)=>ref('Measurement source','source',optional);
const verified=()=>bool('Evidence verified (declaration)','Only mark after examining the actual source. This is not profile approval.');
const state=()=>ref('Physical state','state');
const recipeFields:Fields={recipe_id:id('Recipe ID'),state_id:state()};
const policy=()=>ref('Quality policy','policy');
const viewFields:Fields={
  view_id:id('View ID'),roi_refs:refs('PCB regions','roi'),
  camera_goal:obj('Camera goal in ECU coordinates',{frame:locked('Frame','ecu_local'),translation_mm:xyz('Camera position'),quaternion_xyzw:quat('Camera orientation')}),
  aim_point_mm:xyz('Aim point',true),
  working_distance_range_mm:{kind:'vector',label:'Working distance range',components:['Minimum','Maximum'],unit:'mm',positive:true,optional:true},
  required_capabilities:strings('Required capabilities'),quality_policy_ref:policy(),required:bool('Required view'),source_id:source(),
};
export const editorSections:Record<LibrarySectionName,Section>={
  metadata:{title:'Profile identity',description:'Identifiers and revision are fixed for this saved draft. Clone a revision to make a new identity.',field:obj('Metadata',{
    kind:locked('Document type'),schema_version:locked('Schema version'),template_only:locked('Template only'),
    profile_id:locked('Profile ID'),family_id:locked('Family'),variant_id:locked('Variant'),profile_revision:locked('Revision'),
    display_name:text('Display name',{max:160}),status:locked('Status'),approval_scopes:locked('Approved scopes'),content_sha256:locked('Release digest'),
  })},
  identity:{title:'Manufacturer & identity',description:'Declare identifiers and distinguishing features, without guessing an ECU type.',field:obj('Identity',{
    manufacturer:text('Manufacturer',{optional:true}),manufacturer_part_numbers:strings('Manufacturer part numbers'),oem_part_numbers:strings('OEM part numbers'),
    aliases:strings('Aliases'),variant_relations:locked('Variant relations',[],'Reserved by the V1 schema.'),
    distinguishing_features:refs('Distinguishing features','feature'),known_indistinguishable_variants:list('Known indistinguishable variants',id('Variant ID')),
    declared_by_operator:locked('Declared by operator',true),
  })},
  physical_states:{title:'Physical states',description:'Define each physical configuration. Geometry and recipe references can be filled after those rows exist.',field:rows('Physical states','physical state',{
    state_id:libraryId('State ID'),display_name:text('State name',{max:160}),geometry_id:ref('Geometry','geometry',true),
    required_recipe_ids:refs('Required inspection recipes','recipe'),verified:verified(),source_id:source(true),
  })},
  coordinate_systems:{title:'Coordinate systems',description:'Define the local datum, axis directions and transformations between states. All positions are in millimetres.',field:obj('Coordinates',{
    ecu_local:obj('ECU local frame',{origin_description:text('Origin description',{optional:true}),datum_reference:ref('Datum measurement source','source',true),axis_definitions:text('Axis definitions',{optional:true}),handedness:locked('Handedness','right'),linear_unit:locked('Linear unit','mm'),verified:verified()}),
    state_transforms:rows('State transforms','transform',{from_state_id:ref('From state','state'),to_state_id:ref('To state','state'),translation_mm:xyz('Translation'),quaternion_xyzw:quat('Rotation'),source_id:source(),verified:verified()}),
  })},
  geometry:{title:'Envelope & geometry',description:'Enter measured maximum X/Y/Z dimensions including protrusions. Values are not inferred from field notes.',field:obj('Geometry',{
    per_physical_state:rows('Envelopes by state','envelope',{geometry_id:id('Geometry ID'),state_id:state(),envelope_xyz_mm:xyz('Maximum envelope',false,true),collision_asset_id:ref('Collision geometry asset','asset',true),source_id:source(),uncertainty_mm:uncertainty(),verified:verified()}),
    collision_geometry_requires_verified_envelope:locked('Verified envelope required',true),
  })},
  connectors_landmarks:{title:'Connectors & landmarks',description:'Describe measurable distinguishing features in the ECU-local frame.',field:obj('Features',{
    connectors:rows('Connectors','connector',{feature_id:id('Feature ID'),state_id:state(),color:text('Connector colour',{optional:true}),position_mm:xyz('Position',true),source_id:source(),uncertainty_mm:uncertainty(true),required_for_identity:bool('Required for identity'),verified:verified()}),
    landmarks:rows('Landmarks','landmark',{feature_id:id('Feature ID'),state_id:state(),kind:text('Landmark type'),position_mm:xyz('Position'),source_id:source(),uncertainty_mm:uncertainty(),verified:verified()}),
    variant_disambiguation_uses_physical_features:locked('Physical features required',true),
  })},
  reference_assets:{title:'Reference materials',description:'Declare reference materials with source, state, MIME and SHA-256. Imported images remain unverified until evidence is reviewed.',field:obj('Materials',{
    storage_policy:locked('Storage policy','controlled_or_private'),asset_manifest_revision:id('Manifest revision',true),
    assets:rows('Reference assets','asset',{asset_id:id('Asset ID'),kind:choice('Material type',['photo','image','thermal','drawing','collision_geometry']),relative_path:text('Controlled relative path'),sha256:text('SHA-256',{max:64}),bytes:num('File size','bytes',true,false,true),mime:text('MIME type'),physical_state_id:state(),source_id:source(),verified:verified(),privacy_class:choice('Privacy class',['private','controlled'])}),
  })},
  recognition_rules:{title:'Identity verification',description:'Select required features, reference materials and tolerances. Core determines identity validity.',field:obj('Recognition',{
    selected_variant_must_be_verified:locked('Selected variant must be verified',true),
    features_to_check:rows('Feature checks','feature check',{feature_id:ref('Feature','feature'),state_id:state(),method:choice('Method',['rgb_landmark','rgbd_landmark','depth_geometry','visual_marking']),required:bool('Required check'),tolerance_mm:num('Tolerance','mm',true),reference_asset_id:ref('Reference asset','asset',true),source_id:source()}),
    required_sensor_capabilities:strings('Required sensor capabilities'),on_ambiguity:locked('On ambiguity','BLOCK_AND_REQUIRE_OPERATOR_REVIEW'),on_missing_required_evidence:locked('Missing evidence','NOT_READY'),accepted_policy_ref:ref('Identity policy','policy',true),
  })},
  localization_rules:{title:'Localization',description:'Define features, methods and pose policy. No live sensor acquisition occurs in the editor.',field:obj('Localization',{
    required_features:refs('Required features','feature'),required_sensor_capabilities:strings('Required sensor capabilities'),
    pose_output_frame:locked('Pose frame','ecu_local'),requires_fresh_tf:locked('Fresh TF required',true),requires_current_scene:locked('Current scene required',true),
    pose_quality_policy_ref:ref('Pose quality policy','policy',true),methods:list('Methods',choice('Method',['rgbd_pose','depth_geometry','landmark_registration'])),
  })},
  pcb_definition:{title:'PCB & regions of interest',description:'Add boards and rectangular inspection regions in ECU-local coordinates (X, Y, width, height).',field:obj('PCB',{
    boards:rows('Boards','board',{board_id:id('Board ID'),state_id:state(),source_id:source(),verified:verified()}),
    regions_of_interest:rows('Regions of interest','region',{roi_id:id('Region ID'),board_id:ref('Board','board'),state_id:state(),rectangle_xywh_mm:{kind:'vector',label:'Rectangle',components:['X','Y','Width','Height'],unit:'mm'},source_id:source(),verified:verified()}),
  })},
  photography_recipes:{title:'Photography recipes',description:'Define desired camera poses, regions, working distance and quality requirements. These are draft targets, not commands.',field:obj('Photography',{
    recipes:rows('Photography recipes','photo recipe',{...recipeFields,views:rows('Camera views','camera view',viewFields),quality_policy_refs:refs('Recipe quality policies','policy')}),
    quality_policy_refs:refs('Global photography quality policies','policy'),
  })},
  thermal_recipes:{title:'Thermal recipes',description:'Optional thermal reference definitions. Radiometric work requires its calibration evidence.',field:obj('Thermal',{
    modality_optional_by_default:locked('Optional by default',true),recipes:rows('Thermal recipes','thermal recipe',{...recipeFields,roi_refs:refs('PCB regions','roi'),mode:choice('Thermal mode',['relative_intensity','radiometric']),required_calibration_refs:refs('Calibration dependencies','calibration'),quality_policy_ref:policy(),required_capabilities:strings('Required capabilities')}),
    radiometric_requires_calibration:locked('Radiometric calibration required',true),
  })},
  inspection_workflows:{title:'Inspection workflows',description:'Select the declarative recipe and existing reference IDs. Core owns execution and sequencing.',field:obj('Workflows',{
    recipes:rows('Inspection recipes','inspection recipe',{...recipeFields,recipe_id:libraryId('Recipe ID'),scenario_ref:id('Scenario reference'),required_view_ids:refs('Required views','view'),required_modules:list('Required modules',id('Module ID')),required_capabilities:strings('Required capabilities'),quality_policy_refs:refs('Quality policies','policy'),required_asset_ids:refs('Required assets','asset'),approval_scope:choice('Requested scope',libraryScopes)}),
    no_arbitrary_executable_code_in_profile:locked('No executable profile code',true),no_automatic_motion_after_failure:locked('No automatic motion after failure',true),
  })},
  validation_policies:{title:'Validation policies',description:'Describe measurable thresholds and requested review scopes. Approval flags cannot be edited here.',field:obj('Policies',{
    policies:rows('Policies','policy',{policy_id:id('Policy ID'),kind:text('Policy type'),thresholds:{kind:'thresholds',label:'Named numeric thresholds',help:'Use the metric name and units agreed for this policy. Core interprets the policy; no default value is assumed.'},source_id:source(),verified:verified()}),
    readiness_by_scope_and_physical_state:rows('Proposed scopes','proposed scope',{state_id:state(),recipe_id:ref('Inspection recipe','recipe'),scope:choice('Scope',libraryScopes),approved:locked('Approved',false,'Independent release review only.'),source_id:source()}),
    missing_required_data:locked('Missing required data','NOT_READY'),variant_not_unique:locked('Non-unique variant','AMBIGUOUS'),automatic_variant_substitution:locked('Automatic substitution',false),
  })},
  provenance_release:{title:'Sources, calibration & release',description:'Add measurement provenance first so other sections can refer to it. Source status is a declaration, not an independent approval.',field:obj('Provenance',{
    measurement_sources:rows('Measurement sources','source',{source_id:id('Source ID'),date:text('Measurement date',{placeholder:'YYYY-MM-DD'}),status:choice('Source status',['FIELD_NOTE','MEASURED','VERIFIED']),instrument:text('Instrument / method'),datum:text('Datum'),uncertainty_mm:uncertainty(),reference:text('Evidence reference')}),
    calibration_dependencies:rows('Calibration dependencies','calibration',{name:id('Calibration name'),revision:id('Calibration revision')}),
    asset_hashes:rows('Asset manifest hashes','asset hash',{asset_id:ref('Asset','asset'),sha256:text('SHA-256',{max:64})}),
    release_approval:locked('Release approval',null),released_snapshot_sha256:locked('Released digest',null),supersedes:text('Supersedes reference',{optional:true}),
  })},
};

export type FormDocument=DraftDocument;
export type Row=Record<string,unknown>;
export function row(value:unknown):Row {
  if (value!==null&&typeof value==='object'&&!Array.isArray(value)) return value as Row;
  throw new Error('Unexpected document structure.');
}
export function array(value:unknown):unknown[] {
  if (Array.isArray(value)) return value;
  throw new Error('Unexpected list structure.');
}
function exactKeys(value:Row,fields:Fields) {
  if (Object.keys(value).length!==Object.keys(fields).length||!Object.keys(fields).every(k=>Object.hasOwn(value,k))) {
    throw new Error('Unsupported fields in this V1 form. Reopen with a compatible editor.');
  }
}
export function emptyValue(field:Field):unknown {
  if(field.kind==='locked') return field.initial;
  if(field.kind==='bool') return false;
  if(field.kind==='object') return emptyRow(field.fields);
  if(field.kind==='rows'||field.kind==='list'||field.kind==='thresholds') return [];
  if(field.optional) return null;
  if(field.kind==='vector') return field.components.map(()=>'');
  return '';
}
export function emptyRow(fields:Fields):Row {
  return Object.fromEntries(Object.entries(fields).map(([key,f])=>[key,emptyValue(f)]));
}
function hydrate(field:Field,value:unknown):unknown {
  if(field.kind==='object') {
    const data=row(value);exactKeys(data,field.fields);
    return Object.fromEntries(Object.entries(field.fields).map(([k,f])=>[k,hydrate(f,data[k])]));
  }
  if(field.kind==='rows') return array(value).map(v=>hydrate({kind:'object',label:field.label,fields:field.fields},v));
  if(field.kind==='list') return array(value).map(v=>hydrate(field.item,v));
  if(field.kind==='thresholds') return Object.entries(row(value)).map(([name,v])=>({name,value:String(v)}));
  if(field.kind==='number') {if(value===null&&field.optional)return null;if(typeof value!=='number'||!Number.isFinite(value))throw new Error('Unexpected numeric field.');return String(value);}
  if(field.kind==='vector') {if(value===null&&field.optional)return null;const v=array(value);if(v.length!==field.components.length||v.some(x=>typeof x!=='number'||!Number.isFinite(x)))throw new Error('Unexpected vector.');return v.map(String);}
  return value;
}
export function hydrateDocument(document:DraftDocument):FormDocument {
  return Object.fromEntries(librarySections.map(key=>[key,hydrate(editorSections[key].field,document[key])])) as FormDocument;
}
function fail(path:string,reason:string):never {throw new Error(path+': '+reason);}
function numeric(value:unknown,path:string,positive=false,integer=false):number {
  const text=typeof value==='string'?value.trim():typeof value==='number'?String(value):'';
  if(!/^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$/.test(text)) return fail(path,'enter a number (decimal point or comma).');
  const n=Number(text.replace(',','.'));
  if(!Number.isFinite(n)||Math.abs(n)>1e9||(positive&&n<=0)||(integer&&!Number.isSafeInteger(n))) return fail(path,'number outside the supported range.');
  return n;
}
function serialize(field:Field,value:unknown,path:string):unknown {
  if(field.kind==='locked') return value;
  if(field.optional&&(value===null||value==='')) return null;
  switch(field.kind) {
    case 'text':
    case 'enum':
    case 'ref': {
      if(typeof value!=='string'||!value.trim()) return fail(path,'required value missing.');
      if(field.kind==='text'&&field.id) {
        const valid=field.id==='library'?identifier(value):referenceIdentifier(value);
        if(!valid) return fail(path,field.id==='library'
          ?'use up to 64 ASCII letters, digits, _ or -; start with a letter or digit.'
          :'use up to 128 ASCII letters, digits, _, . or -; start with a letter or digit.');
      }
      if(field.kind==='text'&&value.length>(field.max??4096)) return fail(path,'text too long.');
      // Preserve existing enum/reference values; Core rejects unsupported or
      // unresolved values. The form never substitutes a different identifier.
      return value;
    }
    case 'number': return numeric(value,path,field.positive,field.integer);
    case 'bool': if(typeof value!=='boolean')return fail(path,'checkbox value required.');return value;
    case 'vector': {
      const values=array(value);
      if(values.length!==field.components.length)return fail(path,'invalid vector length.');
      return values.map((v,i)=>numeric(v,path+' / '+field.components[i],field.positive));
    }
    case 'list': return array(value).map((v,i)=>serialize(field.item,v,path+' #'+(i+1)));
    case 'rows': return array(value).map((v,i)=>serialize({kind:'object',label:field.title,fields:field.fields},v,path+' #'+(i+1)));
    case 'object': {
      const data=row(value);exactKeys(data,field.fields);
      return Object.fromEntries(Object.entries(field.fields).map(([k,f])=>[k,serialize(f,data[k],path+' / '+f.label)]));
    }
    case 'thresholds': {
      const result: [string,number][]=[];const seen=new Set<string>();
      for(const v of array(value)) {
        const r=row(v);const name=r.name;
        if(typeof name!=='string'||!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(name)||seen.has(name)) return fail(path,'each metric needs a unique identifier.');
        seen.add(name);result.push([name,numeric(r.value,path+' / '+name,true)]);
      }
      return Object.fromEntries(result);
    }
  }
}
export function serializeDocument(document:FormDocument):string {
  const payload=Object.fromEntries(librarySections.map(key=>[key,serialize(editorSections[key].field,document[key],editorSections[key].title)]));
  const raw=JSON.stringify(payload);
  // Core uses the canonical escaped ASCII JSON byte budget.
  const ascii=raw.replace(/[\u0080-\uffff]/g,c=>'\\u'+c.charCodeAt(0).toString(16).padStart(4,'0'));
  if(ascii.length>65536)throw new Error('Editor document exceeds 64 KiB.');
  return raw;
}
export type ReferenceOption={value:string;label:string};
export function referenceOptions(doc:FormDocument,target:RefKind):ReferenceOption[] {
  const object=(key:LibrarySectionName)=>row(doc[key]);
  const collection=(section:LibrarySectionName,key:string)=>array(object(section)[key]).map(row);
  const entries=(items:Row[],key:string,label?:string)=>items.flatMap(item=>{
    const value=item[key];
    if(typeof value!=='string'||!value.trim())return [];
    const title=label&&typeof item[label]==='string'&&item[label]?String(item[label])+' ('+value+')':value;
    return [{value,label:title}];
  });
  let options:ReferenceOption[];
  switch(target) {
    case 'state':options=entries(array(doc.physical_states).map(row),'state_id','display_name');break;
    case 'source':options=entries(collection('provenance_release','measurement_sources'),'source_id','instrument');break;
    case 'geometry':options=entries(collection('geometry','per_physical_state'),'geometry_id');break;
    case 'feature':options=entries([...collection('connectors_landmarks','connectors'),...collection('connectors_landmarks','landmarks')],'feature_id');break;
    case 'asset':options=entries(collection('reference_assets','assets'),'asset_id');break;
    case 'board':options=entries(collection('pcb_definition','boards'),'board_id');break;
    case 'roi':options=entries(collection('pcb_definition','regions_of_interest'),'roi_id');break;
    case 'policy':options=entries(collection('validation_policies','policies'),'policy_id');break;
    case 'recipe':options=entries(collection('inspection_workflows','recipes'),'recipe_id');break;
    case 'view':options=entries(collection('photography_recipes','recipes').flatMap(r=>array(r.views).map(row)),'view_id');break;
    case 'calibration':options=entries(collection('provenance_release','calibration_dependencies'),'name');break;
  }
  return [...new Map(options.map(o=>[o.value,o])).values()];
}
