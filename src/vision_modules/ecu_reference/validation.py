"""Preview contract. Execution validation is deliberately not implemented yet."""

# These are exactly the fields in the accepted architectural template. Its empty
# collections are intentionally the only supported preview values at present.
_SHAPES = {
 'metadata': {'kind','schema_version','template_only','profile_id','family_id','variant_id','profile_revision','display_name','status','approval_scopes','content_sha256'},
 'identity': {'manufacturer','manufacturer_part_numbers','oem_part_numbers','aliases','variant_relations','distinguishing_features','known_indistinguishable_variants','declared_by_operator'},
 'coordinate_systems': {'ecu_local','state_transforms'},
 'geometry': {'per_physical_state','collision_geometry_requires_verified_envelope'},
 'connectors_landmarks': {'connectors','landmarks','variant_disambiguation_uses_physical_features'},
 'reference_assets': {'storage_policy','asset_manifest_revision','assets'},
 'recognition_rules': {'selected_variant_must_be_verified','features_to_check','required_sensor_capabilities','on_ambiguity','on_missing_required_evidence','accepted_policy_ref'},
 'localization_rules': {'required_features','required_sensor_capabilities','pose_output_frame','requires_fresh_tf','requires_current_scene','pose_quality_policy_ref','methods'},
 'pcb_definition': {'boards','regions_of_interest'},
 'photography_recipes': {'recipes','quality_policy_refs'},
 'thermal_recipes': {'modality_optional_by_default','recipes','radiometric_requires_calibration'},
 'inspection_workflows': {'recipes','no_arbitrary_executable_code_in_profile','no_automatic_motion_after_failure'},
 'validation_policies': {'policies','readiness_by_scope_and_physical_state','missing_required_data','variant_not_unique','automatic_variant_substitution'},
 'provenance_release': {'measurement_sources','calibration_dependencies','asset_hashes','release_approval','released_snapshot_sha256','supersedes'},
}


def _validate_template(data):
    if not isinstance(data, dict) or set(data) != set(_SHAPES) | {'physical_states'}:
        raise ValueError('exactly the 15 V1 sections required')
    for section, keys in _SHAPES.items():
        if not isinstance(data[section], dict) or set(data[section]) != keys:
            raise ValueError('unknown or missing fields: ' + section)
    m = data['metadata']
    if m['kind'] != 'ecu_reference_profile' or m['schema_version'] != 'V1-PROPOSED' or m['template_only'] is not True or m['status'] != 'DRAFT':
        raise ValueError('only proposed draft templates currently supported')
    if any(value is not None for key, value in m.items() if key in ('profile_id','family_id','variant_id','profile_revision','display_name','content_sha256')) or m['approval_scopes'] != []:
        raise ValueError('only the unfilled template is currently supported')
    frame = data['coordinate_systems']['ecu_local']
    if not isinstance(frame, dict) or frame != {'origin_description': None, 'datum_reference': None, 'axis_definitions': None, 'handedness': 'right', 'linear_unit': 'mm', 'verified': False}:
        raise ValueError('unsupported frame')
    # No unchecked nested contract can enter even a preview snapshot.
    def check(value):
        if isinstance(value, list) and value:
            raise ValueError('nonempty template collections not yet supported')
        if isinstance(value, dict):
            for item in value.values(): check(item)
    check(data)
    expected = {
      ('identity','declared_by_operator'): True,
      ('geometry','collision_geometry_requires_verified_envelope'): True,
      ('connectors_landmarks','variant_disambiguation_uses_physical_features'): True,
      ('recognition_rules','selected_variant_must_be_verified'): True,
      ('localization_rules','requires_fresh_tf'): True,
      ('localization_rules','requires_current_scene'): True,
      ('thermal_recipes','modality_optional_by_default'): True,
      ('thermal_recipes','radiometric_requires_calibration'): True,
      ('inspection_workflows','no_arbitrary_executable_code_in_profile'): True,
      ('inspection_workflows','no_automatic_motion_after_failure'): True,
      ('validation_policies','automatic_variant_substitution'): False,
    }
    for (section, key), value in expected.items():
        if data[section][key] is not value: raise ValueError('invalid policy: ' + key)
    if data['physical_states'] != []: raise ValueError('unsupported physical states')

# V1 is declarative: every object below has a closed set of fields.
import math
import re
from pathlib import PurePosixPath

_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
_HASH = re.compile(r'^[0-9a-fA-F]{64}$')
_SCOPES = {'browse_and_select', 'verify_identity', 'localize', 'photo_inspection', 'thermal_relative', 'thermal_radiometric'}

def _fail(message):
    raise ValueError(message)

def _obj(v, fields):
    if type(v) is not dict or set(v) != set(fields.split()): _fail('invalid object fields: ' + fields)

def _str(v, nullable=False):
    if v is None and nullable: return
    if type(v) is not str or not v: _fail('expected nonempty string')

def _id(v, nullable=False):
    if v is None and nullable: return
    if type(v) is not str or not _ID.fullmatch(v): _fail('invalid ID')

def _hash(v, nullable=False):
    if v is None and nullable: return
    if type(v) is not str or not _HASH.fullmatch(v): _fail('invalid hash')

def _bool(v):
    if type(v) is not bool: _fail('expected boolean')

def _num(v, positive=False):
    if type(v) not in (int, float) or not math.isfinite(v) or (positive and v <= 0): _fail('invalid number')

def _vec(v, n, positive=False):
    if type(v) is not list or len(v) != n: _fail('invalid vector')
    for x in v: _num(x, positive)

def _quat(v):
    _vec(v, 4)
    if abs(sum(x*x for x in v) - 1) > 1e-6: _fail('invalid quaternion')

def _list(v, check):
    if type(v) is not list: _fail('expected list')
    for x in v: check(x)

def _enum(v, choices):
    if v not in choices or type(v) is not str: _fail('invalid enum')

def _rows(v, fields, checks):
    def row(x):
        _obj(x, fields)
        for k, f in checks.items(): f(x[k])
    _list(v, row)

def _ids(v): _list(v, _id)
def _strings(v): _list(v, _str)
def _nullable(f): return lambda v: None if v is None else f(v)
def _scope(v): _enum(v, _SCOPES)
def _fixed(v, expected):
    if type(v) is not type(expected) or v != expected: _fail('invalid fixed policy')
def _path(v):
    _str(v)
    if '\\' in v or not re.fullmatch(r'[A-Za-z0-9_./-]+', v) or v.startswith('/') or any(x in ('', '.', '..') for x in v.split('/')): _fail('unsafe asset path')

def validate_preview(d):
    if type(d) is not dict or set(d) != set(_SHAPES) | {'physical_states'}: _fail('exactly the 15 V1 sections required')
    for section, keys in _SHAPES.items():
        if type(d[section]) is not dict or set(d[section]) != keys: _fail('unknown or missing fields: ' + section)
    m = d['metadata']
    if m['schema_version'] == 'V1-PROPOSED':
        _validate_template(d)
        # Template constants are part of the contract too.
        for section, key, value in [('reference_assets','storage_policy','controlled_or_private'),('recognition_rules','on_ambiguity','BLOCK_AND_REQUIRE_OPERATOR_REVIEW'),('recognition_rules','on_missing_required_evidence','NOT_READY'),('localization_rules','pose_output_frame','ecu_local'),('validation_policies','missing_required_data','NOT_READY'),('validation_policies','variant_not_unique','AMBIGUOUS')]: _fixed(d[section][key], value)
        return
    _fixed(m['kind'], 'ecu_reference_profile'); _fixed(m['schema_version'], '1'); _fixed(m['template_only'], False)
    for k in ('profile_id','family_id','variant_id','profile_revision'): _id(m[k])
    _str(m['display_name']); _enum(m['status'], {'DRAFT','REVIEW_READY','APPROVED'}); _hash(m['content_sha256'], True)
    trip = {'state_id':_id,'recipe_id':_id,'scope':_scope}
    _rows(m['approval_scopes'], 'state_id recipe_id scope', trip)
    i=d['identity']; _str(i['manufacturer'], True)
    for k in ('manufacturer_part_numbers','oem_part_numbers','aliases'): _strings(i[k])
    # No relation object contract has been defined; reject unchecked relations.
    if i['variant_relations'] != []: _fail('unsupported variant relations')
    for k in ('distinguishing_features','known_indistinguishable_variants'): _ids(i[k])
    _fixed(i['declared_by_operator'], True)
    _rows(d['physical_states'], 'state_id display_name geometry_id required_recipe_ids verified source_id', {'state_id':_id,'display_name':_str,'geometry_id':_nullable(_id),'required_recipe_ids':_ids,'verified':_bool,'source_id':_nullable(_id)})
    c=d['coordinate_systems']; f=c['ecu_local']; _obj(f,'origin_description datum_reference axis_definitions handedness linear_unit verified')
    for k in ('origin_description','axis_definitions'): _str(f[k], True)
    _id(f['datum_reference'], True); _fixed(f['handedness'],'right'); _fixed(f['linear_unit'],'mm'); _bool(f['verified'])
    _rows(c['state_transforms'],'from_state_id to_state_id translation_mm quaternion_xyzw source_id verified', {'from_state_id':_id,'to_state_id':_id,'translation_mm':lambda v:_vec(v,3),'quaternion_xyzw':_quat,'source_id':_id,'verified':_bool})
    g=d['geometry']; _fixed(g['collision_geometry_requires_verified_envelope'],True)
    _rows(g['per_physical_state'],'geometry_id state_id envelope_xyz_mm collision_asset_id source_id uncertainty_mm verified', {'geometry_id':_id,'state_id':_id,'envelope_xyz_mm':lambda v:_vec(v,3,True),'collision_asset_id':_nullable(_id),'source_id':_id,'uncertainty_mm':lambda v:_num(v,True),'verified':_bool})
    cl=d['connectors_landmarks']; _fixed(cl['variant_disambiguation_uses_physical_features'],True)
    _rows(cl['connectors'],'feature_id state_id color position_mm source_id uncertainty_mm required_for_identity verified', {'feature_id':_id,'state_id':_id,'color':_nullable(_str),'position_mm':_nullable(lambda v:_vec(v,3)),'source_id':_id,'uncertainty_mm':_nullable(lambda v:_num(v,True)),'required_for_identity':_bool,'verified':_bool})
    _rows(cl['landmarks'],'feature_id state_id kind position_mm source_id uncertainty_mm verified', {'feature_id':_id,'state_id':_id,'kind':_str,'position_mm':lambda v:_vec(v,3),'source_id':_id,'uncertainty_mm':lambda v:_num(v,True),'verified':_bool})
    a=d['reference_assets']; _fixed(a['storage_policy'],'controlled_or_private'); _id(a['asset_manifest_revision'],True)
    _rows(a['assets'],'asset_id kind relative_path sha256 bytes mime physical_state_id source_id verified privacy_class', {'asset_id':_id,'kind':_str,'relative_path':_path,'sha256':_hash,'bytes':lambda v: _num(v,True) if type(v) is int else _fail('invalid bytes'),'mime':_str,'physical_state_id':_id,'source_id':_id,'verified':_bool,'privacy_class':_str})
    r=d['recognition_rules']; _fixed(r['selected_variant_must_be_verified'],True); _fixed(r['on_ambiguity'],'BLOCK_AND_REQUIRE_OPERATOR_REVIEW'); _fixed(r['on_missing_required_evidence'],'NOT_READY'); _id(r['accepted_policy_ref'],True); _strings(r['required_sensor_capabilities'])
    _rows(r['features_to_check'],'feature_id state_id method required tolerance_mm reference_asset_id source_id', {'feature_id':_id,'state_id':_id,'method':lambda v:_enum(v,{'rgb_landmark','rgbd_landmark','depth_geometry','visual_marking'}),'required':_bool,'tolerance_mm':lambda v:_num(v,True),'reference_asset_id':_nullable(_id),'source_id':_id})
    l=d['localization_rules']; _ids(l['required_features']); _strings(l['required_sensor_capabilities']); _fixed(l['pose_output_frame'],'ecu_local'); _fixed(l['requires_fresh_tf'],True); _fixed(l['requires_current_scene'],True); _id(l['pose_quality_policy_ref'],True); _list(l['methods'],lambda v:_enum(v,{'rgbd_pose','depth_geometry','landmark_registration'}))
    pcb=d['pcb_definition']; _rows(pcb['boards'],'board_id state_id source_id verified',{'board_id':_id,'state_id':_id,'source_id':_id,'verified':_bool})
    _rows(pcb['regions_of_interest'],'roi_id board_id state_id rectangle_xywh_mm source_id verified',{'roi_id':_id,'board_id':_id,'state_id':_id,'rectangle_xywh_mm':lambda v:_rect(v),'source_id':_id,'verified':_bool})
    def view(v):
        _obj(v,'view_id roi_refs camera_goal aim_point_mm working_distance_range_mm required_capabilities quality_policy_ref required source_id')
        _id(v['view_id']); _ids(v['roi_refs']); goal=v['camera_goal']; _obj(goal,'frame translation_mm quaternion_xyzw'); _fixed(goal['frame'],'ecu_local'); _vec(goal['translation_mm'],3); _quat(goal['quaternion_xyzw']); _nullable(lambda x:_vec(x,3))(v['aim_point_mm']); _nullable(_range)(v['working_distance_range_mm']); _strings(v['required_capabilities']); _id(v['quality_policy_ref']); _bool(v['required']); _id(v['source_id'])
    ph=d['photography_recipes']; _ids(ph['quality_policy_refs']); _rows(ph['recipes'],'recipe_id state_id views quality_policy_refs',{'recipe_id':_id,'state_id':_id,'views':lambda v:_list(v,view),'quality_policy_refs':_ids})
    t=d['thermal_recipes']; _fixed(t['modality_optional_by_default'],True); _fixed(t['radiometric_requires_calibration'],True)
    _rows(t['recipes'],'recipe_id state_id roi_refs mode required_calibration_refs quality_policy_ref required_capabilities',{'recipe_id':_id,'state_id':_id,'roi_refs':_ids,'mode':lambda v:_enum(v,{'relative_intensity','radiometric'}),'required_calibration_refs':_ids,'quality_policy_ref':_id,'required_capabilities':_strings})
    w=d['inspection_workflows']; _fixed(w['no_arbitrary_executable_code_in_profile'],True); _fixed(w['no_automatic_motion_after_failure'],True)
    _rows(w['recipes'],'recipe_id state_id scenario_ref required_view_ids required_modules required_capabilities quality_policy_refs required_asset_ids approval_scope',{'recipe_id':_id,'state_id':_id,'scenario_ref':_id,'required_view_ids':_ids,'required_modules':_ids,'required_capabilities':_strings,'quality_policy_refs':_ids,'required_asset_ids':_ids,'approval_scope':_scope})
    p=d['validation_policies']; _fixed(p['missing_required_data'],'NOT_READY'); _fixed(p['variant_not_unique'],'AMBIGUOUS'); _fixed(p['automatic_variant_substitution'],False)
    _rows(p['policies'],'policy_id kind thresholds source_id verified',{'policy_id':_id,'kind':_str,'thresholds':_thresholds,'source_id':_id,'verified':_bool})
    _rows(p['readiness_by_scope_and_physical_state'],'state_id recipe_id scope approved source_id',dict(trip,approved=_bool,source_id=_id))
    pr=d['provenance_release']; _rows(pr['measurement_sources'],'source_id date status instrument datum uncertainty_mm reference',{'source_id':_id,'date':_str,'status':lambda v:_enum(v,{'FIELD_NOTE','MEASURED','VERIFIED'}),'instrument':_str,'datum':_str,'uncertainty_mm':lambda v:_num(v,True),'reference':_str})
    _rows(pr['calibration_dependencies'],'name revision',{'name':_id,'revision':_id}); _rows(pr['asset_hashes'],'asset_id sha256',{'asset_id':_id,'sha256':_hash})
    if pr['release_approval'] is not None:
        _obj(pr['release_approval'],'reviewer_id approved_at reference content_sha256')
        for k in ('reviewer_id','approved_at','reference'): _str(pr['release_approval'][k])
        _hash(pr['release_approval']['content_sha256'])
    _hash(pr['released_snapshot_sha256'],True); _str(pr['supersedes'],True)
    _references(d)

def _rect(v):
    _vec(v,4)
    if v[2] <= 0 or v[3] <= 0: _fail('invalid rectangle')

def _range(v):
    _vec(v,2,True)
    if v[0] > v[1]: _fail('invalid range')

def _thresholds(v):
    if type(v) is not dict: _fail('invalid thresholds')
    for k,x in v.items(): _id(k); _num(x,True)

def _references(d):
    def index(rows, key):
        result = {}
        for row in rows:
            k=row[key]
            if k in result: _fail('duplicate ID: '+k)
            result[k]=row
        return result
    states=index(d['physical_states'],'state_id'); geo=index(d['geometry']['per_physical_state'],'geometry_id')
    features=index(d['connectors_landmarks']['connectors']+d['connectors_landmarks']['landmarks'],'feature_id')
    assets=index(d['reference_assets']['assets'],'asset_id'); boards=index(d['pcb_definition']['boards'],'board_id'); rois=index(d['pcb_definition']['regions_of_interest'],'roi_id')
    policies=index(d['validation_policies']['policies'],'policy_id'); sources=index(d['provenance_release']['measurement_sources'],'source_id')
    workflows=index(d['inspection_workflows']['recipes'],'recipe_id'); photos=index(d['photography_recipes']['recipes'],'recipe_id'); thermals=index(d['thermal_recipes']['recipes'],'recipe_id')
    views=index([v for r in photos.values() for v in r['views']],'view_id')
    calibrations=index(d['provenance_release']['calibration_dependencies'],'name')
    hashes=index(d['provenance_release']['asset_hashes'],'asset_id')
    def ref(v, table):
        if v is not None and v not in table: _fail('unresolved reference: '+v)
    def refs(v, table):
        for x in v: ref(x,table)
    def sourced(rows):
        for x in rows: ref(x['source_id'],sources)
    def state_rows(rows, key='state_id'):
        for x in rows: ref(x[key],states)
    all_sourced=list(states.values())+list(geo.values())+list(features.values())+list(assets.values())+list(boards.values())+list(rois.values())+list(policies.values())+list(views.values())+d['coordinate_systems']['state_transforms']+d['recognition_rules']['features_to_check']+d['validation_policies']['readiness_by_scope_and_physical_state']
    sourced(all_sourced); ref(d['coordinate_systems']['ecu_local']['datum_reference'],sources)
    for rows in (geo.values(),features.values(),boards.values(),rois.values(),photos.values(),thermals.values(),workflows.values(),d['recognition_rules']['features_to_check'],d['validation_policies']['readiness_by_scope_and_physical_state'],d['metadata']['approval_scopes']): state_rows(rows)
    state_rows(assets.values(),'physical_state_id')
    for x in d['coordinate_systems']['state_transforms']: ref(x['from_state_id'],states); ref(x['to_state_id'],states)
    for x in states.values():
        ref(x['geometry_id'],geo); refs(x['required_recipe_ids'],workflows)
        if x['geometry_id'] and geo[x['geometry_id']]['state_id'] != x['state_id']: _fail('geometry state mismatch')
    for x in geo.values(): ref(x['collision_asset_id'],assets)
    for x in rois.values():
        ref(x['board_id'],boards)
        if boards[x['board_id']]['state_id'] != x['state_id']: _fail('ROI state mismatch')
    for x in d['recognition_rules']['features_to_check']:
        ref(x['feature_id'],features); ref(x['reference_asset_id'],assets)
        if features[x['feature_id']]['state_id'] != x['state_id']: _fail('feature state mismatch')
    refs(d['identity']['distinguishing_features'],features); refs(d['localization_rules']['required_features'],features)
    ref(d['recognition_rules']['accepted_policy_ref'],policies); ref(d['localization_rules']['pose_quality_policy_ref'],policies)
    refs(d['photography_recipes']['quality_policy_refs'],policies)
    for x in photos.values():
        refs(x['quality_policy_refs'],policies)
        for v in x['views']:
            refs(v['roi_refs'],rois); ref(v['quality_policy_ref'],policies)
            if any(rois[y]['state_id'] != x['state_id'] for y in v['roi_refs']): _fail('view state mismatch')
    for x in thermals.values():
        refs(x['roi_refs'],rois); refs(x['required_calibration_refs'],calibrations); ref(x['quality_policy_ref'],policies)
        if any(rois[y]['state_id'] != x['state_id'] for y in x['roi_refs']): _fail('thermal state mismatch')
    for x in workflows.values():
        refs(x['required_view_ids'],views); refs(x['quality_policy_refs'],policies); refs(x['required_asset_ids'],assets)
        if len(set(x['required_view_ids'])) != len(x['required_view_ids']): _fail('duplicate required view')
        if x['approval_scope'] == 'photo_inspection':
            photo = photos.get(x['recipe_id'])
            if not photo or photo['state_id'] != x['state_id']: _fail('workflow photo recipe mismatch')
            if any(not any(v['view_id'] == y for v in photo['views']) for y in x['required_view_ids']): _fail('workflow view recipe mismatch')
        elif x['approval_scope'].startswith('thermal_'):
            thermal = thermals.get(x['recipe_id'])
            mode = 'radiometric' if x['approval_scope'] == 'thermal_radiometric' else 'relative_intensity'
            if not thermal or thermal['state_id'] != x['state_id'] or thermal['mode'] != mode: _fail('workflow thermal recipe mismatch')
        elif any(not any(v['view_id']==y and p['state_id']==x['state_id'] for p in photos.values() for v in p['views']) for y in x['required_view_ids']): _fail('workflow view state mismatch')
        if any(assets[y]['physical_state_id'] != x['state_id'] for y in x['required_asset_ids']): _fail('workflow asset state mismatch')
    for x in d['metadata']['approval_scopes']+d['validation_policies']['readiness_by_scope_and_physical_state']:
        ref(x['recipe_id'],workflows)
        if workflows[x['recipe_id']]['state_id'] != x['state_id'] or workflows[x['recipe_id']]['approval_scope'] != x['scope']: _fail('scope mismatch')
    for x in hashes.values():
        ref(x['asset_id'],assets)
        if x['sha256'].lower() != assets[x['asset_id']]['sha256'].lower(): _fail('asset hash mismatch')
