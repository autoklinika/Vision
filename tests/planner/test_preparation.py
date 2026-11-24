"""S05 integration with synthetic approved Runtime fixtures; no device access."""
import copy
import math
from dataclasses import replace
from pathlib import Path
import unittest

import test_ecu_reference_execution as reference_fixture
import test_vision_runtime_v1 as runtime_fixture
from vision_core.models import GateError
from vision_core.profiles import PROFILE_KINDS, Profile
from vision_modules.ecu_profiles import ECUCatalog, ReleaseStore, ApprovalEvidence, record_sha256
from vision_modules.ecu_reference import ReferenceReleaseStore, ReferenceLibrary
from vision_planner.preparation import (CameraCalibration, PlanningPolicy, prepare_plan,
                                        verify_prepared)

H = 'sha256:'+'b'*64


class SyntheticPlannerFixture:
    """Reusable helper, deliberately not a TestCase (no duplicated test discovery)."""
    def __init__(self, *, strict_planning=False, views=1, advance=True, observation_changes=None,
                 reference_changes=None):
        self.case = f = runtime_fixture.RuntimeTests('runTest')
        try:
            f.setUp()
            f.cal = {**f.cal, 'sony_optics':'v1'}
            originals = []
            recipe_views = []
            base = copy.deepcopy(f.d['photography_recipes']['recipes'][0]['views'][0])
            for i in range(views):
                xyz = (15+10*i, 20, 100)
                original = replace(f.record.views[0], view_id='v'+str(i+1),
                    position=replace(f.record.views[0].position, values=xyz), quaternion_xyzw=(1,0,0,0))
                originals.append(original)
                view = copy.deepcopy(base)
                view.update(view_id=original.view_id, aim_point_mm=[xyz[0],xyz[1],0],
                            working_distance_range_mm=[50,150])
                view['camera_goal'].update(translation_mm=list(xyz), quaternion_xyzw=[1,0,0,0])
                recipe_views.append(view)
            record = replace(f.record, views=tuple(originals), approval=None)
            f.record = replace(record, approval=ApprovalEvidence(record.profile_id, record.revision,
                record_sha256(record), 'reviewer', '2026-01-02T12:00:00Z', 'synthetic-planner-record'))
            f.catalog = ECUCatalog(); f.catalog.register(f.record)
            root = Path(f.tmp.name)
            (root/'planner_ecu').mkdir(); f.ecu = ReleaseStore(root/'planner_ecu'); f.addCleanup(f.ecu.close)
            f.ecu.publish(f.record, f.cal, catalog=f.catalog)
            f.d['photography_recipes']['recipes'][0]['views'] = recipe_views
            # Intentionally reverse this list; the compiled Core uses record
            # order, not the reference's set of required IDs.
            f.d['inspection_workflows']['recipes'][0]['required_view_ids'] = [v.view_id for v in reversed(originals)]
            if reference_changes is not None:
                reference_changes(f.d)
            f.p = reference_fixture.seal(f.d)
            (root/'planner_ref').mkdir(); f.ref = ReferenceReleaseStore(root/'planner_ref'); f.addCleanup(f.ref.close)
            f.ref.publish(f.p); f.lib = ReferenceLibrary(); f.lib.register(f.p)
            f.bundle = reference_fixture.ExecutionTests.compile(f)
            f.caps = f.caps | {'raw'}
            f.profiles = {k: Profile(k,k,'1','r1',True,{'basic','raw'} if k=='capture' else {'basic'},
                {'basic'}, f.cal) for k in PROFILE_KINDS}
            f.profiles['ecu'] = f.bundle.core_profile
            f.coordinator = f.make(**({'strict_planning':True} if strict_planning else {}))
            self.runtime = f.coordinator
            self.calibration = CameraCalibration(calibration_id='sony_optics', revision='v1',
                capture_profile_revision='r1', configuration_ref=H, width=200, height=200,
                fx=100, fy=100, cx=100, cy=100, usable_image_xywh_px=(0,0,200,200),
                rectified=True, approved=True, source='calibration_lab', reference=H)
            self.policy = PlanningPolicy(policy_id='photo_plan', revision='v1', approved=True,
                source='calibration_lab', reference=H, qa_policy_refs=f.bundle.qa_policy_refs,
                capture_configuration_ref=H, physical_state='pcb_exposed_top', recipe='photo',
                reference_sha256=f.bundle.reference_sha256, pcb_plane_z_mm=0, plane_reference=H,
                min_coverage=1, require_raw=True, require_each_view_roi=True)
            if advance:
                f.s03(f.obs(**(observation_changes or {})))
                result = f.coordinator.verify_selected_ecu(f.req('S04'))
                if result.status != 'SUCCEEDED':
                    raise AssertionError(result)
        except BaseException:
            f.doCleanups()
            raise

    def prepare(self, **changes):
        return prepare_plan(self.runtime, camera_calibration=changes.pop('camera_calibration',self.calibration),
                            policy=changes.pop('policy',self.policy), **changes)

    def close(self):
        self.case.doCleanups()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = SyntheticPlannerFixture()
        self.addCleanup(self.fixture.close)

    def test_runtime_recipe_to_bound_plan(self):
        p = self.fixture.prepare()
        self.assertEqual(p.coverage_fraction, 1)
        self.assertTrue(p.core_plan.require_raw)
        self.assertEqual(p.view_bindings[0].reference_view_id, 'v1')
        self.assertEqual(p.view_bindings[0].view_id, 'view_001')
        self.assertEqual(p.footprints[0].rectangle_xywh_mm, (-85,-80,200,200))
        verify_prepared(p, self.fixture.runtime)
        self.assertEqual(p, self.fixture.prepare())

    def test_record_order_is_preserved_despite_reference_required_id_order(self):
        with SyntheticPlannerFixture(views=2) as fixture:
            p = fixture.prepare()
            self.assertEqual([v.reference_view_id for v in p.view_bindings], ['v1','v2'])
            self.assertEqual(len(p.core_plan.targets), 2)
            self.assertEqual(p.core_plan.targets[1].local_xyz_mm,(25,20,100))

    def test_planar_ecu_rotation_preserves_local_capture_coverage(self):
        original = self.fixture.prepare()
        with SyntheticPlannerFixture(observation_changes={
                'position_mm':(20,30,9), 'quaternion_xyzw':(0,0,math.sqrt(.5),math.sqrt(.5))}) as fixture:
            rotated = fixture.prepare()
            self.assertEqual(original.footprints, rotated.footprints)
            self.assertEqual(original.coverage_fraction,rotated.coverage_fraction)
            for a,b in zip(rotated.core_plan.targets[0].scene_xyz_mm,(0,45,109)):
                self.assertAlmostEqual(a,b)
            self.assertNotEqual(original.digest,rotated.digest)

    def test_tilted_ecu_pose_cannot_be_reduced_to_yaw(self):
        with SyntheticPlannerFixture(observation_changes={
                'quaternion_xyzw':(math.sin(.05),0,0,math.cos(.05))}) as fixture:
            with self.assertRaisesRegex(GateError,'yaw-only'): fixture.prepare()

    def test_unapproved_or_mismatched_optics_and_configuration(self):
        c = self.fixture.calibration
        for changes in ({'approved':False},{'rectified':False},{'revision':'v2'},
                        {'capture_profile_revision':'r2'},{'source':'operator'},
                        {'configuration_ref':'sha256:'+'c'*64},{'calibration_id':'camera_cal'}):
            with self.subTest(changes=changes), self.assertRaises(GateError):
                self.fixture.prepare(camera_calibration=replace(c,**changes))

    def test_policy_matches_selected_reference_qa_and_capture_configuration(self):
        policy = self.fixture.policy
        for changes in ({'approved':False},{'recipe':'other'},{'physical_state':'closed'},
                        {'reference_sha256':'c'*64},{'qa_policy_refs':('other',)},
                        {'capture_configuration_ref':'sha256:'+'c'*64},{'source':'operator'}):
            with self.subTest(changes=changes), self.assertRaises(GateError):
                self.fixture.prepare(policy=replace(policy,**changes))

    def test_invalid_calibration_geometry_and_policy_numbers(self):
        c = self.fixture.calibration
        for changes in ({'fx':0},{'fy':math.nan},{'width':True},{'approved':1},
                        {'fx':10**1000},
                        {'cx':-1},{'usable_image_xywh_px':(0,0,201,200)},
                        {'usable_image_xywh_px':(0,0,0,10)}):
            with self.subTest(changes=changes), self.assertRaises(GateError): replace(c,**changes)
        for changes in ({'min_coverage':0},{'min_coverage':math.inf},{'require_raw':1},
                        {'pcb_plane_z_mm':math.nan},{'qa_policy_refs':('qa','qa')}):
            with self.subTest(changes=changes), self.assertRaises(GateError): replace(self.fixture.policy,**changes)

    def test_small_useful_image_fails_required_roi(self):
        c = replace(self.fixture.calibration, usable_image_xywh_px=(95,95,10,10))
        with self.assertRaisesRegex(GateError,'cover'): self.fixture.prepare(camera_calibration=c)

    def test_predicted_union_cannot_claim_uncovered_hole(self):
        # Disabling per-view coverage does not disable total PCB coverage.
        c = replace(self.fixture.calibration, usable_image_xywh_px=(95,95,10,10))
        policy = replace(self.fixture.policy, require_each_view_roi=False)
        with self.assertRaisesRegex(GateError,'predicted PCB coverage'):
            self.fixture.prepare(camera_calibration=c, policy=policy)

    def test_aim_plane_and_working_distance_are_enforced(self):
        with self.assertRaisesRegex(GateError,'PCB plane'):
            self.fixture.prepare(policy=replace(self.fixture.policy,pcb_plane_z_mm=2))
        with SyntheticPlannerFixture(reference_changes=lambda d:
                d['photography_recipes']['recipes'][0]['views'][0].update(working_distance_range_mm=[1,2])) as fixture:
            with self.assertRaisesRegex(GateError,'working-distance'): fixture.prepare()

    def test_missing_accepted_stages_and_stale_observation(self):
        with SyntheticPlannerFixture(advance=False) as fixture:
            with self.assertRaisesRegex(GateError,'S01'): fixture.prepare()
        p = self.fixture.prepare()
        self.fixture.case.now = 111
        with self.assertRaises(ValueError): verify_prepared(p,self.fixture.runtime)

    def test_altered_inmemory_observation_cannot_replace_durable_evidence(self):
        runtime = self.fixture.runtime
        runtime._observation = replace(runtime._observation,position_mm=(1,0,0))
        with self.assertRaisesRegex(GateError,'accepted Runtime evidence'): self.fixture.prepare()

    def test_altered_coverage_or_policy_invalidates_preparation(self):
        p = self.fixture.prepare()
        for altered in (replace(p,digest='a'*64),replace(p,coverage_fraction=.9),
                        replace(p,policy=replace(p.policy,min_coverage=.9)),
                        replace(p,footprints=(replace(p.footprints[0],rectangle_xywh_mm=(0,0,1,1)),))):
            with self.subTest(altered=altered.digest), self.assertRaises(GateError):
                verify_prepared(altered,self.fixture.runtime)

    def test_changed_profile_or_recipe_is_not_silently_replanned(self):
        p = self.fixture.prepare()
        engine = self.fixture.runtime.engine
        engine.profiles['capture'] = replace(engine.profiles['capture'],revision='r2')
        with self.assertRaisesRegex(GateError,'configuration changed'):
            verify_prepared(p,self.fixture.runtime)


if __name__ == '__main__':
    unittest.main()
