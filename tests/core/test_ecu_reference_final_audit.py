"""Post-implementation offline quality contract regressions, synthetic data only."""
import unittest
import test_ecu_reference_execution as baseline
from vision_modules.ecu_reference import evaluate_readiness


class ReferencePoliciesFinalAudit(unittest.TestCase):
    def trial(self):
        t = baseline.ExecutionTests('runTest')
        t.setUp()
        self.addCleanup(t.doCleanups)
        return t

    def check_reject(self, mutation):
        t = self.trial()
        profile, store = t.modified(mutation)
        report = evaluate_readiness(
            profile, 'pcb_exposed_top', 'photo', 'photo_inspection',
            capabilities=t.caps, calibrations=t.cal, asset_ids_verified={'image'})
        self.assertEqual(report.status, 'NOT_READY')
        with self.assertRaises(ValueError):
            t.compile(profile, reference_release_store=store, library=None)

    def test_selected_recipe_unverified_photo_policy_rejected(self):
        def mutation(d):
            d['validation_policies']['policies'].append(dict(
                policy_id='unreviewed', kind='quality', thresholds={'min_focus':1},
                source_id='source', verified=False))
            d['photography_recipes']['recipes'][0]['quality_policy_refs']=['unreviewed']
        self.check_reject(mutation)

    def test_selected_recipe_empty_photo_policy_rejected(self):
        def mutation(d):
            d['validation_policies']['policies'].append(dict(
                policy_id='empty', kind='quality', thresholds={},
                source_id='source', verified=True))
            d['photography_recipes']['recipes'][0]['quality_policy_refs']=['empty']
        self.check_reject(mutation)

    def test_global_photography_quality_policy_rejected(self):
        def mutation(d):
            d['validation_policies']['policies'].append(dict(
                policy_id='global',kind='quality',thresholds={},
                source_id='source', verified=False))
            d['photography_recipes']['quality_policy_refs']=['global']
        self.check_reject(mutation)

    def test_missing_asset_manifest_revision_rejected(self):
        self.check_reject(lambda d:d['reference_assets'].update(asset_manifest_revision=None))

    def test_verified_global_and_recipe_policies_are_included_in_bundle(self):
        t = self.trial()
        def mutation(d):
            d['validation_policies']['policies'].extend((
                dict(policy_id='global_qa', kind='quality',
                     thresholds={'minimum':1}, source_id='source', verified=True),
                dict(policy_id='recipe_qa', kind='quality',
                     thresholds={'minimum':1}, source_id='source', verified=True),
            ))
            d['photography_recipes']['quality_policy_refs']=['global_qa']
            d['photography_recipes']['recipes'][0]['quality_policy_refs']=['recipe_qa']
        profile, store = t.modified(mutation)
        report = evaluate_readiness(
            profile, 'pcb_exposed_top', 'photo', 'photo_inspection',
            capabilities=t.caps, calibrations=t.cal, asset_ids_verified={'image'})
        self.assertEqual(report.status, 'PASS')
        bundle = t.compile(profile, reference_release_store=store, library=None)
        self.assertTrue({'global_qa', 'recipe_qa', 'qa'}.issubset(bundle.qa_policy_refs))



if __name__=='__main__': unittest.main()
