"""Independent ECU catalog pre-merge regressions; synthetic geometry only."""
import unittest
from dataclasses import replace
from test_ecu_profiles import synthetic, measured
from vision_modules.ecu_profiles import (
    ECUCatalog, Declaration, ECUObservation, ObservedConnector,
    verify_declared_ecu, validate_draft, to_core_ecu_profile,
)


class RealWorldInputRegressions(unittest.TestCase):
    def setUp(self):
        self.good = synthetic()

    def test_current_unix_timestamp_valid_for_fresh_observation(self):
        now = 1795520000.0  # 2026, real-world Unix epoch magnitude
        o = ECUObservation('oakd', 'rgbd-observation', 'oak_rgb_optical_frame',
                           'session', 'scene', 'r1', now,
                           (ObservedConnector('a', 'black', (1, 1, 1)),), True, True)
        catalog = ECUCatalog(); catalog.register(self.good)
        result = verify_declared_ecu(
            self.good, Declaration('ETC3','synthetic_variant','r1','operator'),
            o, session_id='session', frame_id='oak_rgb_optical_frame',
            scene_revision='scene', now=now, max_age=10,
            calibrations={'cal':'v1'}, catalog=catalog)
        self.assertEqual(result.status, 'ACCEPTED')

    def test_valid_nested_ros2_tf_frame_id(self):
        now = 1795520000.0
        frame = 'oak/rgb_camera_optical_frame'
        o = ECUObservation('oakd', 'rgbd-observation', frame,
                           'session', 'scene', 'r1', now,
                           (ObservedConnector('a', 'black', (1, 1, 1)),), True, True)
        catalog = ECUCatalog(); catalog.register(self.good)
        result = verify_declared_ecu(
            self.good, Declaration('ETC3','synthetic_variant','r1','operator'),
            o, session_id='session', frame_id=frame,
            scene_revision='scene', now=now, max_age=10,
            calibrations={'cal':'v1'}, catalog=catalog)
        self.assertEqual(result.status, 'ACCEPTED')

    def test_oblique_camera_target_outside_pcb_projection_can_be_reviewable(self):
        original = self.good.views[0]
        # This is camera TOOL/optical-center XYZ, NOT footprint or aim point.
        off_axis = replace(original, position=measured((-25, -12, 65),'view'))
        proposed = replace(self.good, views=(off_axis,), status='READY_FOR_REVIEW', approval=None)
        self.assertEqual(validate_draft(proposed), ())

    def test_incomplete_ETC3_cannot_be_promoted_even_with_approval(self):
        from pathlib import Path
        from vision_modules.ecu_profiles import load_json, ApprovalEvidence, record_sha256
        draft=load_json(Path('config/ecu_profiles/etc3_poc_v1.json').read_bytes())
        approval=ApprovalEvidence(draft.profile_id,draft.revision,record_sha256(draft),'reviewer',
                                  '2026-11-24T09:00:00+01:00','external-review')
        approved=replace(draft,status='APPROVED',approval=approval)
        c=ECUCatalog();c.register(approved)
        with self.assertRaises(ValueError):
            to_core_ecu_profile(approved,{},catalog=c)


if __name__=='__main__': unittest.main()

class IdentityAndEvidenceRegressions(unittest.TestCase):
    def setUp(self):
        self.good = synthetic()

    def test_approved_verification_requires_catalog_for_variant_disambiguation(self):
        now=100.
        obs=ECUObservation('oakd','obs-identity','frame','session','scene','r1',now,
                           (ObservedConnector('a','black',(1,1,1)),),True,True)
        result=verify_declared_ecu(self.good,Declaration('ETC3','synthetic_variant','r1','operator'),
              obs,session_id='session',frame_id='frame',scene_revision='scene',now=now,
              max_age=10,calibrations={'cal':'v1'})
        self.assertNotEqual(result.status,'ACCEPTED',
                            'a single selected record cannot prove variant uniqueness')

    def test_second_PCB_region_with_body_reference_fails_review(self):
        p=replace(self.good,pcb_regions=self.good.pcb_regions+(measured((15,15,15,15),'body'),),
                  status='READY_FOR_REVIEW',approval=None)
        self.assertTrue(validate_draft(p),
                        'every PCB measurement needs independent provenance from body')

    def test_second_view_with_body_reference_fails_review(self):
        second=replace(self.good.views[0],view_id='v2',
                       position=measured((15,15,50),'body'))
        p=replace(self.good,views=self.good.views+(second,),
                  status='READY_FOR_REVIEW',approval=None)
        self.assertTrue(validate_draft(p),
                        'every view pose provenance must be independent of body')

class FinalVariantAndReleaseRegressions(unittest.TestCase):
    def test_same_physical_connector_but_different_catalog_ids_is_ambiguous(self):
        from test_ecu_profiles_remediation import approve
        r = synthetic()
        other = approve(replace(
            r, profile_id='other', variant='other',
            connectors=(replace(r.connectors[0], connector_id='b'),)))
        catalog = ECUCatalog()
        catalog.register(r)
        catalog.register(other)
        observation = ECUObservation('oakd','sensor-output','frame',
                                     'session','scene','r1',100,
                                     (ObservedConnector('a','black',(1,1,1)),),True,True)
        result=verify_declared_ecu(
            r, Declaration('ETC3','synthetic_variant','r1','operator'),
            observation,session_id='session',frame_id='frame',scene_revision='scene',
            now=100,max_age=10,calibrations={'cal':'v1'},catalog=catalog)
        self.assertEqual(result.status,'AMBIGUOUS')

    def test_release_publish_uses_original_open_directory_after_path_replacement(self):
        import os
        import tempfile
        from pathlib import Path
        from vision_modules.ecu_profiles import ReleaseStore
        r=synthetic()
        c=ECUCatalog()
        c.register(r)
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)/'releases'
            moved=Path(root)/'moved'
            base.mkdir()
            with ReleaseStore(base) as store:
                base.rename(moved)
                base.symlink_to(Path(root)/'nonexistent')
                store.publish(r, {'cal':'v1'},catalog=c)
                self.assertEqual(store.read(r.profile_id,r.revision),r)
                self.assertTrue((moved/store._name(r.profile_id,r.revision)).is_file())

class ThreeConnectorVariantRegressions(unittest.TestCase):
    def test_same_three_connector_geometry_with_relabeling_is_ambiguous(self):
        from test_ecu_profiles_remediation import approve
        from vision_modules.ecu_profiles import Connector
        base = synthetic()
        black_b = Connector('black_b','black',measured((25, 2, 3),'landmark'),True)
        gray = Connector('gray','gray',measured((60, 2, 3),'landmark'),True)
        primary = approve(replace(base, connectors=base.connectors + (black_b,gray)))
        # Physical variants have identical landmarks, but catalog-specific
        # arbitrary connector identifiers and ordering do NOT match.
        alt_connectors = (
            replace(gray, connector_id='gray_other'),
            replace(black_b, connector_id='black_other_2'),
            replace(primary.connectors[0], connector_id='black_other_1'),
        )
        other = approve(replace(primary,profile_id='different',variant='other',
                                connectors=alt_connectors))
        catalog=ECUCatalog()
        catalog.register(primary)
        catalog.register(other)
        observation=ECUObservation(
            'depthai','independent-observation','oak/rgb_optical_frame',
            'session','scene','r1',1795520000.0,
            (ObservedConnector('a','black',(1,1,1)),
             ObservedConnector('black_b','black',(25,2,3)),
             ObservedConnector('gray','gray',(60,2,3))), True, True)
        args=dict(session_id='session',frame_id='oak/rgb_optical_frame',
                  scene_revision='scene',now=1795520000.0,max_age=10,
                  calibrations={'cal':'v1'},catalog=catalog)
        result=verify_declared_ecu(primary,
                                  Declaration('ETC3','synthetic_variant','r1','operator'),
                                  observation, **args)
        self.assertEqual(result.status,'AMBIGUOUS')

    def test_different_three_connector_geometry_is_not_ambiguous(self):
        from test_ecu_profiles_remediation import approve
        from vision_modules.ecu_profiles import Connector
        base=synthetic()
        black_b=Connector('black_b','black',measured((25,2,3),'landmark'),True)
        gray=Connector('gray','gray',measured((60,2,3),'landmark'),True)
        primary=approve(replace(base,connectors=base.connectors+(black_b,gray)))
        other_gray=Connector('different_gray','gray',measured((70,40,3),'landmark'),True)
        other=approve(replace(primary,profile_id='different',variant='different',
                              connectors=(replace(base.connectors[0],connector_id='x'),
                                          replace(black_b,connector_id='y'),other_gray)))
        catalog=ECUCatalog();catalog.register(primary);catalog.register(other)
        observation=ECUObservation(
            'depthai','independent-observation','frame','session','scene','r1',100,
            (ObservedConnector('a','black',(1,1,1)),
             ObservedConnector('black_b','black',(25,2,3)),
             ObservedConnector('gray','gray',(60,2,3))), True,True)
        result=verify_declared_ecu(primary,Declaration('ETC3','synthetic_variant','r1','operator'),
            observation,session_id='session',frame_id='frame',scene_revision='scene',
            now=100,max_age=10,calibrations={'cal':'v1'},catalog=catalog)
        self.assertEqual(result.status,'ACCEPTED')
