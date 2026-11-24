"""Independent pre-PR regressions for reference profile state/recipe and releases.

All measurements, images, identities and timestamps below are synthetic.
"""
import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_ecu_reference_execution as baseline
from test_ecu_profiles import measured
from test_ecu_profiles_remediation import approve
from vision_modules.ecu_profiles import ECUCatalog, ReleaseStore
from vision_modules.ecu_reference import (
    ReferenceReleaseStore, canonical_json, compile_profile,
    content_sha256, evaluate_readiness, load_json,
)
from vision_modules.ecu_reference.codec import MAX_BYTES


class ReferenceIndependentAudit(unittest.TestCase):
    def fixture(self):
        test=baseline.ExecutionTests('runTest')
        test.setUp()
        self.addCleanup(test.doCleanups)
        return test

    def test_missing_identification_and_pose_requirements_prevent_ready(self):
        t=self.fixture()
        def change(d):
            c=d['connectors_landmarks']['connectors'][0]
            c['position_mm']=None
            c['uncertainty_mm']=None
            d['recognition_rules']['accepted_policy_ref']=None
            d['localization_rules']['pose_quality_policy_ref']=None
            d['localization_rules']['required_features']=[]
        profile,store=t.modified(change)
        result=evaluate_readiness(
            profile,'pcb_exposed_top','photo','photo_inspection',
            capabilities=t.caps,calibrations=t.cal,asset_ids_verified={'image'})
        self.assertEqual(result.status,'NOT_READY')

    def test_workflow_cannot_use_views_from_another_photo_recipe(self):
        t=self.fixture()
        with self.assertRaises(ValueError):
            profile,store=t.modified(
                lambda d:d['photography_recipes']['recipes'][0].update(recipe_id='other'))
            t.compile(profile,reference_release_store=store,library=None)

    def test_extra_core_record_view_is_not_included_in_selected_reference_recipe(self):
        t=self.fixture()
        second=replace(t.record.views[0],
                       view_id='v2',position=measured((15,25,60),'extra-view-pos'),
                       orientation_provenance=measured((0,),'extra-view-orientation').provenance)
        record=approve(replace(t.record,views=t.record.views+(second,)))
        cat=ECUCatalog()
        cat.register(record)
        folder=Path(t.tmp.name)/'second_ecu'
        folder.mkdir()
        store=ReleaseStore(folder)
        self.addCleanup(store.close)
        store.publish(record,t.cal,catalog=cat)
        with self.assertRaises(ValueError):
            compile_profile(t.p,'pcb_exposed_top','photo',record,cat,store,t.cal,
                            capabilities=t.caps,asset_store=t.assets,
                            reference_release_store=t.ref,library=t.lib)

    def test_approved_release_rejects_unreadable_oversized_canonical_snapshot(self):
        t=self.fixture()
        d=copy.deepcopy(t.d)
        # ensure_ascii=False is compact on disk; canonical ASCII escapes
        # threefold, so the release could be larger than the input limit.
        d['identity']['aliases']=['ą'*3500 for _ in range(55)]
        d['metadata']['content_sha256']=None
        d['provenance_release']['release_approval']['content_sha256']='0'*64
        d['provenance_release']['released_snapshot_sha256']=None
        preliminary=load_json(json.dumps(d,ensure_ascii=False))
        digest=content_sha256(preliminary)
        d['metadata']['content_sha256']=digest
        d['provenance_release']['release_approval']['content_sha256']=digest
        d['provenance_release']['released_snapshot_sha256']=digest
        final=load_json(json.dumps(d,ensure_ascii=False))
        self.assertGreater(len(canonical_json(final).encode('ascii')),MAX_BYTES)
        folder=Path(t.tmp.name)/'large_release'
        folder.mkdir()
        store=ReferenceReleaseStore(folder)
        self.addCleanup(store.close)
        with self.assertRaises(ValueError):
            store.publish(final)
        self.assertFalse(list(folder.glob('*.json')))

    def test_missing_metric_position(self):
        self.check_not_ready(lambda d: d['connectors_landmarks']['connectors'][0].update(position_mm=None))

    def test_missing_metric_uncertainty(self):
        self.check_not_ready(lambda d: d['connectors_landmarks']['connectors'][0].update(uncertainty_mm=None))

    def test_missing_recognition_policy(self):
        self.check_not_ready(lambda d: d['recognition_rules'].update(accepted_policy_ref=None))

    def test_missing_pose_policy(self):
        self.check_not_ready(lambda d: d['localization_rules'].update(pose_quality_policy_ref=None))

    def test_missing_localization_features(self):
        self.check_not_ready(lambda d: d['localization_rules'].update(required_features=[]))

    def test_empty_policy_thresholds(self):
        self.check_not_ready(lambda d: d['validation_policies']['policies'][0].update(thresholds={}))

    def test_localization_feature_wrong_state(self):
        def change(d):
            d['connectors_landmarks']['landmarks'].append(dict(feature_id='other', state_id='closed', kind='mark', position_mm=[1,2,3], source_id='source', uncertainty_mm=0.1, verified=True))
            d['localization_rules']['required_features'] = ['other']
        self.check_not_ready(change)

    def test_ambiguous_variant_not_ready_to_execute(self):
        t=self.fixture()
        p,store=t.modified(lambda d:d['identity'].update(known_indistinguishable_variants=['other']))
        self.assertEqual(evaluate_readiness(p,'pcb_exposed_top','photo','photo_inspection',capabilities=t.caps,calibrations=t.cal,asset_ids_verified={'image'}).status, 'AMBIGUOUS')
        with self.assertRaises(ValueError): t.compile(p,reference_release_store=store,library=None)

    def test_only_selected_roi_in_core_profile(self):
        t=self.fixture()
        record=approve(replace(t.record,pcb_regions=t.record.pcb_regions+(measured((90,65,5,5),'other-pcb'),)))
        cat=ECUCatalog(); cat.register(record)
        folder=Path(t.tmp.name)/'roi_ecu'; folder.mkdir()
        store=ReleaseStore(folder); self.addCleanup(store.close); store.publish(record,t.cal,catalog=cat)
        bundle=compile_profile(t.p,'pcb_exposed_top','photo',record,cat,store,t.cal,capabilities=t.caps,asset_store=t.assets,reference_release_store=t.ref,library=t.lib)
        self.assertEqual(bundle.core_profile.pcb_regions, ((5,5,20,30),))

    def test_optional_view_not_executed(self):
        t=self.fixture()
        def change(d):
            v=copy.deepcopy(d['photography_recipes']['recipes'][0]['views'][0]); v.update(view_id='optional',required=False)
            d['photography_recipes']['recipes'][0]['views'].append(v)
        p,store=t.modified(change)
        self.assertEqual(len(t.compile(p,reference_release_store=store,library=None).core_profile.view_targets), 1)

    def check_not_ready(self, change):
        t=self.fixture(); p,store=t.modified(change)
        result=evaluate_readiness(p,'pcb_exposed_top','photo','photo_inspection',capabilities=t.caps,calibrations=t.cal,asset_ids_verified={'image'})
        self.assertEqual(result.status,'NOT_READY')
        with self.assertRaises(ValueError): t.compile(p,reference_release_store=store,library=None)


if __name__=='__main__':
    unittest.main()
