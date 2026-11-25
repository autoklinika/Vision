"""Synthetic-only vertical slice. No production socket or equipment."""
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

# Reuse released synthetic ECU fixtures without re-discovering their tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import test_ecu_reference_execution as reference_fixture
import test_station as station_fixture
from vision_core import State
from vision_runtime import ReadinessReceipt
from vision_core.profiles import PROFILE_KINDS, Profile
from vision_api.identity import IdentityStore, provision_account
from vision_station.client import RemoteStationOwner
from vision_station.host import CoreHost
from vision_station.inspection import (DEVICES, DeviceStatus, InspectionRejected,
    RuntimeComposition, Selection, validate_inspection_report)
from vision_station.server import CoreServer


def observations(*, status="READY", offset=0):
    return tuple(DeviceStatus(d, "ACTIVE", status, time.time()+offset) for d in DEVICES)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        reference_fixture.ExecutionTests.setUp(self)
        self.root = Path(self.tmp.name)
        self.session_root = self.root / "sessions"
        self.session_root.mkdir(mode=0o700)
        self.choice = Selection("synthetic-photo", self.record.family, self.record.variant,
                                self.record.revision, "pcb_exposed_top", "photo")
        self.devices = lambda: observations()
        self.trusted = True
        self.receipt = lambda request: ReadinessReceipt(
            request.context.session_id, request.request_id, request.context.profile_revisions,
            self.cal, time.time(), "synthetic-source", "sha256:"+"a"*64, True,
            frozenset(self.caps|{"depth","camera_info","tf"}), "sha256:"+"b"*64)
        self.composition = RuntimeComposition(
            selections=[self.choice],
            profiles={k: Profile(k,k,"1","r1",True,{"basic"},{"basic"},self.cal)
                      for k in PROFILE_KINDS if k != "ecu"},
            calibrations=self.cal, requirements={}, capabilities=self.caps|{"depth","camera_info","tf"},
            release_store=self.ecu, reference_release_store=self.ref, reference_library=self.lib,
            asset_store=self.assets, trust_verifier=lambda *_: self.trusted,
            readiness_provider=lambda: self.devices(), readiness_receipt_provider=lambda request: self.receipt(request), sensor_frame="camera", scene_frame="station",
            known_transforms={("camera","station")}, max_age=10, max_skew=.1)
        self.host = CoreHost(self.root / "draft-library", composition=self.composition,
                             session_root=self.session_root, diagnostics=lambda: observations(status="UNKNOWN"))
        self.host.library.catalog.register(self.record)
        self.addCleanup(self.host.shutdown_inspection)

    def start(self, **changes):
        args = dict(selection_id=self.choice.selection_id,
                    instance_id=self.host.station_report()["instanceId"], intent_token=self.host.inspection_report()["intentToken"], operator="test.operator")
        args.update(changes)
        return self.host.start_inspection(**args)

    def close(self, **changes):
        station = self.host.station_report()
        args = dict(session_id=station["sessionId"], instance_id=station["instanceId"], operator="test.operator")
        args.update(changes)
        return self.host.close_inspection(**args)

    def test_real_runtime_verified_preparation_with_private_intent_and_journal(self):
        report = self.host.inspection_report()
        self.assertTrue(validate_inspection_report(report))
        self.assertTrue(report["startAllowed"])
        self.assertEqual(report["selections"], [self.choice.report()])
        station = self.start()
        self.assertEqual(station["state"], "SESSION_ACTIVE")
        self.assertEqual(self.host._runtime.engine.states["S01"], State.SUCCEEDED)
        self.assertEqual(self.host._runtime.engine.states["S02"], State.SUCCEEDED)
        self.assertTrue(all(self.host._runtime.engine.states[f"S{i:02}"] == State.PENDING for i in range(3,12)))
        self.assertTrue(self.host._runtime.engine.strict_planning)
        session_id = station["sessionId"]
        folder = self.session_root / session_id
        intent = json.loads((folder / "intent.json").read_text())
        self.assertEqual(intent["operator"], "test.operator")
        self.assertEqual(intent["selection"], self.choice.report())
        self.assertEqual((folder / "journal.sqlite").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.session_root / "active-session").read_text().strip(), session_id)
        self.assertEqual(self.host.session_report()["sessionId"], session_id)
        self.assertTrue(self.host.inspection_report()["closeAllowed"])
        self.assertEqual(self.close()["state"], "NO_ACTIVE_SESSION")
        self.assertFalse((self.session_root / "active-session").exists())
        self.assertTrue((folder / "closed.json").exists())
        self.assertTrue(self.host.inspection_report()["startAllowed"])
        self.assertNotEqual(self.start()["sessionId"], session_id)

    def test_missing_release_and_no_synthetic_fallback(self):
        self.ref.close()
        report = self.host.inspection_report()
        self.assertFalse(report["startAllowed"])
        self.assertIn("NO_APPROVED_SELECTION", report["blockers"])
        with self.assertRaises(InspectionRejected):
            self.start()
        self.assertFalse((self.session_root / "active-session").exists())

    def test_no_composition_and_draft_library(self):
        idle = CoreHost(self.root / "idle-library", diagnostics=lambda: observations(status="UNKNOWN"))
        report = idle.inspection_report()
        self.assertTrue(validate_inspection_report(report))
        self.assertFalse(report["startAllowed"])
        self.assertEqual(set(report["blockers"]), {"COMPOSITION_UNCONFIGURED","NO_APPROVED_SELECTION","DEVICES_NOT_VERIFIED"})
        with self.assertRaises(InspectionRejected):
            idle.start_inspection(selection_id="etc3", instance_id=report["instanceId"], intent_token=report["intentToken"], operator="operator")
        self.assertIsNone(idle._runtime)

    def test_unknown_and_stale_readiness_rejected(self):
        for provider in (lambda: observations(status="UNKNOWN"), lambda: observations(offset=-60),
                         lambda: observations(offset=60), lambda: (), lambda: (_ for _ in ()).throw(OSError())):
            with self.subTest(provider=provider):
                self.devices = provider
                report = self.host.inspection_report()
                self.assertIn("DEVICES_NOT_VERIFIED", report["blockers"])
                with self.assertRaises(InspectionRejected):
                    self.start()
        self.assertFalse((self.session_root / "active-session").exists())

    def test_stale_instance_and_unknown_choice_rejected(self):
        with self.assertRaises(InspectionRejected):
            self.start(instance_id="a"*32)
        with self.assertRaises(InspectionRejected):
            self.start(selection_id="draft")
        with self.assertRaises(ValueError):
            self.start(selection_id="../profile")
        with self.assertRaises(ValueError):
            self.start(operator="x/y")
        self.assertFalse((self.session_root / "active-session").exists())

    def test_single_owner_under_concurrent_start(self):
        gate = threading.Barrier(2)
        results = []
        def worker():
            gate.wait()
            try:
                results.append(self.start()["state"])
            except InspectionRejected:
                results.append("rejected")
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(5)
        self.assertCountEqual(results, ["SESSION_ACTIVE", "rejected"])
        self.assertEqual(len(list(self.session_root.glob("inspection-*"))), 1)

    def test_restart_blocks_without_auto_replay(self):
        station = self.start()
        self.host.shutdown_inspection()
        other = CoreHost(self.root / "recovered-library", composition=self.composition,
                         session_root=self.session_root)
        other.library.catalog.register(self.record)
        report = other.inspection_report()
        self.assertIn("RECOVERY_REQUIRED", report["blockers"])
        self.assertIsNone(other._runtime)
        self.assertFalse(report["startAllowed"])
        with self.assertRaises(InspectionRejected):
            other.start_inspection(selection_id=self.choice.selection_id, instance_id=report["instanceId"], intent_token=report["intentToken"], operator="operator")
        self.assertEqual((self.session_root/"active-session").read_text().strip(),station["sessionId"])

    def test_running_stage_cannot_be_closed_through_api(self):
        self.start()
        self.host._runtime.engine.start("S03", "localization-request")
        self.assertFalse(self.host.inspection_report()["closeAllowed"])
        with self.assertRaises(InspectionRejected):
            self.close()
        self.assertEqual(self.host.station_report()["state"], "SESSION_ACTIVE")

    def test_verified_receipt_required_not_merely_device_availability(self):
        self.trusted = False
        self.assertTrue(self.host.inspection_report()["startAllowed"])
        self.start()
        self.assertEqual(self.host._runtime.engine.states["S01"], State.FAILED)
        self.assertEqual(self.host._runtime.engine.states["S02"], State.BLOCKED)
        self.assertTrue(self.host.inspection_report()["closeAllowed"])

    def test_readiness_receipt_provider_failure_blocks_s02(self):
        def fail(_request):
            raise OSError("synthetic device failure")
        self.receipt = fail
        self.start()
        self.assertEqual(self.host._runtime.engine.states["S01"], State.FAILED)
        self.assertEqual(self.host._runtime.engine.states["S02"], State.BLOCKED)

    def test_old_start_token_cannot_restart_closed_inspection(self):
        old = self.host.inspection_report()["intentToken"]
        self.start()
        self.close()
        with self.assertRaises(InspectionRejected):
            self.start(intent_token=old)

    def test_actual_private_ipc(self):
        sock = self.root / "ipc" / "core.sock"
        server = CoreServer(sock,self.host)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":.01})
        thread.start()
        try:
            client = RemoteStationOwner(sock)
            report = client.inspection_report()
            station = client.start_inspection(selection_id=self.choice.selection_id,
                       instance_id=report["instanceId"],intent_token=report["intentToken"],operator="fixture-operator")
            self.assertEqual(station["state"],"SESSION_ACTIVE")
            with self.assertRaises(InspectionRejected):
                client.start_inspection(selection_id=self.choice.selection_id,
                       instance_id=report["instanceId"],intent_token=report["intentToken"],operator="fixture-operator")
            self.assertEqual(client.close_inspection(session_id=station["sessionId"],
                instance_id=report["instanceId"],operator="fixture-operator")["state"],"NO_ACTIVE_SESSION")
        finally:
            server.shutdown(); thread.join(3); server.server_close()


class InspectionHttpTests(unittest.TestCase):
    setUp = station_fixture.StationTests.setUp
    request = station_fixture.StationTests.request
    login = station_fixture.StationTests.login

    def test_role_origin_identity_and_default_blockers(self):
        host = CoreHost(self.root / "inspection-library", diagnostics=lambda: observations(status="UNKNOWN"))
        self.app.owner = host
        route = "/api/v1/inspection/start"
        headers = {"HTTP_ORIGIN":"http://127.0.0.1:18490", "HTTP_X_VISION_CLIENT":"webgui"}
        payload = {"selectionId":"draft", "instanceId":host.station_report()["instanceId"], "intentToken":host.inspection_report()["intentToken"]}
        self.assertEqual(self.request("/api/v1/inspection")["status"],401)
        self.assertEqual(self.request(route,method="POST",value=payload,headers=headers)["status"],401)
        _, reader = self.login()
        self.assertFalse(self.request("/api/v1/inspection",cookie=reader)["json"]["startAllowed"])
        self.assertEqual(self.request(route,method="POST",value=payload,headers=headers,cookie=reader)["json"]["code"],"OPERATOR_REQUIRED")
        # Existing reader is never promoted by account name. Explicit local provisioning is needed.
        provision_account(self.accounts,"operator",self.password,replace=True,role="operator")
        self.assertEqual(self.request("/api/v1/auth/session",cookie=reader)["status"],401)
        report, operator = self.login()
        self.assertEqual(report["json"]["role"],"operator")
        self.assertEqual(self.request(route,method="POST",value=payload,cookie=operator)["json"]["code"],"ORIGIN_REJECTED")
        self.assertEqual(self.request(route,method="POST",value={**payload,"operator":"forged"},headers=headers,cookie=operator)["status"],400)
        with patch.object(host,"start_inspection",wraps=host.start_inspection) as start:
            response = self.request(route,method="POST",value=payload,headers=headers,cookie=operator)
            self.assertEqual(response["status"],409)
            self.assertEqual(response["json"]["code"],"INSPECTION_REJECTED")
            start.assert_called_once_with(selection_id="draft",instance_id=payload["instanceId"],intent_token=payload["intentToken"],operator="operator")
        self.assertIsNone(host._runtime)

    def test_operator_role_survives_reset_and_password_change(self):
        provision_account(self.accounts,"operator",self.password,replace=True,role="operator")
        provision_account(self.accounts,"operator",self.password,replace=True)
        self.identity = IdentityStore(self.accounts)
        token, report = self.identity.login("operator",self.password,"fixture")
        self.assertEqual(report["role"],"operator")
        new_password = "synthetic-changed-account-password"
        self.identity.change_password(token,self.password,new_password)
        _, report = self.identity.login("operator",new_password,"fixture")
        self.assertEqual(report["role"],"operator")


if __name__ == "__main__":
    unittest.main()
