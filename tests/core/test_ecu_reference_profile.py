"""Regression checks for the architectural template preview boundary."""
import json
from pathlib import Path
import unittest

from vision_modules.ecu_reference import canonical_json, compile_profile, content_sha256, load_json

TEMPLATE = Path('docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json').read_text()


class ReferencePreviewTests(unittest.TestCase):
    def test_template_round_trip(self):
        profile = load_json(TEMPLATE)
        self.assertEqual(canonical_json(load_json(canonical_json(profile))), canonical_json(profile))
        self.assertEqual(content_sha256(load_json(canonical_json(profile))), content_sha256(profile))

    def test_deep_immutable(self):
        p = load_json(TEMPLATE)
        with self.assertRaises(TypeError): p.data['metadata']['status'] = 'APPROVED'
        with self.assertRaises(AttributeError): p.data['physical_states'].append('closed')

    def test_template_never_compiles(self):
        with self.assertRaisesRegex(ValueError, 'NOT_READY'):
            compile_profile(load_json(TEMPLATE), 'closed', 'recipe', None, None, None, {})

    def test_duplicate_key(self):
        with self.assertRaises(ValueError): load_json('{"metadata":{},"metadata":{}}')

    def test_oversized(self):
        with self.assertRaises(ValueError): load_json(' ' * (512 * 1024 + 1))

    def test_nan(self):
        with self.assertRaises(ValueError): load_json(TEMPLATE.replace('null', 'NaN', 1))

    def test_unknown_section(self):
        value = json.loads(TEMPLATE); value['unknown'] = {}
        with self.assertRaises(ValueError): load_json(json.dumps(value))

    def test_unknown_nested_field(self):
        value = json.loads(TEMPLATE); value['inspection_workflows']['command'] = 'run'
        with self.assertRaises(ValueError): load_json(json.dumps(value))

    def test_real_release_not_supported_yet(self):
        value = json.loads(TEMPLATE); value['metadata']['schema_version'] = 'V1'
        with self.assertRaises(ValueError): load_json(json.dumps(value))

    def test_unchecked_nested_content_rejected(self):
        value = json.loads(TEMPLATE); value['inspection_workflows']['recipes'] = [{'command': 'run'}]
        with self.assertRaises(ValueError): load_json(json.dumps(value))


def synthetic_profile():
    d = json.loads(TEMPLATE)
    d['metadata'].update(schema_version='1', template_only=False, profile_id='synthetic', family_id='family', variant_id='variant', profile_revision='r1', display_name='Synthetic', status='APPROVED', approval_scopes=[dict(state_id='pcb_exposed_top', recipe_id='photo', scope='photo_inspection')])
    d['physical_states'] = [dict(state_id=s, display_name=s, geometry_id='g_'+s, required_recipe_ids=['photo'] if s == 'pcb_exposed_top' else [], verified=True, source_id='source') for s in ('closed','pcb_exposed_top')]
    d['coordinate_systems']['ecu_local'].update(origin_description='synthetic datum', datum_reference='source', axis_definitions='right-handed XYZ', verified=True)
    d['geometry']['per_physical_state'] = [dict(geometry_id='g_'+s, state_id=s, envelope_xyz_mm=[100,80,20], collision_asset_id=None, source_id='source', uncertainty_mm=0.1, verified=True) for s in ('closed','pcb_exposed_top')]
    d['connectors_landmarks']['connectors'] = [dict(feature_id='connector', state_id='pcb_exposed_top', color='blue', position_mm=[10,10,1], source_id='source', uncertainty_mm=0.1, required_for_identity=True, verified=True)]
    d['reference_assets']['asset_manifest_revision']='assets-r1'
    d['reference_assets']['assets'] = [dict(asset_id='image', kind='photo', relative_path='private/image.png', sha256='a'*64, bytes=100, mime='image/png', physical_state_id='pcb_exposed_top', source_id='source', verified=True, privacy_class='private')]
    d['recognition_rules']['features_to_check'] = [dict(feature_id='connector', state_id='pcb_exposed_top', method='rgb_landmark', required=True, tolerance_mm=1, reference_asset_id='image', source_id='source')]
    d['recognition_rules']['required_sensor_capabilities'] = ['rgb']
    d['recognition_rules']['accepted_policy_ref'] = 'qa'
    d['localization_rules'].update(methods=['rgbd_pose'], required_features=['connector'], pose_quality_policy_ref='qa')
    d['pcb_definition']['boards'] = [dict(board_id='board', state_id='pcb_exposed_top', source_id='source', verified=True)]
    d['pcb_definition']['regions_of_interest'] = [dict(roi_id='roi', board_id='board', state_id='pcb_exposed_top', rectangle_xywh_mm=[1,2,20,30], source_id='source', verified=True)]
    view=dict(view_id='view', roi_refs=['roi'], camera_goal=dict(frame='ecu_local', translation_mm=[0,0,100], quaternion_xyzw=[0,0,0,1]), aim_point_mm=[10,10,0], working_distance_range_mm=[50,150], required_capabilities=['camera'], quality_policy_ref='qa', required=True, source_id='source')
    d['photography_recipes']['recipes'] = [dict(recipe_id='photo', state_id='pcb_exposed_top', views=[view], quality_policy_refs=['qa'])]
    d['inspection_workflows']['recipes'] = [dict(recipe_id='photo', state_id='pcb_exposed_top', scenario_ref='inspection', required_view_ids=['view'], required_modules=['vision'], required_capabilities=['camera'], quality_policy_refs=['qa'], required_asset_ids=['image'], approval_scope='photo_inspection')]
    d['validation_policies']['policies'] = [dict(policy_id='qa', kind='quality', thresholds={'minimum':1}, source_id='source', verified=True)]
    d['validation_policies']['readiness_by_scope_and_physical_state'] = [dict(state_id='pcb_exposed_top', recipe_id='photo', scope='photo_inspection', approved=True, source_id='source')]
    d['provenance_release'].update(measurement_sources=[dict(source_id='source', date='2026-01-01', status='VERIFIED', instrument='synthetic', datum='synthetic', uncertainty_mm=0.1, reference='synthetic')], calibration_dependencies=[dict(name='camera_cal', revision='r1')], asset_hashes=[dict(asset_id='image',sha256='a'*64)])
    digest=content_sha256(load_json(json.dumps(d)))
    d['metadata']['content_sha256']=digest
    d['provenance_release']['released_snapshot_sha256']=digest
    d['provenance_release']['release_approval']=dict(reviewer_id='reviewer', approved_at='2026-01-01', reference='review', content_sha256=digest)
    return d


class FilledProfileTests(unittest.TestCase):
    def test_positive_and_missing_evidence(self):
        from vision_modules.ecu_reference import evaluate_readiness
        p=load_json(json.dumps(synthetic_profile()))
        self.assertEqual(canonical_json(load_json(canonical_json(p))), canonical_json(p))
        def check(**kwargs): return evaluate_readiness(p, 'pcb_exposed_top', 'photo', 'photo_inspection', **kwargs).status
        self.assertEqual(check(capabilities={'rgb','camera'}, calibrations={'camera_cal':'r1'}, asset_ids_verified={'image'}), 'PASS')
        for kwargs in (dict(capabilities={'rgb','camera'}, calibrations={'camera_cal':'r1'}), dict(capabilities={'rgb'}, calibrations={'camera_cal':'r1'}, asset_ids_verified={'image'}), dict(capabilities={'rgb','camera'}, calibrations={}, asset_ids_verified={'image'})):
            self.assertEqual(check(**kwargs), 'NOT_READY')

    def test_template_not_ready(self):
        from vision_modules.ecu_reference import evaluate_readiness
        self.assertEqual(evaluate_readiness(load_json(TEMPLATE), 'closed', 'x', 'verify_identity', capabilities=set(), calibrations={}).status, 'NOT_READY')

    def test_invalid_nested_contracts(self):
        mutations = [
            lambda d: d['physical_states'][0].update(command='run'),
            lambda d: d['geometry']['per_physical_state'][0].update(envelope_xyz_mm=[0,1,1]),
            lambda d: d['geometry']['per_physical_state'][0].update(source_id='missing'),
            lambda d: d['physical_states'].append(d['physical_states'][0]),
            lambda d: d['reference_assets']['assets'][0].update(relative_path='../secret'),
            lambda d: d['photography_recipes']['recipes'][0]['views'][0]['camera_goal'].update(quaternion_xyzw=[0,0,0,0]),
            lambda d: d['validation_policies']['policies'][0].update(thresholds={'x':0}),
            lambda d: d['pcb_definition']['regions_of_interest'][0].update(board_id='missing'),
            lambda d: d['coordinate_systems']['ecu_local'].update(linear_unit='inch'),
            lambda d: d['inspection_workflows']['recipes'][0].update(required_view_ids=['missing']),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                d=synthetic_profile(); mutate(d)
                with self.assertRaises(ValueError): load_json(json.dumps(d))

# Independent malformed-input cases keep each closed contract under regression.
def _invalid_case(path, value):
    def test(self):
        d=synthetic_profile(); target=d
        for part in path[:-1]: target=target[part]
        target[path[-1]]=value
        with self.assertRaises(ValueError): load_json(json.dumps(d))
    return test

for _n, (_path, _value) in enumerate([
    (['metadata','profile_id'], '../bad'), (['metadata','status'], 'ACTIVE'),
    (['metadata','template_only'], True), (['metadata','content_sha256'], 'bad'),
    (['identity','declared_by_operator'], False), (['physical_states',0,'verified'], 1),
    (['physical_states',0,'geometry_id'], 'unknown'), (['coordinate_systems','ecu_local','handedness'], 'left'),
    (['coordinate_systems','ecu_local','verified'], 'yes'), (['geometry','collision_geometry_requires_verified_envelope'], False),
    (['connectors_landmarks','connectors',0,'state_id'], 'unknown'),
    (['connectors_landmarks','connectors',0,'uncertainty_mm'], -1),
    (['reference_assets','assets',0,'sha256'], 'bad'), (['reference_assets','assets',0,'bytes'], 1.2),
    (['recognition_rules','features_to_check',0,'method'], 'execute'),
    (['recognition_rules','on_ambiguity'], 'ALLOW'), (['localization_rules','methods'], ['script']),
    (['localization_rules','requires_fresh_tf'], False), (['pcb_definition','boards',0,'source_id'], 'missing'),
    (['pcb_definition','regions_of_interest',0,'rectangle_xywh_mm'], [0,0,-1,2]),
    (['photography_recipes','recipes',0,'views',0,'quality_policy_ref'], 'missing'),
    (['photography_recipes','recipes',0,'views',0,'working_distance_range_mm'], [3,2]),
    (['thermal_recipes','radiometric_requires_calibration'], False),
    (['inspection_workflows','no_automatic_motion_after_failure'], False),
    (['inspection_workflows','recipes',0,'approval_scope'], 'execute'),
    (['validation_policies','automatic_variant_substitution'], True),
    (['validation_policies','policies',0,'thresholds'], {'x': -1}),
    (['provenance_release','measurement_sources',0,'status'], 'TRUSTED'),
    (['provenance_release','asset_hashes',0,'sha256'], 'b'*64),
    (['provenance_release','release_approval','content_sha256'], 'bad'),
]):
    setattr(FilledProfileTests, 'test_invalid_contract_%02d' % _n, _invalid_case(_path, _value))

setattr(FilledProfileTests, 'test_invalid_extra_view_field', _invalid_case(['photography_recipes','recipes',0,'views',0,'camera_goal'], {'frame':'ecu_local','translation_mm':[0,0,0],'quaternion_xyzw':[0,0,0,1],'script':'run'}))
setattr(FilledProfileTests, 'test_invalid_asset_absolute_path', _invalid_case(['reference_assets','assets',0,'relative_path'], '/private/image.png'))
setattr(FilledProfileTests, 'test_invalid_policy_reference', _invalid_case(['recognition_rules','accepted_policy_ref'], 'missing'))
