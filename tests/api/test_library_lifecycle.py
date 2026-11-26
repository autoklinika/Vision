"""Synthetic library management and trusted review; no equipment or production."""
import base64
import copy
from dataclasses import replace
import subprocess
import threading
import json
from pathlib import Path
import sys
import tempfile
import unittest

from vision_api.access import Credentials
from vision_api.library_reports import validate_library_report, validate_library_history_report
from vision_station.draft_editor import DraftConflict, DraftNotFound, validate_draft_report
from vision_station.host import CoreHost
from vision_station.inspection import RuntimeComposition, DEVICES, DeviceStatus
from vision_core.profiles import PROFILE_KINDS, Profile
from vision_core import State
from vision_runtime import ReadinessReceipt
import time
from vision_station.reference_review import (publish_reviewed_reference, approved_selections, unsigned_content,
    ReviewAuthority, ReviewIntent, review_intent_bytes, Ed25519ReviewVerifier)
from vision_modules.ecu_reference import ReferenceLibrary, ReferenceReleaseStore, content_sha256
from vision_modules.ecu_profiles import record_sha256, canonical_json as canonical_catalog
from vision_station.server import CoreServer
from vision_station.client import RemoteStationOwner
from vision_api.identity import provision_account
import test_station as station_fixture
from vision_modules.ecu_reference.models import thaw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"core"))
import test_ecu_reference_execution as fixtures


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.host=CoreHost(self.root/"library",diagnostics=lambda:())
        self.instance=self.host.station_report()["instanceId"]
        self.base={"instanceId":self.instance,"key":"test-profile"}
        self.created=self.host.draft_editor("create_empty",{**self.base,"family":"test-family",
            "variant":"test-variant","revision":"r1","displayName":"Synthetic test"})

    def run_action(self,action,report,**args):
        return self.host.draft_editor(action,{**self.base,"etag":report["etag"],**args})

    def test_archive_restore_history_and_restart(self):
        doc=copy.deepcopy(self.created["document"])
        doc["identity"].update(manufacturer="Synthetic Manufacturer",oem_part_numbers=["OE-12345"])
        saved=self.run_action("save",self.created,document=doc)
        archived=self.run_action("archive",saved)
        self.assertTrue(validate_draft_report(archived))
        self.assertEqual(archived["lifecycle"],"ARCHIVED")
        self.assertNotEqual(saved["etag"],archived["etag"])
        self.assertEqual(doc,archived["document"])
        with self.assertRaises(DraftConflict):self.run_action("save",archived,document=doc)
        with self.assertRaises(DraftConflict):self.run_action("restore",saved)
        library=self.host.library_reader.library_report(Credentials())
        self.assertTrue(validate_library_report(library))
        entry=next(e for e in library["entries"] if e["profileId"]=="test-profile")
        self.assertEqual(entry["lifecycle"],"ARCHIVED")
        self.assertIn("OE-12345",entry["searchTerms"])
        history=self.host.library_reader.history_report(Credentials(),entry_id=entry["entryId"],view=library["viewId"])
        self.assertTrue(validate_library_history_report(history))
        self.assertEqual(history["items"][-1]["lifecycle"],"ARCHIVED")
        old=self.run_action("open_generation",archived,snapshotId=history["items"][0]["snapshotId"])
        self.assertTrue(validate_draft_report(old))
        self.assertEqual(old["document"],self.created["document"])
        with self.assertRaises(DraftNotFound):self.run_action("open_generation",archived,snapshotId="a"*32)
        self.host=CoreHost(self.root/"library",diagnostics=lambda:())
        self.base["instanceId"]=self.host.station_report()["instanceId"]
        current=self.host.draft_editor("open",self.base)
        self.assertEqual(current["lifecycle"],"ARCHIVED")
        restored=self.run_action("restore",current)
        self.assertNotIn("lifecycle",restored)
        self.assertEqual(len(self.host.library.history("test-profile")),4)
        self.assertEqual(restored["document"],doc)

    def test_history_rejects_stale_generation_and_uncommitted_snapshot(self):
        first=self.host.library.history("test-profile")[0]
        saved=self.run_action("save",self.created,document=self.created["document"])
        with self.assertRaises(DraftConflict):
            self.run_action("open_generation",self.created,snapshotId=first["snapshot_id"])
        with self.assertRaises(DraftNotFound):
            self.run_action("open_generation",saved,snapshotId="b"*32)

    def test_review_requires_workflow_and_never_approves_in_browser(self):
        with self.assertRaises(ValueError): self.run_action("submit_review",self.created)
        with self.assertRaises(ValueError): self.run_action("approve",self.created)
        with self.assertRaises(ValueError): self.run_action("release",self.created)
        self.assertFalse(self.host.inspection_report()["startAllowed"])


class TrustedReleaseTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExecutionTests.setUp(self)
        self.root=Path(self.tmp.name)
        self.host=CoreHost(self.root/"drafts-private",diagnostics=lambda:())
        self.host.library.catalog.register(self.record)
        self.reviewed=self.p
        draft=thaw(unsigned_content(self.reviewed).data)
        m=draft["metadata"]
        self.args={"instanceId":self.host.station_report()["instanceId"],"key":m["profile_id"]}
        created=self.host.draft_editor("create_empty",{**self.args,"family":m["family_id"],
            "variant":m["variant_id"],"revision":m["profile_revision"],"displayName":m["display_name"]})
        saved=self.host.draft_editor("save",{**self.args,"etag":created["etag"],"document":draft})
        self.submitted=self.host.draft_editor("submit_review",{**self.args,"etag":saved["etag"]})
        (self.root/"actual-release").mkdir()
        (self.root/"review-staging").mkdir(mode=0o700)
        self.target=ReferenceReleaseStore(self.root/"actual-release")
        self.addCleanup(self.target.close)
        self.refs=ReferenceLibrary()

    def publish(self,**changes):
        args=dict(authenticate_review=lambda intent: intent.submitted_etag==self.submitted["etag"] and intent.reviewer_id=="reviewer",
            reference_store=self.target,release_store=self.ecu,reference_library=self.refs,
            asset_store=self.assets,calibrations=self.cal,capabilities=self.caps,staging_root=self.root/"review-staging")
        args.update(changes)
        return publish_reviewed_reference(self.host,self.reviewed,self.submitted["etag"],**args)

    def test_authenticated_review_publish_and_exact_choices(self):
        self.assertEqual(self.submitted["lifecycle"],"REVIEW_READY")
        self.assertEqual(self.submitted["document"]["metadata"]["status"],"DRAFT")
        with self.assertRaises(DraftConflict):
            self.host.draft_editor("save",{**self.args,"etag":self.submitted["etag"],"document":self.submitted["document"]})
        self.assertEqual(approved_selections(self.host.library,reference_library=self.refs,reference_store=self.target,
            release_store=self.ecu,asset_store=self.assets,calibrations=self.cal,capabilities=self.caps),())
        with self.assertRaises(ValueError):self.publish(authenticate_review=lambda _:False)
        self.assertEqual(list((self.root/"actual-release").iterdir()),[])
        with self.assertRaises(ValueError):self.publish(capabilities=set())
        self.assertEqual(list((self.root/"actual-release").iterdir()),[])
        choices=self.publish()
        self.assertEqual(len(choices),1)
        self.assertEqual(choices[0].recipe,"photo")
        self.assertEqual(self.target.require(self.reviewed),self.reviewed.data["metadata"]["content_sha256"])
        saved=self.host.draft_editor("open",self.args)
        self.assertEqual(saved["lifecycle"],"RELEASED")
        self.assertEqual(saved["document"]["metadata"]["status"],"DRAFT")
        self.assertFalse(self.host.inspection_report()["startAllowed"])
        self.assertEqual(approved_selections(self.host.library,reference_library=self.refs,reference_store=self.target,
            release_store=self.ecu,asset_store=self.assets,calibrations=self.cal,capabilities=self.caps),choices)
        # Bind the real published reference to the existing Runtime
        # composition, using ONLY synthetic trusted receipt fixtures.
        session_root=self.root/"synthetic-sessions"
        session_root.mkdir(mode=0o700)
        cal=self.cal
        caps=self.caps|{"depth","camera_info","tf"}
        composition=RuntimeComposition.from_released_references(self.host.library,
            profiles={k:Profile(k,k,"1","r1",True,{"basic"},{"basic"},cal) for k in PROFILE_KINDS if k!="ecu"},
            calibrations=cal,requirements={},capabilities=caps,
            release_store=self.ecu,reference_release_store=self.target,
            reference_library=self.refs,asset_store=self.assets,trust_verifier=lambda *_:True,
            readiness_provider=lambda:tuple(DeviceStatus(d,"ACTIVE","READY",time.time()) for d in DEVICES),
            readiness_receipt_provider=lambda request:ReadinessReceipt(
                request.context.session_id,request.request_id,request.context.profile_revisions,
                cal,time.time(),"synthetic-source","sha256:"+"a"*64,True,frozenset(caps),"sha256:"+"b"*64),
            sensor_frame="camera",scene_frame="station",known_transforms={("camera","station")},
            max_age=10,max_skew=.1)
        runtime_host=CoreHost(self.root/"drafts-private",composition=composition,session_root=session_root)
        self.addCleanup(runtime_host.shutdown_inspection)
        runtime_host.library.catalog.register(self.record)
        report=runtime_host.inspection_report()
        self.assertEqual(report["selections"],[choices[0].report()])
        self.assertTrue(report["startAllowed"])
        started=runtime_host.start_inspection(selection_id=choices[0].selection_id,instance_id=report["instanceId"],
            intent_token=report["intentToken"],operator="synthetic.operator")
        self.assertEqual(started["state"],"SESSION_ACTIVE")
        self.assertEqual(runtime_host._runtime.engine.states["S01"],State.SUCCEEDED)
        self.assertEqual(runtime_host._runtime.engine.states["S02"],State.SUCCEEDED)
        self.assertTrue(all(runtime_host._runtime.engine.states[f"S{i:02}"]==State.PENDING for i in range(3,12)))
        runtime_host.close_inspection(session_id=started["sessionId"],instance_id=started["instanceId"],operator="synthetic.operator")
        self.target.close()
        self.assertEqual(approved_selections(self.host.library,reference_library=self.refs,reference_store=self.target,
            release_store=self.ecu,asset_store=self.assets,calibrations=self.cal,capabilities=self.caps),())

    def test_signed_review_via_real_http_ipc_and_restart(self):
        # A TEST-ONLY signing key and real Ed25519 verification.
        # No reviewer keys are created in operational configuration.
        key_dir=self.root/"review-staging"
        private=key_dir/"fixture-key.pem"
        public=key_dir/"fixture-key.der"
        subprocess.run(["/usr/bin/openssl","genpkey","-algorithm","ED25519","-out",str(private)],
                       check=True,capture_output=True)
        subprocess.run(["/usr/bin/openssl","pkey","-in",str(private),"-pubout","-outform","DER","-out",str(public)],
                       check=True,capture_output=True)
        raw=public.read_bytes()
        self.assertEqual(raw[:12],bytes.fromhex("302a300506032b6570032100"))
        verifier=Ed25519ReviewVerifier({"reviewer":raw[12:]},key_dir)
        approval=self.reviewed.data["provenance_release"]["release_approval"]
        intent=ReviewIntent(self.args["key"],self.submitted["etag"],content_sha256(unsigned_content(self.reviewed)),
            content_sha256(self.reviewed),record_sha256(self.record),approval["reviewer_id"],
            approval["reference"],approval["approved_at"],(("pcb_exposed_top","photo","photo_inspection"),))
        source=key_dir/"fixture-intent"
        signature=key_dir/"fixture-signature"
        source.write_bytes(review_intent_bytes(intent))
        subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-inkey",str(private),"-rawin","-in",str(source),"-out",str(signature)],
                       check=True,capture_output=True)
        proof=signature.read_bytes()
        self.assertTrue(verifier(intent,proof))
        self.assertFalse(verifier(replace(intent,submitted_etag='"'+"f"*64+'"'),proof))
        authority=ReviewAuthority(verifier,self.target,self.ecu,self.refs,self.assets,self.cal,self.caps,key_dir)
        catalog_dir=self.root/"catalog"
        catalog_dir.mkdir()
        (catalog_dir/"fixture.json").write_text(canonical_catalog(self.record))
        def factory(library):
            return RuntimeComposition.from_released_references(library,
                profiles={k:Profile(k,k,"1","r1",True,{"basic"},{"basic"},self.cal)
                          for k in PROFILE_KINDS if k!="ecu"},
                calibrations=self.cal,requirements={},capabilities=self.caps,
                release_store=self.ecu,reference_release_store=self.target,
                reference_library=self.refs,asset_store=self.assets,trust_verifier=lambda *_:False,
                readiness_provider=lambda:(),readiness_receipt_provider=lambda _:None,
                sensor_frame="camera",scene_frame="station",known_transforms={("camera","station")},
                max_age=10,max_skew=.1)
        session_root=self.root/"review-sessions"
        session_root.mkdir(mode=0o700)
        host=CoreHost(self.root/"drafts-private",catalog_dir=catalog_dir,review_authority=authority,
                      composition_factory=factory,session_root=session_root)
        self.assertEqual(host.inspection_report()["selections"],[])
        socket=self.root/"review-ipc/core.sock"
        server=CoreServer(socket,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        # Actual authenticated WSGI request -> same-UID IPC -> Core.
        web=station_fixture.StationTests()
        web.setUp()
        self.addCleanup(web.doCleanups)
        web.app.owner=RemoteStationOwner(socket)
        _,reader=web.login()
        args={**self.args,"instanceId":host.station_report()["instanceId"]}
        submitted=host.draft_editor("open",args)
        self.assertTrue(submitted["reviewAvailable"])
        request={**args,"etag":submitted["etag"],"document":thaw(self.reviewed.data),
                 "reviewProof":base64.b64encode(proof).decode("ascii")}
        def send(value,cookie):
            return web.request("/api/v1/library/editor/publish_review",method="POST",value=value,cookie=cookie,
                headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui"})
        self.assertEqual(send(request,None)["status"],401)
        self.assertEqual(send(request,reader)["status"],403)
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,operator=web.login()
        self.assertEqual(send({**request,"reviewProof":base64.b64encode(bytes(64)).decode("ascii")},operator)["status"],400)
        self.assertEqual(list((self.root/"actual-release").iterdir()),[])
        result=send(request,operator)
        self.assertEqual(result["status"],200)
        self.assertEqual(result["json"]["lifecycle"],"RELEASED")
        self.assertEqual(result["json"]["releaseDigest"],content_sha256(self.reviewed))
        self.assertTrue(validate_draft_report(result["json"]))
        self.assertEqual(len(host.inspection_report()["selections"]),1)
        self.assertFalse(host.inspection_report()["startAllowed"])
        # The durable marker rehydrates a fresh registry, not an in-memory
        # approval. A missing immutable release cannot be selected.
        self.refs=ReferenceLibrary()
        restarted=CoreHost(self.root/"drafts-private",catalog_dir=catalog_dir,composition_factory=factory,session_root=session_root)
        self.assertEqual(restarted.inspection_report()["selections"],host.inspection_report()["selections"])
        self.assertFalse(restarted.inspection_report()["startAllowed"])
        (self.root/"actual-release"/self.target._name(self.args["key"],"r1")).unlink()
        self.refs=ReferenceLibrary()
        restarted=CoreHost(self.root/"drafts-private",catalog_dir=catalog_dir,composition_factory=factory,session_root=session_root)
        self.assertEqual(restarted.inspection_report()["selections"],[])

    def test_changed_measurements_cannot_be_approved(self):
        changed=thaw(self.reviewed.data)
        changed["geometry"]["per_physical_state"][0]["envelope_xyz_mm"][0]+=1
        self.reviewed=fixtures.seal(changed)
        with self.assertRaisesRegex(ValueError,"differs"):
            self.publish()
        self.assertEqual(list((self.root/"actual-release").iterdir()),[])
        self.assertEqual(self.host.draft_editor("open",self.args)["lifecycle"],"REVIEW_READY")
