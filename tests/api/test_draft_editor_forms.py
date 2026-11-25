"""Neutral synthetic reference forms and private image transport."""
import base64
import copy
import hashlib
import json
import struct
from pathlib import Path
import threading
import unittest

import cv2
import numpy as np

import test_draft_editor as fixture
from vision_api.identity import provision_account
from vision_station.client import RemoteStationOwner
from vision_station.draft_editor import (DraftConflict,DraftNotFound,
    ASSET_LIMIT,DraftRequestInvalid,validate_asset_report)
from vision_station.host import CoreHost
from vision_station.server import CoreServer


def image_bytes(large=False):
    pixels=(np.random.default_rng(42).integers(0,256,(400,400,3),dtype=np.uint8)
            if large else np.full((32,48,3),113,dtype=np.uint8))
    ok,encoded=cv2.imencode(".png",pixels)
    assert ok
    return encoded.tobytes()


class FormEditorTests(unittest.TestCase):
    setUp=fixture.DraftEditorTests.setUp
    open=fixture.DraftEditorTests.open
    save=fixture.DraftEditorTests.save

    def new(self,**changes):
        return self.host.draft_editor("create_empty",{
            "instanceId":self.instance,"family":"fixture-family","variant":"fixture-variant",
            "key":self.key,"revision":"r1","displayName":"Neutral test draft",**changes})

    def test_unregistered_family_is_unsigned_only(self):
        before=self.host.library.catalog.list_records()
        report=self.new()
        self.assertEqual(report["document"]["metadata"]["family_id"],"fixture-family")
        self.assertEqual(report["document"]["physical_states"],[])
        self.assertEqual(report["document"]["geometry"]["per_physical_state"],[])
        self.assertEqual(report["document"]["metadata"]["status"],"DRAFT")
        self.assertEqual(self.host.library.catalog.list_records(),before)
        with self.assertRaises(DraftConflict):self.new()
        self.assertEqual(self.host.station_report()["state"],"NO_ACTIVE_SESSION")

    def test_all_sections_fixture_and_locked_approval(self):
        value=json.loads(Path("webgui/tests/fixtures/editor-profile.json").read_text())
        report=self.new(key=value["metadata"]["profile_id"])
        saved=self.save(report,value)
        self.assertEqual(saved["document"],value)
        args={"instanceId":self.instance,"key":report["key"],"document":value}
        diag=self.host.draft_editor("validate_structure",args)
        self.assertTrue(diag["valid"])
        self.assertEqual(diag["status"],"NOT_READY")
        tampered=copy.deepcopy(value)
        tampered["validation_policies"]["readiness_by_scope_and_physical_state"][0]["approved"]=True
        with self.assertRaises(ValueError):self.save(saved,tampered)
        self.assertFalse(self.host.draft_editor("validate_structure",{**args,"document":tampered})["valid"])

    def test_blank_structure_check_needs_no_specimen_or_recipe(self):
        report=self.new()
        args={"instanceId":self.instance,"key":self.key,"document":report["document"]}
        result=self.host.draft_editor("validate_structure",args)
        self.assertTrue(result["valid"])
        self.assertEqual(result["status"],"NOT_READY")
        self.assertEqual(self.open(),report)
        bad=copy.deepcopy(report["document"]);bad["geometry"]["other"]=False
        self.assertFalse(self.host.draft_editor("validate_structure",{**args,"document":bad})["valid"])

    def test_reference_import_and_preview_are_bound_to_saved_draft(self):
        report=self.new()
        raw=image_bytes()
        args={"instanceId":self.instance,"key":self.key,"etag":report["etag"]}
        imported=self.host.draft_editor("asset_import",{**args,"data":base64.b64encode(raw).decode("ascii")})
        self.assertTrue(validate_asset_report(imported))
        self.assertEqual(imported["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(imported["status"],"UNVERIFIED")
        self.assertEqual(self.open(),report)
        with self.assertRaises(DraftNotFound):
            self.host.draft_editor("asset_preview",{**args,"assetId":"photo-test"})
        doc=copy.deepcopy(report["document"])
        doc["physical_states"]=[dict(state_id="state-test",display_name="Synthetic state",geometry_id=None,required_recipe_ids=[],verified=False,source_id=None)]
        doc["provenance_release"]["measurement_sources"]=[dict(source_id="source-test",date="2026-01-01",status="MEASURED",instrument="synthetic",datum="synthetic",uncertainty_mm=.1,reference="test")]
        doc["reference_assets"]["assets"]=[dict(asset_id="photo-test",kind="photo",relative_path=imported["relativePath"],
            sha256=imported["sha256"],bytes=imported["bytes"],mime=imported["mime"],physical_state_id="state-test",source_id="source-test",verified=False,privacy_class="private")]
        doc["provenance_release"]["asset_hashes"]=[dict(asset_id="photo-test",sha256=imported["sha256"])]
        saved=self.save(report,doc)
        with self.assertRaises(DraftConflict):self.host.draft_editor("asset_preview",{**args,"assetId":"photo-test"})
        args["etag"]=saved["etag"]
        result=self.host.draft_editor("asset_preview",{**args,"assetId":"photo-test"})
        self.assertTrue(validate_asset_report(result,preview=True))
        self.assertEqual(base64.b64decode(result["data"]),raw)
        p=self.host.library.store.root/"assets"/imported["sha256"]
        p.write_bytes(b"X"*len(raw))
        with self.assertRaises(ValueError):self.host.draft_editor("asset_preview",{**args,"assetId":"photo-test"})

    def test_preview_accepts_reference_ids_via_ipc_without_path_access(self):
        report=self.new()
        raw=image_bytes()
        sock=self.root/"ipc/core.sock"
        server=CoreServer(sock,self.host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        proxy=RemoteStationOwner(sock)
        args={"instanceId":self.instance,"key":self.key,"etag":report["etag"]}
        imported=proxy.draft_editor("asset_import",{**args,"data":base64.b64encode(raw).decode("ascii")})
        doc=copy.deepcopy(report["document"])
        doc["physical_states"]=[dict(state_id="state-test",display_name="Synthetic state",geometry_id=None,required_recipe_ids=[],verified=False,source_id=None)]
        doc["provenance_release"]["measurement_sources"]=[dict(source_id="source-test",date="2026-01-01",status="MEASURED",instrument="synthetic",datum="synthetic",uncertainty_mm=.1,reference="test")]
        asset_ids=("photo.test","p"+"a"*126+".")
        for asset_id in asset_ids:
            doc["reference_assets"]["assets"].append(dict(asset_id=asset_id,kind="photo",relative_path=imported["relativePath"],
                sha256=imported["sha256"],bytes=imported["bytes"],mime=imported["mime"],physical_state_id="state-test",source_id="source-test",verified=False,privacy_class="private"))
            doc["provenance_release"]["asset_hashes"].append(dict(asset_id=asset_id,sha256=imported["sha256"]))
        saved=proxy.draft_editor("save",{**args,"document":doc})
        args["etag"]=saved["etag"]
        for asset_id in asset_ids:
            with self.subTest(asset_id=asset_id):
                result=proxy.draft_editor("asset_preview",{**args,"assetId":asset_id})
                self.assertEqual(result["assetId"],asset_id)
                self.assertEqual(base64.b64decode(result["data"]),raw)
                self.assertTrue(validate_asset_report(result,preview=True))
        for invalid in ("../photo", "photo/test", "a"*129):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DraftRequestInvalid):
                    proxy.draft_editor("asset_preview",{**args,"assetId":invalid})
                self.assertFalse(validate_asset_report({**result,"assetId":invalid},preview=True))

    def test_import_rejects_malformed_oversize_and_stale_requests(self):
        report=self.new()
        args={"instanceId":self.instance,"key":self.key,"etag":report["etag"]}
        raw=image_bytes()
        oversize_header=raw[:16]+struct.pack(">II",20000,20000)+raw[24:]
        for data in ("bad!",base64.b64encode(b"not image").decode(),
                     base64.b64encode(oversize_header).decode(),base64.b64encode(b"x"*(ASSET_LIMIT+1)).decode()):
            with self.assertRaises(ValueError):
                self.host.draft_editor("asset_import",{**args,"data":data})
        with self.assertRaises(DraftConflict):
            self.host.draft_editor("asset_import",{**args,"etag":'"'+'0'*64+'"',"data":base64.b64encode(raw).decode()})
        self.assertEqual(list((self.host.library.store.root/"assets").iterdir()),[])


class FormEditorHTTPTests(unittest.TestCase):
    setUp=fixture.DraftEditorHttpTests.setUp
    request=fixture.DraftEditorHttpTests.request
    login=fixture.DraftEditorHttpTests.login

    def test_neutral_creation_and_large_image_via_real_ipc(self):
        host=CoreHost(self.root/"forms-library",diagnostics=lambda:())
        sock=self.root/"ipc/core.sock"
        server=CoreServer(sock,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01})
        thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        self.app.owner=RemoteStationOwner(sock)
        instance=host.station_report()["instanceId"]
        create={"instanceId":instance,"family":"neutral-family","variant":"neutral-variant","key":"neutral","revision":"r1","displayName":"Neutral"}
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui"}
        def post(action,value,cookie=None):
            return self.request("/api/v1/library/editor/"+action,method="POST",value=value,cookie=cookie,headers=headers)
        self.assertEqual(post("create_empty",create)["status"],401)
        _,reader=self.login()
        self.assertEqual(post("create_empty",create,reader)["status"],403)
        provision_account(self.accounts,"operator",self.password,replace=True,role="operator")
        _,operator=self.login()
        response=post("create_empty",create,operator)
        self.assertEqual(response["status"],200)
        report=response["json"]
        raw=image_bytes(large=True)
        self.assertGreater(len(raw),128*1024)
        args={"instanceId":instance,"key":"neutral","etag":report["etag"],"data":base64.b64encode(raw).decode()}
        self.assertEqual(post("asset_import",args,reader)["status"],401)
        imported=post("asset_import",args,operator)
        self.assertEqual(imported["status"],200)
        self.assertEqual(imported["json"]["bytes"],len(raw))
        self.assertEqual(imported["json"]["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(post("asset_import",{**args,"data":"bad!"},operator)["status"],400)
        self.assertEqual(host.station_report()["state"],"NO_ACTIVE_SESSION")


if __name__=="__main__":unittest.main()
