"""Bind approved declarative references to approved Core ECU records, offline."""
from dataclasses import dataclass, replace
from .assets import AssetStore
from .library import ReferenceLibrary
from .models import ReferenceProfile
from .readiness import evaluate_readiness, _evaluate_review_requirements
from .codec import content_sha256
from .releases import ReferenceReleaseStore
from vision_modules.ecu_profiles import to_core_approved, record_sha256
from vision_core.extensions import ModuleRegistry, ScenarioSpec
from vision_core.workflow import STAGES, CHECKS, Workflow
from vision_core.profiles import PROFILE_KINDS

EPSILON = 1e-6

@dataclass(frozen=True)
class ExecutionBundle:
    core_profile: object
    record_sha256: str
    reference_sha256: str
    asset_hashes: tuple
    physical_state: str
    recipe: str
    required_capabilities: frozenset
    modules: tuple
    scenario_spec: object
    qa_policy_refs: tuple

def _scenario(scenario, registry, modules, scenario_ref):
    if not isinstance(scenario, ScenarioSpec) or not isinstance(registry, ModuleRegistry): raise ValueError('NOT_READY: scenario and module registry required')
    if scenario.scenario_id != scenario_ref or set(scenario.required_module_ids) != set(modules): raise ValueError('NOT_READY: scenario modules mismatch')
    specs = {s.stage_id: s for s in scenario.stages}
    resolved = {m: registry.resolve(m) for m in modules}
    if any(m.profile_kind in PROFILE_KINDS for m in resolved.values()): raise ValueError('NOT_READY: module profile conflict')
    for i, name in enumerate(STAGES):
        s = specs.get(name)
        if s is None or s.module_id is not None or not CHECKS[name] <= s.checks or (i and STAGES[i-1] not in s.dependencies): raise ValueError('NOT_READY: invalid builtin stage chain')
    for s in scenario.stages:
        if s.stage_id not in STAGES:
            m = resolved.get(s.module_id)
            if m is None or s.stage_id not in m.stage_ids or 'S03' not in Workflow._ancestors(s.stage_id, specs) or s.stage_id not in Workflow._ancestors('S11', specs): raise ValueError('NOT_READY: invalid module stage')
    if set(resolved) != {s.module_id for s in scenario.stages if s.module_id}: raise ValueError('NOT_READY: unused module')
    for mid, m in resolved.items():
        if not set(m.required_stage_ids) <= {s.stage_id for s in scenario.stages if s.module_id == mid}: raise ValueError('NOT_READY: missing module stage')
    return tuple(resolved[mid] for mid in modules)

def compile_profile(profile, physical_state, recipe, record, catalog, release_store, calibrations, *, capabilities=None, asset_store=None, reference_release_store=None, library=None, module_registry=None, scenario_spec=None):
    if not isinstance(profile, ReferenceProfile): raise ValueError('reference profile required')
    d = profile.data; m = d['metadata']
    if m['status'] != 'APPROVED' or m['template_only'] is not False: raise ValueError('NOT_READY: approved reference required')
    if not isinstance(asset_store, AssetStore) or not isinstance(reference_release_store, ReferenceReleaseStore) or capabilities is None or calibrations is None: raise ValueError('NOT_READY: explicit stores, capabilities and calibrations required')
    ref_sha = reference_release_store.require(profile)
    if library is not None:
        if not isinstance(library, ReferenceLibrary) or library.select(m['family_id'], m['variant_id'], m['profile_revision']) != profile: raise ValueError('NOT_READY: library mismatch')
    return _compile_contents(profile, physical_state, recipe, record, catalog, release_store, calibrations,
                             capabilities=capabilities, asset_store=asset_store, ref_sha=ref_sha,
                             module_registry=module_registry, scenario_spec=scenario_spec, review=False)


def _check_review_contents(profile, physical_state, recipe, record, catalog, release_store, calibrations,
                           *, capabilities, asset_store):
    """Run the existing compiler's content checks before reference release.

    This deliberately returns no execution bundle. The public compiler still
    requires the exact approved snapshot in ReferenceReleaseStore.
    """
    if not isinstance(profile, ReferenceProfile) or not isinstance(asset_store, AssetStore):
        raise ValueError('typed review inputs required')
    # Reject a non-review document before entering the shared checks.
    d=profile.data; m=d['metadata']; pr=d['provenance_release']
    if (m['status'] != 'REVIEW_READY' or m['template_only'] is not False
            or m['approval_scopes'] or m['content_sha256'] is not None
            or pr['release_approval'] is not None or pr['released_snapshot_sha256'] is not None):
        raise ValueError('unsigned review candidate required')
    _compile_contents(profile, physical_state, recipe, record, catalog, release_store, calibrations,
                      capabilities=capabilities, asset_store=asset_store, ref_sha=content_sha256(profile),
                      module_registry=None, scenario_spec=None, review=True)


def _compile_contents(profile, physical_state, recipe, record, catalog, release_store, calibrations,
                      *, capabilities, asset_store, ref_sha, module_registry, scenario_spec, review):
    d=profile.data; m=d['metadata']
    core = to_core_approved(record, calibrations, catalog=catalog, release_store=release_store)
    if (m['profile_id'], m['family_id'], m['variant_id'], m['profile_revision']) != (record.profile_id, record.family, record.variant, record.revision): raise ValueError('NOT_READY: ECU identity mismatch')
    workflows = [x for x in d['inspection_workflows']['recipes'] if x['recipe_id'] == recipe and x['state_id'] == physical_state]
    if len(workflows) != 1: raise ValueError('NOT_READY: state or recipe mismatch')
    w = workflows[0]; scope = w['approval_scope']
    if scope != 'photo_inspection': raise ValueError('NOT_READY: execution supported only for photo_inspection')
    # Verify all assets implicated by identity, workflow, or collision geometry.
    ids = set(w['required_asset_ids'])
    ids.update(x['reference_asset_id'] for x in d['recognition_rules']['features_to_check'] if x['state_id'] == physical_state and x['required'] and x['reference_asset_id'])
    state = next((x for x in d['physical_states'] if x['state_id'] == physical_state), None)
    geometry = next((x for x in d['geometry']['per_physical_state'] if state and x['geometry_id'] == state['geometry_id'] and x['state_id'] == physical_state), None)
    if geometry is None or record.envelope is None or any(abs(a-b)>EPSILON for a,b in zip(geometry['envelope_xyz_mm'], record.envelope.values)): raise ValueError('NOT_READY: envelope mismatch')
    if geometry['collision_asset_id']: ids.add(geometry['collision_asset_id'])
    assets = {a['asset_id']: a for a in d['reference_assets']['assets']}
    sources = {s['source_id']: s for s in d['provenance_release']['measurement_sources']}
    if any(assets[aid]['physical_state_id'] != physical_state or sources[assets[aid]['source_id']]['status'] != 'VERIFIED' or not any(h['asset_id'] == aid for h in d['provenance_release']['asset_hashes']) for aid in ids): raise ValueError('NOT_READY: asset provenance mismatch')
    verified = tuple(asset_store.verify_asset(assets[aid]) for aid in sorted(ids))
    evaluator = _evaluate_review_requirements if review else evaluate_readiness
    report = evaluator(profile, physical_state, recipe, scope, capabilities=capabilities, calibrations=calibrations, asset_ids_verified={x.asset_id for x in verified})
    if report.status != ('REVIEW_READY' if review else 'PASS'): raise ValueError('NOT_READY: ' + '; '.join(report.blockers))
    views = {v['view_id']: v for p in d['photography_recipes']['recipes'] if p['state_id'] == physical_state and p['recipe_id'] == recipe for v in p['views']}
    targets = {v.view_id: v for v in record.views}; roi_ids = set()
    if len(targets) != len(record.views) or len(set(w['required_view_ids'])) != len(w['required_view_ids']) or set(targets) != set(w['required_view_ids']): raise ValueError('NOT_READY: selected views must exactly match approved record')
    for vid in w['required_view_ids']:
        v = views[vid]; target = targets.get(vid); goal = v['camera_goal']
        if target is None or target.quaternion_xyzw is None or any(abs(a-b)>EPSILON for a,b in zip(goal['translation_mm'], target.position.values)) or any(abs(a-b)>EPSILON for a,b in zip(goal['quaternion_xyzw'], target.quaternion_xyzw)): raise ValueError('NOT_READY: view target mismatch')
        roi_ids.update(v['roi_refs'])
    for t in d['thermal_recipes']['recipes']:
        if t['recipe_id'] == recipe and t['state_id'] == physical_state and scope.startswith('thermal_'): roi_ids.update(t['roi_refs'])
    rois = {r['roi_id']: r for r in d['pcb_definition']['regions_of_interest']}
    if not roi_ids: raise ValueError('NOT_READY: selected PCB ROI required')
    for rid in roi_ids:
        x,y,width,height = rois[rid]['rectangle_xywh_mm']
        if not any(x >= a-EPSILON and y >= b-EPSILON and x+width <= a+c+EPSILON and y+height <= b+e+EPSILON for a,b,c,e in (p.values for p in record.pcb_regions)): raise ValueError('NOT_READY: ROI outside approved PCB region')
    core = replace(core, pcb_regions=tuple(tuple(rois[rid]['rectangle_xywh_mm']) for rid in sorted(roi_ids)))
    modules = _scenario(scenario_spec, module_registry, w['required_modules'], w['scenario_ref']) if w['required_modules'] else ()
    if not modules and (scenario_spec is not None or module_registry is not None): raise ValueError('NOT_READY: unexpected scenario or registry')
    needed = set(d['recognition_rules']['required_sensor_capabilities']) | set(w['required_capabilities']) | set(record.required_capabilities)
    if scope not in ('browse_and_select','verify_identity'): needed.update(d['localization_rules']['required_sensor_capabilities'])
    for vid in w['required_view_ids']: needed.update(views[vid]['required_capabilities'])
    for t in d['thermal_recipes']['recipes']:
        if t['recipe_id'] == recipe and t['state_id'] == physical_state and scope.startswith('thermal_'): needed.update(t['required_capabilities'])
    for module in modules: needed.update(module.capabilities)
    if not needed <= set(capabilities): raise ValueError('NOT_READY: capability missing')
    selected_photos = [
        p for p in d['photography_recipes']['recipes']
        if p['state_id'] == physical_state and p['recipe_id'] == recipe
    ]
    if len(selected_photos) != 1:
        raise ValueError('NOT_READY: selected photography recipe missing')
    qa = (set(w['quality_policy_refs'])
          | set(d['photography_recipes']['quality_policy_refs'])
          | set(selected_photos[0]['quality_policy_refs'])
          | {views[v]['quality_policy_ref'] for v in w['required_view_ids']})
    for t in d['thermal_recipes']['recipes']:
        if t['recipe_id'] == recipe and t['state_id'] == physical_state and scope.startswith('thermal_'): qa.add(t['quality_policy_ref'])
    return ExecutionBundle(core, record_sha256(record), ref_sha, verified, physical_state, recipe, frozenset(needed), modules, scenario_spec, tuple(sorted(qa)))

prepare_execution = compile_profile
