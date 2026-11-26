"""Simplified V2 authoring in the same generation store (synthetic only)."""
import base64
import copy
import json
from pathlib import Path
import unittest

from vision_api.access import Credentials
from vision_station.draft_editor import DraftConflict, DraftNotFound, validate_draft_report
from vision_station.host import CoreHost
import test_draft_editor as fixture
from test_draft_editor_forms import image_bytes


def payload(family="Synthetic Family",variant="285"):
    return {
        "identity":{"manufacturer":"Synthetic","manufacturer_part_numbers":["TEST-PN"],"oem_part_numbers":["TEST-OE"],
                    "aliases":[],"displayName":"Synthetic ECU"},
        "declaration":{"schema":"vision.ecu-declaration.v2","familyLabel":family,"variantLabel":variant,
            "states":[{"stateId":"pcb_top","dimensionsMm":[100.25,80,None]}],
            "photos":[],"inspection":{"template":"standard_pcb","overview":True,"oblique":False,
                                      "details":False,"customRoi":True,"notes":"Declared only\nNo executable recipe"}}
    }


class BasicProfileTests(unittest.TestCase):
    setUp=fixture.DraftEditorTests.setUp

    def create_basic(self,p=None,key="basic-test"):
        return self.host.draft_editor("create_basic",{"instanceId":self.instance,"key":key,"document":p or payload()})

    def action(self,name,report,**extra):
        return self.host.draft_editor(name,{"instanceId":self.instance,"key":report["key"],"etag":report["etag"],**extra})

    def get(self,key):
        return self.host.draft_editor("open",{"instanceId":self.instance,"key":key})

    def test_create_partial_and_revision_history(self):
        p=payload()
        r=self.create_basic(p)
        self.assertTrue(validate_draft_report(r))
        self.assertEqual(r["document"]["metadata"]["family_id"],"Synthetic_Family")
        self.assertEqual(r["document"]["metadata"]["profile_revision"],"r1")
        self.assertEqual(r["declaration"],p["declaration"])
        self.assertEqual(r["document"]["geometry"]["per_physical_state"],[])
        self.assertEqual(r["document"]["provenance_release"]["measurement_sources"],[])
        self.assertEqual(r["document"]["inspection_workflows"]["recipes"],[])
        self.assertEqual(r["document"]["metadata"]["status"],"DRAFT")
        self.assertFalse(self.host.inspection_report()["startAllowed"])
        with self.assertRaises(DraftConflict): self.create_basic(payload("synthetic_family"),key="duplicate")
        p["declaration"]["states"][0]["dimensionsMm"][2]=20.5
        saved=self.action("save_basic",r,document=p)
        self.assertNotEqual(saved["etag"],r["etag"])
        with self.assertRaises(DraftConflict):self.action("save_basic",r,document=p)
        with self.assertRaises(DraftConflict):self.action("save",saved,document=saved["document"])
        with self.assertRaises(ValueError):self.action("submit_review",saved)
        entries=self.host.library_reader.library_report(Credentials())
        item=next(x for x in entries["entries"] if x["profileId"]=="basic-test")
        self.assertTrue(item["simplified"])
        self.assertIn("TEST-OE",item["searchTerms"])
        self.assertEqual(item["readiness"],"NOT_READY")
        detail=self.host.library_reader.entry_report(Credentials(),entry_id=item["entryId"],view=entries["viewId"])
        self.assertEqual(detail["profile"]["physicalStates"],[{"id":"pcb_top","displayName":"Exposed PCB top","declaredVerified":False}])
        history=self.host.library.history("basic-test")
        self.assertEqual(len(history),2)
        historic=self.action("open_generation",saved,snapshotId=history[0]["snapshot_id"])
        self.assertEqual(historic["declaration"]["states"][0]["dimensionsMm"],[100.25,80,None])
        archived=self.action("archive",saved)
        self.assertEqual(archived["lifecycle"],"ARCHIVED")
        self.assertEqual(archived["declaration"],saved["declaration"])
        with self.assertRaises(DraftConflict):self.action("save_basic",archived,document=p)
        restored=self.action("restore",archived)
        clone=self.action("clone_basic",restored,newKey="basic-test-next")
        self.assertEqual(clone["document"]["metadata"]["profile_revision"],"r2")
        self.assertEqual(clone["declaration"],saved["declaration"])
        clone2=self.action("clone_basic",restored,newKey="basic-test-third")
        self.assertEqual(clone2["document"]["metadata"]["profile_revision"],"r3")
        again=CoreHost(self.root/"library",diagnostics=lambda:())
        reopened=again.draft_editor("open",{"instanceId":again.station_report()["instanceId"],"key":clone["key"]})
        self.assertEqual(reopened["declaration"],saved["declaration"])
        self.assertEqual(reopened["etag"],clone["etag"])

    def test_validation_preserves_incomplete_unmeasured_data(self):
        for edit in (
            lambda p:p["declaration"]["states"][0]["dimensionsMm"].__setitem__(0,0),
            lambda p:p["declaration"]["states"][0]["dimensionsMm"].__setitem__(0,True),
            lambda p:p["declaration"]["states"].append(copy.deepcopy(p["declaration"]["states"][0])),
            lambda p:p["declaration"]["inspection"].update(template="arbitrary"),
            lambda p:p["declaration"].update(approved=True),
            lambda p:p["declaration"].update(familyLabel="invalid/label"),
        ):
            with self.subTest(edit=edit):
                p=payload();edit(p)
                with self.assertRaises(ValueError):self.create_basic(p)
                self.assertEqual(self.host.library.store.keys(),[])
        r=self.create_basic()
        p=payload();p["declaration"]["familyLabel"]="changed"
        with self.assertRaises(ValueError):self.action("save_basic",r,document=p)
        self.assertEqual(self.get(r["key"]),r)

    def test_photos_are_managed_not_fabricated(self):
        r=self.create_basic()
        raw=image_bytes()
        imported=self.action("asset_import",r,data=base64.b64encode(raw).decode("ascii"))
        p=payload()
        photo={"sha256":imported["sha256"],"bytes":imported["bytes"],"mime":imported["mime"],"stateId":"pcb_top","role":"pcb_top"}
        p["declaration"]["photos"]=[photo]
        with self.assertRaises(DraftNotFound):self.action("asset_preview",r,assetId=photo["sha256"])
        bad=copy.deepcopy(p);bad["declaration"]["photos"][0]["bytes"]+=1
        with self.assertRaises(ValueError):self.action("save_basic",r,document=bad)
        bad=copy.deepcopy(p);bad["declaration"]["photos"][0]["stateId"]="closed"
        with self.assertRaises(ValueError):self.action("save_basic",r,document=bad)
        saved=self.action("save_basic",r,document=p)
        preview=self.action("asset_preview",saved,assetId=photo["sha256"])
        self.assertEqual(base64.b64decode(preview["data"]),raw)
        self.assertEqual(preview["status"],"UNVERIFIED")
        self.assertEqual(saved["document"]["reference_assets"]["assets"],[])
        p["declaration"]["photos"]=[]
        removed=self.action("save_basic",saved,document=p)
        self.assertEqual(removed["declaration"]["photos"],[])
        self.assertTrue((self.host.library.store.root/"assets"/photo["sha256"]).is_file())
        self.assertEqual(self.host.library.history(r["key"])[1]["declaration"]["photos"],[photo])

    def test_adopt_only_empty_legacy_document(self):
        p=payload()
        old=self.host.draft_editor("create_empty",{"instanceId":self.instance,"key":"old-profile","family":"Synthetic_Family","variant":"285","revision":"r11","displayName":"Legacy"})
        self.assertTrue(old["basicEligible"])
        saved=self.action("save_basic",old,document=p)
        self.assertEqual(saved["document"]["metadata"]["profile_revision"],"r11")
        self.assertNotIn("basicEligible",saved)
        self.assertEqual(len(self.host.library.history("old-profile")),2)
        self.assertNotIn("declaration",self.host.library.history("old-profile")[0])
        self.assertEqual(self.action("clone_basic",saved,newKey="next-profile")["document"]["metadata"]["profile_revision"],"r12")
        full=json.loads(Path("webgui/tests/fixtures/editor-profile.json").read_text())
        m=full["metadata"]
        legacy=self.host.draft_editor("create_empty",{"instanceId":self.instance,"key":m["profile_id"],"family":m["family_id"],"variant":m["variant_id"],"revision":m["profile_revision"],"displayName":m["display_name"]})
        legacy=self.action("save",legacy,document=full)
        self.assertNotIn("basicEligible",legacy)
        with self.assertRaises(ValueError):self.action("save_basic",legacy,document=payload(m["family_id"],m["variant_id"]))
        self.assertEqual(self.get(legacy["key"]),legacy)
