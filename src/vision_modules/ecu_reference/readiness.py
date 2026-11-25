"""Fail-closed release readiness; hashes do not authenticate reviewers."""
from dataclasses import dataclass
from .models import ReferenceProfile, thaw
from .codec import content_sha256

@dataclass(frozen=True)
class ReadinessReport:
    status: str
    blockers: tuple

def evaluate_readiness(profile, state_id, recipe_id, scope, *, capabilities, calibrations, asset_ids_verified=frozenset()):
    """Public execution readiness always requires an approved release snapshot."""
    return _evaluate(profile, state_id, recipe_id, scope, capabilities=capabilities,
                     calibrations=calibrations, asset_ids_verified=asset_ids_verified, review=False)


def _evaluate_review_requirements(profile, state_id, recipe_id, scope, *, capabilities, calibrations, asset_ids_verified):
    """Internal, non-execution preflight of an unsigned REVIEW_READY candidate.

    An author cannot set the approval flags. The prospective reviewer checks
    the proposed scope and evidence; the actual approval is published later.
    """
    d = profile.data
    m, pr = d['metadata'], d['provenance_release']
    if (m['status'] != 'REVIEW_READY' or m['template_only'] is not False
            or m['approval_scopes'] or m['content_sha256'] is not None
            or pr['release_approval'] is not None or pr['released_snapshot_sha256'] is not None
            or any(x['approved'] for x in d['validation_policies']['readiness_by_scope_and_physical_state'])):
        raise ValueError('unsigned review candidate required')
    return _evaluate(profile, state_id, recipe_id, scope, capabilities=capabilities,
                     calibrations=calibrations, asset_ids_verified=asset_ids_verified, review=True)


def _evaluate(profile, state_id, recipe_id, scope, *, capabilities, calibrations, asset_ids_verified, review):
    if not isinstance(profile, ReferenceProfile): raise ValueError('reference profile required')
    d=thaw(profile.data); blockers=[]
    def need(condition, message):
        if not condition: blockers.append(message)
    m=d['metadata']; pr=d['provenance_release']
    match=lambda x: x['state_id']==state_id and x['recipe_id']==recipe_id and x['scope']==scope
    if not review:
        need(m['schema_version']=='1' and m['status']=='APPROVED', 'profile is not approved V1')
        digest=content_sha256(profile)
        need(m['content_sha256'] == digest, 'content digest missing or mismatched')
        approval=pr['release_approval']
        need(bool(approval and approval['content_sha256']==digest), 'release approval missing or mismatched')
        need(pr['released_snapshot_sha256']==digest, 'released snapshot digest missing or mismatched')
        need(any(match(x) for x in m['approval_scopes']), 'approval scope missing')
    entries=[x for x in d['validation_policies']['readiness_by_scope_and_physical_state'] if match(x) and (review or x['approved'])]
    if review:
        need(len(entries)==1, 'exactly one proposed readiness entry required')
    sources={x['source_id']:x for x in pr['measurement_sources']}
    verified_source=lambda sid: sid in sources and sources[sid]['status']=='VERIFIED'
    need(any(verified_source(x['source_id']) for x in entries), 'verified readiness entry missing')
    states={x['state_id']:x for x in d['physical_states']}; state=states.get(state_id)
    workflows={x['recipe_id']:x for x in d['inspection_workflows']['recipes']}; workflow=workflows.get(recipe_id)
    need(bool(state and state['verified'] and verified_source(state['source_id'])), 'state not verified')
    need(bool(workflow and workflow['state_id']==state_id and workflow['approval_scope']==scope), 'workflow missing or mismatched')
    frame=d['coordinate_systems']['ecu_local']; need(bool(frame['verified'] and frame['origin_description'] and frame['axis_definitions'] and verified_source(frame['datum_reference'])), 'coordinate frame not verified')
    geos=[x for x in d['geometry']['per_physical_state'] if x['state_id']==state_id and state and x['geometry_id']==state['geometry_id']]
    need(any(x['verified'] and verified_source(x['source_id']) for x in geos), 'geometry not verified')
    features={x['feature_id']:x for x in d['connectors_landmarks']['connectors']+d['connectors_landmarks']['landmarks']}
    required=[x for x in d['recognition_rules']['features_to_check'] if x['state_id']==state_id and x['required']]
    need(bool(required), 'required identity evidence missing')
    metric=lambda f: bool(f and f['state_id']==state_id and f['verified'] and verified_source(f['source_id']) and f['position_mm'] is not None and f['uncertainty_mm'] is not None and f['uncertainty_mm'] > 0)
    for x in required:
        f=features.get(x['feature_id']); need(bool(f and f['state_id']==state_id and f['verified'] and verified_source(f['source_id']) and verified_source(x['source_id'])), 'feature not verified: '+x['feature_id'])
    if scope in ('localize','photo_inspection','thermal_relative','thermal_radiometric'):
        need(any(metric(features.get(x['feature_id'])) and verified_source(x['source_id']) for x in required), 'metric identity feature missing')
    if scope in ('localize','photo_inspection','thermal_relative','thermal_radiometric'):
        need(bool(d['localization_rules']['methods']), 'localization methods missing')
        need(bool(d['localization_rules']['required_features']), 'localization features missing')
        for fid in d['localization_rules']['required_features']:
            need(metric(features.get(fid)), 'localization feature not verified: '+fid)
    caps=set(capabilities); needed=set(d['recognition_rules']['required_sensor_capabilities'])
    if scope in ('localize','photo_inspection','thermal_relative','thermal_radiometric'): needed.update(d['localization_rules']['required_sensor_capabilities'])
    policies={x['policy_id']:x for x in d['validation_policies']['policies']}; assets={x['asset_id']:x for x in d['reference_assets']['assets']}; rois={x['roi_id']:x for x in d['pcb_definition']['regions_of_interest']}; boards={x['board_id']:x for x in d['pcb_definition']['boards']}
    views={v['view_id']:v for p in d['photography_recipes']['recipes'] if p['state_id']==state_id and p['recipe_id']==recipe_id for v in p['views']}
    asset_need={x['reference_asset_id'] for x in required if x['reference_asset_id']}
    policy_need=set()
    if scope == 'photo_inspection':
        selected_photos = [
            x for x in d['photography_recipes']['recipes']
            if x['recipe_id'] == recipe_id and x['state_id'] == state_id
        ]
        need(len(selected_photos) == 1, 'selected photography recipe missing')
        need(bool(d['reference_assets']['asset_manifest_revision']),
             'asset manifest revision required')
        policy_need.update(d['photography_recipes']['quality_policy_refs'])
        if len(selected_photos) == 1:
            policy_need.update(selected_photos[0]['quality_policy_refs'])
    if scope in ('localize','photo_inspection','thermal_relative','thermal_radiometric'):
        for pid in (d['recognition_rules']['accepted_policy_ref'], d['localization_rules']['pose_quality_policy_ref']):
            need(bool(pid), 'identity or pose policy missing')
            if pid: policy_need.add(pid)
    roi_need=set()
    if workflow:
        if scope == 'photo_inspection': need(bool(workflow['required_view_ids']), 'required views missing')
        needed.update(workflow['required_capabilities']); asset_need.update(workflow['required_asset_ids']); policy_need.update(workflow['quality_policy_refs'])
        for vid in workflow['required_view_ids']:
            v=views.get(vid)
            need(bool(v), 'required view missing: '+vid)
            if v:
                needed.update(v['required_capabilities']); policy_need.add(v['quality_policy_ref']); roi_need.update(v['roi_refs']); need(verified_source(v['source_id']), 'view source not verified: '+vid)
    thermal=[x for x in d['thermal_recipes']['recipes'] if x['recipe_id']==recipe_id and x['state_id']==state_id]
    if scope.startswith('thermal_'):
        need(bool(thermal), 'thermal recipe missing')
        for t in thermal:
            need(t['mode']==('radiometric' if scope=='thermal_radiometric' else 'relative_intensity'), 'thermal mode mismatch')
            need(t['mode']!='radiometric' or bool(t['required_calibration_refs']), 'radiometric calibration missing')
            needed.update(t['required_capabilities']); roi_need.update(t['roi_refs']); policy_need.add(t['quality_policy_ref'])
            for name in t['required_calibration_refs']: need(name in calibrations, 'calibration missing: '+name)
    for dep in pr['calibration_dependencies']:
        need(dep['name'] in calibrations and (not hasattr(calibrations,'get') or calibrations.get(dep['name'])==dep['revision']), 'calibration missing or revision mismatch: '+dep['name'])
    for cap in sorted(needed-caps): blockers.append('capability missing: '+cap)
    if scope not in ('browse_and_select','verify_identity'): need(bool(asset_need), 'required assets missing')
    for aid in sorted(asset_need):
        a=assets.get(aid); need(bool(a and a['physical_state_id']==state_id and a['verified'] and verified_source(a['source_id']) and aid in asset_ids_verified and any(h['asset_id']==aid for h in pr['asset_hashes'])), 'asset not verified: '+aid)
    for pid in sorted(policy_need):
        p=policies.get(pid); need(bool(p and p['verified'] and p['thresholds'] and all(v > 0 for v in p['thresholds'].values()) and verified_source(p['source_id'])), 'policy not verified: '+pid)
    for rid in sorted(roi_need):
        r=rois[rid]; b=boards[r['board_id']]; need(r['verified'] and b['verified'] and verified_source(r['source_id']) and verified_source(b['source_id']), 'PCB ROI not verified: '+rid)
        if geos:
            x,y,w,h=r['rectangle_xywh_mm']; ex,ey,_=geos[0]['envelope_xyz_mm']; need(x>=0 and y>=0 and x+w<=ex and y+h<=ey, 'ROI outside envelope: '+rid)
    ambiguous=bool(d['identity']['known_indistinguishable_variants'])
    if ambiguous: blockers.append('variant is not unique')
    return ReadinessReport('NOT_READY' if not review and m['status'] != 'APPROVED' else 'AMBIGUOUS' if ambiguous else 'NOT_READY' if blockers else 'REVIEW_READY' if review else 'PASS', tuple(blockers))
