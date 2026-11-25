"""ECU editor against isolated Core/IPC and authenticated station HTTP."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import test_station as fixture
from vision_api.access import Credentials, ReportUnavailable
from vision_api.identity import provision_account
from vision_station.client import RemoteStationOwner
from vision_station.draft_editor import (DraftConflict, DraftNotFound, DraftRequestInvalid,
    DOCUMENT_LIMIT, validate_draft_report, validate_diagnostic_report)
from vision_station.host import CoreHost
from vision_station.server import CoreServer


class DraftEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="draft-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.host=CoreHost(self.root/"library",diagnostics=lambda:())
        self.instance=self.host.station_report()["instanceId"]
        self.args={"instanceId":self.instance,"family":"ETC3","variant":"provisional_3connector",
                   "catalogRevision":"v1","key":"synthetic-draft","revision":"r1","displayName":"Synthetic ETC3"}
        self.key=self.args["key"]

    def create(self, **changes):
        return self.host.draft_editor("create",{**self.args,**changes})

    def open(self,key=None):
        return self.host.draft_editor("open",{"instanceId":self.instance,"key":key or self.key})

    def save(self, report, document, **changes):
        return self.host.draft_editor("save",{"instanceId":self.instance,"key":report["key"],
                         "etag":report["etag"],"document":document,**changes})

    def validate(self, document):
        return self.host.draft_editor("validate",{"instanceId":self.instance,"key":self.key,
                "document":document,"stateId":"pcb_exposed_top","recipeId":"photo","scope":"photo_inspection"})

    def test_create_edit_history_clone(self):
        report=self.create()
        self.assertTrue(validate_draft_report(report))
        self.assertEqual(report,self.open())
        doc=copy.deepcopy(report["document"]); doc["identity"]["manufacturer"]="Synthetic Manufacturer"
        diag=self.validate(doc)
        self.assertTrue(validate_diagnostic_report(diag))
        self.assertTrue(diag["valid"])
        self.assertEqual(diag["status"],"NOT_READY")
        self.assertIn("profile is not approved V1",diag["blockers"])
        self.assertEqual(self.open(),report) # Validation has no write side effect.
        saved=self.save(report,doc)
        self.assertNotEqual(saved["etag"],report["etag"])
        self.assertEqual(self.open(),saved)
        history=self.host.library.history(self.key)
        self.assertEqual(len(history),2)
        self.assertEqual(history[0]["profile"],report["document"])
        self.assertEqual(history[1]["profile"],doc)
        clone=self.host.draft_editor("clone",{"instanceId":self.instance,"key":self.key,
                       "etag":saved["etag"],"newKey":"synthetic-next","newRevision":"r2"})
        self.assertEqual(clone["document"]["metadata"]["profile_revision"],"r2")
        self.assertEqual(clone["document"]["identity"],doc["identity"])
        self.assertEqual(self.open(),saved)
        library=self.host.library_reader.library_report(Credentials())
        self.assertEqual(len(library["entries"]),3)
        self.assertTrue(all(e["readiness"]=="NOT_READY" for e in library["entries"]))
        self.assertEqual(self.host.station_report()["state"],"NO_ACTIVE_SESSION")

    def test_stale_etag_and_duplicate_revision_do_not_write(self):
        report=self.create()
        with self.assertRaises(DraftConflict): self.create()
        with self.assertRaises(DraftConflict): self.create(key="other-key")
        doc=copy.deepcopy(report["document"]); doc["identity"]["aliases"]=["first"]
        saved=self.save(report,doc)
        with self.assertRaises(DraftConflict): self.save(report,doc)
        with self.assertRaises(DraftConflict):
            self.host.draft_editor("clone",{"instanceId":self.instance,"key":self.key,"etag":report["etag"],
                                 "newKey":"old-copy","newRevision":"r2"})
        self.assertEqual(self.open(),saved)
        self.assertEqual(len(self.host.library.history(self.key)),2)
        self.assertEqual(self.host.library.store.keys(),[self.key])

    def test_concurrent_save_one_wins(self):
        report=self.create()
        gate=threading.Barrier(2)
        def worker(label):
            doc=copy.deepcopy(report["document"]); doc["identity"]["aliases"]=[label]
            gate.wait()
            try: return self.save(report,doc)["document"]["identity"]["aliases"][0]
            except DraftConflict: return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(worker,("one","two")))
        self.assertEqual(outcomes.count("rejected"),1)
        self.assertEqual(len(self.host.library.history(self.key)),2)
        self.assertIn(self.open()["document"]["identity"]["aliases"][0], outcomes)

    def test_draft_cannot_be_approved_or_change_identity(self):
        report=self.create()
        for change in ("APPROVED","REVIEW_READY"):
            doc=copy.deepcopy(report["document"]); doc["metadata"]["status"]=change
            self.assertFalse(self.validate(doc)["valid"])
            with self.assertRaises(ValueError): self.save(report,doc)
        for field,value in (("profile_id","other"),("family_id","OTHER"),("variant_id","other"),("profile_revision","r2")):
            doc=copy.deepcopy(report["document"]); doc["metadata"][field]=value
            with self.assertRaises(ValueError): self.save(report,doc)
        doc=copy.deepcopy(report["document"]); doc["metadata"]["content_sha256"]="a"*64
        with self.assertRaises(ValueError): self.save(report,doc)
        self.assertEqual(self.open(),report)
        self.assertEqual(len(self.host.library.history(self.key)),1)

    def test_projection_invalid_names_and_identifiers_blocked_before_save(self):
        with self.assertRaises(ValueError): self.create(displayName="path/private")
        report=self.create()
        for name in ("X"*161,"bad/name"):
            doc=copy.deepcopy(report["document"]); doc["metadata"]["display_name"]=name
            with self.assertRaises(ValueError): self.save(report,doc)
        doc=copy.deepcopy(report["document"])
        doc["physical_states"]=[{"state_id":"bad.id","display_name":"State","geometry_id":None,
                                  "required_recipe_ids":[],"verified":False,"source_id":None}]
        with self.assertRaises(ValueError): self.save(report,doc)
        self.assertEqual(len(self.host.library.history(self.key)),1)

    def test_nonexistent_and_stale_instance(self):
        with self.assertRaises(DraftNotFound): self.open("missing")
        with self.assertRaises(DraftNotFound): self.create(catalogRevision="missing")
        with self.assertRaises(DraftConflict): self.create(instanceId="0"*32)
        with self.assertRaises(ValueError): self.create(key="../bad")
        with self.assertRaises(ValueError): self.create(extra="forbidden")
        self.assertEqual(self.host.library.store.keys(),[])

    def test_mutation_blocked_during_active_or_recovery(self):
        report=self.create()
        station=self.host.station_report()
        with patch.object(self.host,"station_report",return_value={**station,"state":"SESSION_ACTIVE"}):
            with self.assertRaises(DraftConflict): self.save(report,report["document"])
        self.host._inspection._poisoned=True
        with self.assertRaises(DraftConflict): self.save(report,report["document"])
        self.assertEqual(self.open(),report)

    def test_bounded_document_and_existing_projection_budget(self):
        report=self.create()
        doc=copy.deepcopy(report["document"]); doc["identity"]["aliases"]=["x"*4000]*20
        self.assertFalse(self.validate(doc)["valid"])
        with self.assertRaises(ValueError): self.save(report,doc)
        self.assertGreater(len(json.dumps(doc)),DOCUMENT_LIMIT)
        with patch("vision_station.draft_editor._ReadBudget") as budget:
            budget.return_value.revisions_left=0
            budget.return_value.bytes_left=0
            original=self.host.library.store._chain
            def chain(key, **kwargs):
                return [] if "budget" in kwargs else original(key,**kwargs)
            with patch.object(self.host.library.store,"_chain",side_effect=chain):
                with self.assertRaises(DraftConflict): self.save(report,report["document"])
        self.assertEqual(len(self.host.library.history(self.key)),1)

    def test_real_ipc_large_document_conflict_and_invalid_request(self):
        sock=self.root/"ipc/core.sock"
        server=CoreServer(sock,self.host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        try:
            proxy=RemoteStationOwner(sock)
            report=proxy.draft_editor("create",self.args)
            doc=copy.deepcopy(report["document"]); doc["identity"]["aliases"]=["x"*4000+str(i) for i in range(5)]
            args={"instanceId":self.instance,"key":self.key,"etag":report["etag"],"document":doc}
            self.assertGreater(len(json.dumps(args)),16384)
            saved=proxy.draft_editor("save",args)
            self.assertEqual(saved["document"],doc)
            with self.assertRaises(DraftConflict): proxy.draft_editor("save",args)
            with self.assertRaises(DraftNotFound): proxy.draft_editor("open",{"instanceId":self.instance,"key":"missing"})
            with self.assertRaises(DraftRequestInvalid):
                proxy.draft_editor("save",{**args,"etag":"invalid"})
            self.assertEqual(proxy.draft_editor("open",{"instanceId":self.instance,"key":self.key}),saved)
        finally:
            server.shutdown();thread.join(3);server.server_close()


class DraftEditorHttpTests(unittest.TestCase):
    setUp=fixture.StationTests.setUp
    request=fixture.StationTests.request
    login=fixture.StationTests.login

    def test_real_http_authorization_validation_and_persistence_via_ipc(self):
        host=CoreHost(self.root/"editor-library",diagnostics=lambda:())
        sock=self.root/"ipc/core.sock"
        server=CoreServer(sock,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        self.app.owner=RemoteStationOwner(sock)
        instance=host.station_report()["instanceId"]
        payload={"instanceId":instance,"family":"ETC3","variant":"provisional_3connector",
                 "catalogRevision":"v1","key":"http-draft","revision":"r1","displayName":"Synthetic"}
        route="/api/v1/library/editor/create"
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui"}
        def post(path, value, cookie=None, **kwargs):
            return self.request("/api/v1/library/editor/"+path,method="POST",value=value,cookie=cookie,headers=headers,**kwargs)
        self.assertEqual(post("create",payload)["status"],401)
        _,reader=self.login()
        self.assertEqual(post("create",payload,reader)["json"]["code"],"OPERATOR_REQUIRED")
        self.assertEqual(host.library.store.keys(),[])
        provision_account(self.accounts,"operator",self.password,replace=True,role="operator")
        _,operator=self.login()
        self.assertEqual(self.request(route,method="POST",value=payload,cookie=operator)["json"]["code"],"ORIGIN_REJECTED")
        self.assertEqual(post("create",{**payload,"actor":"forged"},operator)["status"],400)
        result=post("create",payload,operator)
        self.assertEqual(result["status"],200); report=result["json"]
        self.assertEqual(post("create",payload,operator)["json"]["code"],"DRAFT_CONFLICT")
        doc=copy.deepcopy(report["document"]); doc["identity"]["aliases"]=["x"*4000+str(i) for i in range(5)]
        update={"instanceId":instance,"key":"http-draft","etag":report["etag"],"document":doc}
        self.assertGreater(len(json.dumps(update)),16384)
        saved=post("save",update,operator)
        self.assertEqual(saved["status"],200)
        self.assertEqual(post("save",update,operator)["status"],409)
        duplicate=json.dumps(update).replace('"document":','"document":{},"document":',1).encode()
        self.assertEqual(self.request("/api/v1/library/editor/save",method="POST",raw=duplicate,cookie=operator,headers=headers)["status"],400)
        self.assertEqual(post("open",{"instanceId":instance,"key":"missing"},operator)["status"],404)
        self.assertEqual(len(host.library.history("http-draft")),2)
        # Old endpoints retain their smaller body budget.
        oversized=json.dumps({"username":"operator","password":"x"*18000}).encode()
        self.assertEqual(self.request("/api/v1/auth/login",method="POST",raw=oversized,headers=headers)["status"],400)


if __name__=="__main__": unittest.main()
