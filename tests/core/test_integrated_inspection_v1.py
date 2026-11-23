"""End-to-end 0.1->0.2->0.3 synthetic inspection, without hardware."""
import json
import os
import tempfile
import unittest
from dataclasses import replace

import cv2
import numpy as np
import test_workflow as fixtures
from vision_core import Journal, Workflow, Evidence, State
from vision_core.workflow import CHECKS, STAGES
from vision_core.archive import Archive, digest
from vision_core.photography import PhotographySession, MotionResult, ResultIdentity, CaptureResult, Original
from vision_core.quality import QualityPolicy
from vision_core.repeatability import (
    ObservedECU, create_plan, complete_s05, photography_views,
    SpatialCoverageEvidence, SpatialFootprint, coverage_proof,
)

NOW=fixtures.NOW


class IntegratedInspectionV1(unittest.TestCase):
    def test_full_11_stage_inspection_with_verified_plan_and_archive(self):
        with tempfile.TemporaryDirectory() as root:
            profiles=fixtures.profiles()
            profiles['ecu']=replace(profiles['ecu'],
                view_targets=((1.0,2.0,3.0),(5.0,6.0,3.0)),
                view_quaternions_xyzw=((0.0,0.0,0.0,1.0),(0.0,0.0,0.0,1.0)))
            ctx=fixtures.context()
            path=os.path.join(root,'journal.sqlite')
            j=Journal(path)
            workflow=Workflow(j,ctx,profiles,{'cal':'v1'},{},10,lambda: NOW)
            observation=ObservedECU(ctx.frame_id,(100,200,10),0.2,NOW,ctx.scene_revision,
                profiles['ecu'].revision,profiles['ecu'].declared_type,profiles['ecu'].variant,'synthetic-observation')
            plan=create_plan(ctx,profiles,{'cal':'v1'},{},observation,NOW,10,
                 min_coverage=1.0,require_raw=True)
            ar=Archive(root,ctx.session_id)
            try:
                for s in STAGES[:4]:
                    workflow.start(s,'req-'+s)
                    workflow.complete(Evidence(ctx.session_id,s,'req-'+s,ctx,NOW,True,True,
                        frozenset(CHECKS[s]),'synthetic-ok'))
                workflow.start('S05','req-S05')
                complete_s05(workflow,plan)
                self.assertEqual(workflow.accepted_plan_hash,plan.digest)
                workflow.start('S06','req-S06')
                workflow.complete(Evidence(ctx.session_id,'S06','req-S06',ctx,NOW,True,True,
                    frozenset(CHECKS['S06']),'synthetic-moveit-plan',plan.digest))
                workflow.start('S07','req-S07')
                views=photography_views(plan,ctx,profiles,{'cal':'v1'},{},NOW,10)
                session=PhotographySession(workflow,ar,views,plan=plan)
                image=np.indices((32,32)).sum(axis=0) % 2 * 180 + 30
                ok,encoded=cv2.imencode('.png',image.astype(np.uint8))
                self.assertTrue(ok)
                for i,view in enumerate(views):
                    identity=ResultIdentity(ctx,'req-S07',view.view_id,NOW)
                    session.accept_motion(MotionResult(identity,True,(0.1,0.2),True,NOW,'synthetic-feedback-'+view.view_id))
                    pic=cv2.imencode('.png',(image + i*4).astype(np.uint8))[1].tobytes()
                    raw=('synthetic RAW bytes '+view.view_id).encode()
                    originals=(Original('png',pic,digest(pic),view.view_id+'-png'),
                               Original('raw',raw,digest(raw),view.view_id+'-raw'))
                    session.accept_capture(CaptureResult(identity,True,True,originals,'synthetic-transfer-'+view.view_id))
                session.complete_capture()
                self.assertEqual(workflow.states['S07'],State.SUCCEEDED)
                workflow.start('S08','req-S08')
                observed=SpatialCoverageEvidence(ctx.session_id,plan.digest,ctx.scene_revision,
                    ctx.profile_revisions,NOW,frozenset(v.view_id for v in views),
                    tuple(SpatialFootprint(v.view_id,(0,0,10,20),True) for v in views),
                    'ecu_local','synthetic-spatial-provenance',True,session.capture_bindings())
                proof,frac=coverage_proof(plan,observed,'req-S08',
                    ctx,profiles,{'cal':'v1'},{},NOW,10)
                self.assertEqual(frac,1.0)
                policy=QualityPolicy(10,.2,.2,5,250,16,16,(0,0,16,16))
                session.assess(policy,proof)
                self.assertEqual(workflow.states['S08'],State.SUCCEEDED)
                workflow.start('S09','req-S09')
                workflow.complete(Evidence(ctx.session_id,'S09','req-S09',ctx,NOW,True,True,
                    frozenset(CHECKS['S09']),'synthetic-supervised-park'))
                workflow.start('S10','req-S10')
                session.archive_session()
                workflow.start('S11','req-S11')
                workflow.complete(Evidence(ctx.session_id,'S11','req-S11',ctx,NOW,True,True,
                    frozenset(CHECKS['S11']),'synthetic-summary'))
                self.assertTrue(all(s==State.SUCCEEDED for s in workflow.states.values()))
                self.assertEqual(len([e for e in j.replay(ctx.session_id) if e.kind=='dispatch']),11)
                manifest=json.loads(ar._read('manifest-v1.json'))
                self.assertEqual(manifest['status'],'prepared')
                self.assertEqual(len(manifest['views']),2)
                for record in manifest['views']:
                    for entry in record['files']:
                        ar.verify(entry['name'],entry['sha256'])
            finally:
                ar.close()
                j.close()
            re=Journal(path)
            try:
                replay=Workflow(re,ctx,profiles,{'cal':'v1'},{},10,lambda: NOW)
                self.assertEqual(replay.accepted_plan_hash,plan.digest)
                self.assertTrue(all(s==State.SUCCEEDED for s in replay.states.values()))
            finally:
                re.close()


if __name__=='__main__': unittest.main()
