"""Read-only commissioning review boundaries, without hardware commands."""
import unittest
from unittest.mock import patch

from vision_station.nero_manual_review import ManualReviewHost
from vision_station.nero_manual_station import Candidate, STATUS
from vision_station.inspection import InspectionRejected
from vision_api.station import StationApplication
from vision_api.identity import provision_account
import test_station


class ManualReviewTests(unittest.TestCase):
    def setUp(self):
        self.web=test_station.StationTests()
        self.web.setUp()
        self.addCleanup(self.web.doCleanups)
        candidate=Candidate({"status":STATUS,"physicalExecutionAllowed":False,
            "limits":{"jointPositionRad":[[-1.,1.]]*7,
                      "controllerMaxVelocityRadS":[3.14]*7}},
            "", "", b"", (0.,)*7)
        self.host=ManualReviewHost(self.web.root/"review-library",candidate=candidate,
                                   nero_directory=self.web.root/"absent-observer")
        provision_account(self.web.accounts,"operator",self.web.password,replace=True,role="operator")
        self.web.app=StationApplication(identity=self.web.identity,owner=self.host,
            dist_root=self.web.dist,origins=["http://127.0.0.1:18490"],manual_review_local=True)
        _,self.cookie=self.web.login()
        self.headers={"REMOTE_ADDR":"127.0.0.1","HTTP_ORIGIN":"http://127.0.0.1:18490",
                      "HTTP_X_VISION_CLIENT":"webgui"}
        self.route="/api/v1/devices/nero/manual"

    def test_review_is_explicit_and_never_admits_commands(self):
        r=self.web.request(self.route,cookie=self.cookie,headers=self.headers)["json"]["status"]
        self.assertEqual(r["reason"],"REVIEW_ONLY")
        self.assertEqual((r["linearMax"],r["angularMax"]),(5,2))
        self.assertEqual(r["driveEnabled"],[None]*7)
        self.assertTrue(all(r[k] is False for k in ("pipelineReady","enableAvailable","jogAvailable","holdAvailable")))
        with patch.object(self.host,"nero_manual_command",side_effect=AssertionError("command reached Core")):
            out=self.web.request(self.route+"/command",method="POST",cookie=self.cookie,
                                 headers=self.headers,value={})
            self.assertEqual(out["status"],403)
        with self.assertRaises(InspectionRejected):self.host.start_inspection()
        with self.assertRaises(InspectionRejected):self.host.attach_runtime(None)

    def test_review_only_for_authenticated_local_operator(self):
        self.assertEqual(self.web.request(self.route,headers=self.headers)["status"],401)
        out=self.web.request(self.route,cookie=self.cookie,
                   headers={**self.headers,"REMOTE_ADDR":"192.0.2.1"})
        self.assertIsNone(out["json"]["status"])

    def test_review_listener_rejects_command_composition_and_remote_origin(self):
        args=dict(identity=self.web.identity,owner=self.host,dist_root=self.web.dist)
        with self.assertRaises(ValueError):
            StationApplication(**args,origins=["http://127.0.0.1:18490"],
                               manual_review_local=True,manual_local=True)
        with self.assertRaises(ValueError):
            StationApplication(**args,origins=["https://station.example"],manual_review_local=True)

    def test_miswired_core_does_not_appear_ready(self):
        good=self.host.nero_manual_report()
        good["status"]["enableAvailable"]=True
        with patch.object(self.host,"nero_manual_report",return_value=good):
            out=self.web.request(self.route,cookie=self.cookie,headers=self.headers)
        self.assertIsNone(out["json"]["status"])

if __name__=="__main__":
    unittest.main()
