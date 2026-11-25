"""Isolated human-review workflow; synthetic geometry and images only."""
from dataclasses import replace
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from test_ecu_profiles import synthetic
from test_ecu_reference_profile import synthetic_profile
from vision_api.access import AccessDenied
from vision_api.identity import IdentityStore, provision_account
from vision_modules.ecu_library_backend import ECULibraryService
from vision_modules.ecu_profiles import ECUCatalog, ReleaseStore, record_sha256, load_json as load_catalog
from vision_modules.ecu_reference import (AssetStore, ReferenceReleaseStore, ReferenceLibrary,
    compile_profile, evaluate_readiness, load_json, canonical_json)
from vision_modules.ecu_reference.models import thaw
from vision_station.reference_review import (ReferenceReviewService, ReviewAuthority, ReviewStore,
    ReviewConflict, ReviewBlocked, catalog_review_blockers)
from vision_station.review_cli import prepare_workspace, _status, _config


class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix="ecu-review-")
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.lib=ECULibraryService(self.root/"library")
        self.review=self.root/"reviews";self.catalog_release=self.root/"catalog-release";self.ref_release=self.root/"reference-release"
        for path in (self.review,self.catalog_release,self.ref_release):
            path.mkdir(mode=0o700)
        accounts=self.root/"accounts.json"
        password="synthetic-local-review-password"
        for name,role in (("author","operator"),("reviewer","operator"),("reader","reader"),("outsider","operator")):
            provision_account(accounts,name,password,role=role)
        self.identity=IdentityStore(accounts)
        self.author=self.identity.login("author",password,"fixture")[0]
        self.reviewer=self.identity.login("reviewer",password,"fixture")[0]
        self.reader=self.identity.login("reader",password,"fixture")[0]
        self.outsider=self.identity.login("outsider",password,"fixture")[0]
        self.authority=ReviewAuthority(self.identity,authors={"author"},reviewers={"reviewer","reader"})
        self.cal={"cal":"v1","camera_cal":"r1"};self.caps={"basic","rgb","camera"}
        self.service=self.make_service()
        self.record=replace(synthetic(),status="DRAFT",approval=None)
        # A genuine, small decodable synthetic PNG, not claimed hardware data.
        ok,encoded=cv2.imencode(".png",np.full((24,32,3),127,dtype=np.uint8))
        self.assertTrue(ok)
        self.image=encoded.tobytes()

    def make_service(self, **overrides):
        return ReferenceReviewService(self.lib,self.authority,**{
            "review_root":self.review,"catalog_release_root":self.catalog_release,
            "reference_release_root":self.ref_release,"calibrations":self.cal,
            "capabilities":self.caps,**overrides})

    def approve_catalog(self):
        submitted=self.service.submit_catalog(self.author,self.record)
        self.assertEqual(submitted["status"],"REVIEW_READY")
        self.service.approve(self.reviewer,submitted["reviewId"],"synthetic catalog review record")
        return submitted

    def create_reference(self, **changes):
        data=synthetic_profile()
        data["metadata"].update(family_id=self.record.family,variant_id=self.record.variant,
            profile_id=self.record.profile_id,profile_revision=self.record.revision,
            status="DRAFT",approval_scopes=[],content_sha256=None)
        data["provenance_release"].update(release_approval=None,released_snapshot_sha256=None)
        data["validation_policies"]["readiness_by_scope_and_physical_state"][0]["approved"]=False
        data["inspection_workflows"]["recipes"][0].update(required_modules=[],required_view_ids=["v1"])
        view=data["photography_recipes"]["recipes"][0]["views"][0]
        view["view_id"]="v1";view["camera_goal"]["translation_mm"]=[10,20,50]
        data["pcb_definition"]["regions_of_interest"][0]["rectangle_xywh_mm"]=[5,5,20,30]
        image=self.service.ingest_image(self.author,self.image)
        self.assertEqual(image["status"],"UNVERIFIED")
        data["reference_assets"]["assets"][0].update(relative_path=image["relative_path"],
            sha256=image["sha256"],bytes=image["size"],mime=image["mime"])
        data["provenance_release"]["asset_hashes"][0]["sha256"]=image["sha256"]
        if "mutate" in changes: changes["mutate"](data)
        draft=load_json(json.dumps(data))
        etag=self.lib.store.save(self.record.profile_id,draft,create=True)
        return draft,etag,image

    def submit_reference(self,etag):
        return self.service.submit_reference(self.author,self.record.profile_id,etag,"pcb_exposed_top","photo")

    def test_full_review_approval_and_actual_runtime_compiler(self):
        catalog_review=self.approve_catalog()
        self.assertEqual(self.service.inspect(self.reviewer,catalog_review["reviewId"])["status"],"APPROVED")
        draft,etag,image=self.create_reference()
        self.assertEqual(evaluate_readiness(draft,"pcb_exposed_top","photo","photo_inspection",
            capabilities=self.caps,calibrations=self.cal,asset_ids_verified={"image"}).status,"NOT_READY")
        result=self.submit_reference(etag);rid=result["reviewId"]
        report=self.service.inspect(self.reviewer,rid)
        self.assertEqual(report["status"],"REVIEW_READY")
        self.assertEqual(report["review"]["document"]["metadata"]["status"],"REVIEW_READY")
        self.assertIsNone(report["review"]["document"]["provenance_release"]["release_approval"])
        self.assertEqual(report["review"]["assets"][0]["sha256"],image["sha256"])
        self.assertEqual(self.service.read_review_image(self.reviewer,rid,"image"),(self.image,"image/png"))
        candidate=load_json(json.dumps(report["review"]["document"]))
        with self.assertRaises(ValueError):
            compile_profile(candidate,"pcb_exposed_top","photo",None,None,None,{})
        approval=self.service.approve(self.reviewer,rid,"synthetic independent reference review")
        self.assertEqual(approval["status"],"APPROVED")
        self.assertEqual(self.service.inspect(self.author,rid)["status"],"APPROVED")
        self.assertEqual(self.lib.store.get(self.record.profile_id),(draft,etag))
        self.assertEqual(len(self.lib.history(self.record.profile_id)),1)
        with ReleaseStore(self.catalog_release) as ecu, ReferenceReleaseStore(self.ref_release) as refs, AssetStore(self.lib.store.root) as assets:
            record=ecu.read(self.record.profile_id,self.record.revision)
            profile=refs.read(self.record.profile_id,self.record.revision)
            self.assertEqual(record.status,"APPROVED")
            self.assertEqual(record.approval.reviewer_id,"reviewer")
            self.assertEqual(profile.data["metadata"]["status"],"APPROVED")
            self.assertEqual(profile.data["provenance_release"]["release_approval"]["reviewer_id"],"reviewer")
            catalog=ECUCatalog();catalog.register(record)
            library=ReferenceLibrary();library.register(profile)
            bundle=compile_profile(profile,"pcb_exposed_top","photo",record,catalog,ecu,self.cal,
                capabilities=self.caps,asset_store=assets,reference_release_store=refs,library=library)
            self.assertEqual(bundle.reference_sha256,approval["releaseSha256"])
            self.assertEqual(bundle.record_sha256,record_sha256(record))
            self.assertEqual(bundle.asset_hashes[0].sha256,image["sha256"])
        # The same revision cannot be silently republished.
        with self.assertRaises(ReviewConflict): self.service.approve(self.reviewer,rid,"duplicate")

    def test_roles_and_independent_reviewer(self):
        with self.assertRaises(ValueError):
            ReviewAuthority(self.identity,authors={"author"},reviewers={"author"})
        for token in (self.reader,self.reviewer,self.outsider,"invalid"):
            with self.assertRaises(AccessDenied): self.service.submit_catalog(token,self.record)
        r=self.service.submit_catalog(self.author,self.record)["reviewId"]
        for token in (self.author,self.reader,self.outsider,"invalid"):
            with self.assertRaises(AccessDenied): self.service.approve(token,r,"not authorized")
        with self.assertRaises(AccessDenied): self.service.inspect(self.outsider,r)
        self.assertEqual(list(self.catalog_release.iterdir()),[])
        self.identity.logout(self.reviewer)
        with self.assertRaises(AccessDenied): self.service.approve(self.reviewer,r,"revoked")

    def test_incomplete_real_catalog_blocked(self):
        real=self.lib.catalog.get("ETC3","provisional_3connector","v1")
        blockers=catalog_review_blockers(real,{},set())
        self.assertIn("verified body envelope required",blockers)
        self.assertIn("verified PCB regions required",blockers)
        self.assertIn("verified views and orientations required",blockers)
        with self.assertRaises(ReviewBlocked): self.service.submit_catalog(self.author,real)
        self.assertEqual(list(self.review.iterdir()),[])
        self.assertEqual(list(self.catalog_release.iterdir()),[])

    def test_unreleased_catalog_blocks_reference(self):
        _,etag,_=self.create_reference()
        with self.assertRaisesRegex(ReviewBlocked,"matching approved catalog"):
            self.submit_reference(etag)
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_stale_draft_etag_and_snapshot(self):
        self.approve_catalog()
        draft,etag,_=self.create_reference()
        rid=self.submit_reference(etag)["reviewId"]
        d=thaw(draft.data);d["identity"]["manufacturer"]="edited after submit"
        self.lib.update_draft(self.record.profile_id,d,etag)
        self.assertEqual(self.service.inspect(self.reviewer,rid)["status"],"STALE")
        with self.assertRaises(ReviewConflict): self.service.approve(self.reviewer,rid,"stale")
        with self.assertRaises(ReviewConflict): self.submit_reference(etag)
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_configuration_change_requires_new_review(self):
        r=self.service.submit_catalog(self.author,self.record)["reviewId"]
        other=self.make_service(capabilities=self.caps|{"extra"})
        self.assertEqual(other.inspect(self.reviewer,r)["status"],"STALE")
        with self.assertRaises(ReviewConflict): other.approve(self.reviewer,r,"stale config")
        self.assertEqual(list(self.catalog_release.iterdir()),[])

    def test_corrupt_image_after_review_is_rejected(self):
        self.approve_catalog()
        _,etag,image=self.create_reference()
        rid=self.submit_reference(etag)["reviewId"]
        p=self.lib.store.root/"assets"/image["sha256"]
        p.write_bytes(b"X"*len(self.image))
        with self.assertRaises(ReviewBlocked): self.service.read_review_image(self.reviewer,rid,"image")
        with self.assertRaises(ReviewBlocked): self.service.approve(self.reviewer,rid,"asset changed")
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_no_author_supplied_approval_flag(self):
        self.approve_catalog()
        _,etag,_=self.create_reference(mutate=lambda d:d["validation_policies"]["readiness_by_scope_and_physical_state"][0].update(approved=True))
        with self.assertRaises(ReviewBlocked): self.submit_reference(etag)
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_assets_missing_manifest_and_wrong_mime(self):
        self.approve_catalog()
        draft,etag,_=self.create_reference(mutate=lambda d:d["provenance_release"].update(asset_hashes=[]))
        with self.assertRaisesRegex(ReviewBlocked,"complete asset manifest"):
            self.submit_reference(etag)
        d=thaw(draft.data);a=d["reference_assets"]["assets"][0]
        d["provenance_release"]["asset_hashes"]=[{"asset_id":a["asset_id"],"sha256":a["sha256"]}]
        a["mime"]="image/jpeg"
        new=self.lib.update_draft(self.record.profile_id,d,etag)
        with self.assertRaisesRegex(ReviewBlocked,"size or MIME"):
            self.submit_reference(new["etag"])
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_compiler_preflight_rejects_geometry_mismatch_before_release(self):
        self.approve_catalog()
        _,etag,_=self.create_reference(mutate=lambda d:d["geometry"]["per_physical_state"][1].update(envelope_xyz_mm=[101,80,20]))
        with self.assertRaisesRegex(ReviewBlocked,"envelope mismatch"):
            self.submit_reference(etag)
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_review_envelope_integrity_and_no_overwrite(self):
        rid=self.service.submit_catalog(self.author,self.record)["reviewId"]
        path=self.review/(rid+".json")
        raw=path.read_bytes()
        with ReviewStore(self.review) as store:
            doc=store.read(rid)
            with self.assertRaises(FileExistsError): store.publish(doc)
        self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        path.write_bytes(raw+b" ")
        with self.assertRaises(ValueError): self.service.approve(self.reviewer,rid,"tampered")
        self.assertEqual(list(self.catalog_release.iterdir()),[])

    def test_catalog_revision_not_replaced_or_duplicated(self):
        self.approve_catalog()
        for r in (self.record,replace(self.record,profile_id="different-key")):
            with self.assertRaises(ReviewBlocked): self.service.submit_catalog(self.author,r)
        self.assertEqual(len(list(self.catalog_release.glob("*.json"))),1)

    def test_reference_rejects_nonmanaged_asset_path(self):
        self.approve_catalog()
        _,etag,_=self.create_reference(mutate=lambda d:d["reference_assets"]["assets"][0].update(relative_path="elsewhere/file.png"))
        with self.assertRaisesRegex(ReviewBlocked,"managed reviewed reference image"):
            self.submit_reference(etag)
        self.assertEqual(list(self.ref_release.iterdir()),[])

    def test_prepared_etc3_workspace_keeps_only_existing_unverified_facts(self):
        self.root.chmod(0o700)
        target=self.root/"etc3-preparation"
        report=prepare_workspace(target,family="ETC3",variant="provisional_3connector",
            base_revision="v1",profile_id="etc3_poc_v2",revision="v2",display_name="ETC3")
        self.assertEqual(report["status"],"DRAFT")
        self.assertFalse(report["approvalConfigured"])
        status=_status(target,_config(target))
        self.assertEqual(status["fieldNoteCount"],2)
        self.assertFalse(status["verifiedEnvelope"])
        candidate=load_catalog((target/"catalog-candidate.json").read_bytes())
        self.assertEqual({n.reported_height_mm for n in candidate.field_notes},{65,69})
        self.assertTrue(all(n.provenance.status=="FIELD_NOTE" for n in candidate.field_notes))
        self.assertIsNone(candidate.envelope)
        self.assertFalse(candidate.views)
        self.assertFalse(candidate.pcb_regions)
        draft=ECULibraryService(target/"library").get_draft("etc3_poc_v2")["profile"]
        self.assertFalse(draft["physical_states"][0]["verified"])
        self.assertEqual(draft["geometry"]["per_physical_state"],[])
        self.assertEqual(list((target/"catalog-release").iterdir()),[])
        self.assertEqual(list((target/"reference-release").iterdir()),[])
        with self.assertRaises(FileExistsError):
            prepare_workspace(target,family="ETC3",variant="provisional_3connector",
                base_revision="v1",profile_id="etc3_poc_v2",revision="v2",display_name="ETC3")

    def test_reviewer_revocation_during_preflight_blocks_publication(self):
        r=self.service.submit_catalog(self.author,self.record)["reviewId"]
        original=self.service._check_catalog_candidate
        def check(record):
            original(record)
            self.identity.logout(self.reviewer)
        with patch.object(self.service,"_check_catalog_candidate",side_effect=check):
            with self.assertRaises(AccessDenied):
                self.service.approve(self.reviewer,r,"revoked")
        self.assertEqual(list(self.catalog_release.iterdir()),[])

    def test_private_directories_required(self):
        self.review.chmod(0o755)
        with self.assertRaises(ValueError): self.make_service()
        self.review.chmod(0o700)
        alias=self.root/"alias";alias.symlink_to(self.review)
        with self.assertRaises(ValueError): self.make_service(review_root=alias)
        with self.assertRaises(ValueError): self.make_service(reference_release_root=self.review)


if __name__=="__main__": unittest.main()
