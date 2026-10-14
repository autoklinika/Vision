"""Hardware-free long-run, cleanup, storage and SD-integrity regressions."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/audit"))
import sony_stability_test as st


class RunnerTests(unittest.TestCase):
    def run_fake(self, mode="both", shots=50, fault=None):
        events = {"shutters": 0, "presses": 0, "ble_instances": 0}
        class Camera:
            usable = True
            env = {}
            def __init__(self, *args, debug): events["debug"] = debug
            def command(self, command, **kw): return "Model: ILCE-6100A"
            def current(self, key, **kw): return st.EXPECTED_CONFIG[key]
            def buffer(self): return 0
            def set_action(self, action, value):
                events.setdefault("releases", []).append((action, value))
                if fault == "release" and action == "capture": raise RuntimeError()
            def close(self): events["camera_closed"] = True
        class UVC:
            ready = SimpleNamespace(wait=lambda seconds: True)
            errors = []
            pattern_checks = 0
            rows = [{"index": 0, "receive_s": 0, "sha256": "fake"}]
            def __init__(self, *args, frame_count): events["frame_count"] = frame_count
            def gate(self):
                if fault == "uvc" and events["shutters"] >= 1: raise st.af.GateError("UVC_LOST")
            def close(self): events["uvc_closed"] = True
            def report(self): return {"frames_received": len(self.rows), "collector_errors": []}
        class BLE:
            def __init__(self): events["ble_instances"] += 1
            def gate(self):
                if fault == "ble" and events["presses"] >= 1: raise st.af.GateError("BLE_LOST")
            def pause(self, seconds): pass
            def write(self, data):
                if data[1] in (0x45, 0x47):
                    events["presses"] += 1
                    if fault == "zoom": raise TimeoutError()
                else: events["zoom_releases"] = events.get("zoom_releases", 0) + 1
            def close(self): events["ble_closed"] = True
        def shutter(camera, before, limit):
            if fault == "af" and events["shutters"] == 1:
                return {"status": "FAIL", "full_press_requests": 0}
            before()
            events["shutters"] += 1
            if fault == "interrupt": raise InterruptedError()
            return {"status": "SHUTTER_REQUESTED", "full_press_requests": 1, "af_confirmation_s": 2.0}
        def pair(folder):
            if fault == "pair" and events["shutters"] == 2:
                raise st.af.GateError("PAIR_INCOMPLETE")
            number = int(folder.name.rsplit("-", 1)[1])
            value = 39 if folder.name.startswith("zoom") and number % 2 == 0 else 50
            if fault == "fixed_exif" and number == 2: value = 39
            if fault == "no_motion": value = 50
            files = []
            for ext in ("jpg", "arw"):
                p = folder / ("original." + ext)
                p.write_bytes(b"fake")
                row = {"file": p.name, "size_bytes": 4, "sha256": st.sd.sha_file(p)}
                if ext == "jpg": row["exif"] = {"focal_length_mm": str(value), "datetime_original": "2026:10:14 00:%02d:00" % number}
                files.append(row)
            return files
        args = SimpleNamespace(mode=mode, shots=shots, pulse=.65, settle=1, interval=10,
                               af_timeout=8, uvc_gap_limit=1, gphoto="fake", library_dir="fake")
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            base = Path(directory)
            for path in ("tools/sony-af-prototype", "tools/streamdeck-eval", "vision/sessions"):
                (base / path).mkdir(parents=True)
            for name, value in (("BASE", base), ("nvme_guard", lambda: None), ("Shell", Camera),
                                ("UVC", UVC), ("detect_port", lambda: "fake"), ("af_then_shutter", shutter),
                                ("validate_pair", pair), ("photo_paths", lambda f: ["jpg", "arw"]),
                                ("wait_buffer_idle", lambda c: [0]),
                                ("create_session", lambda p: (p.mkdir(), p)[1])):
                stack.enter_context(patch.object(st.af, name, value))
            stack.enter_context(patch.object(st, "space_guard", lambda n: None))
            stack.enter_context(patch.object(st.zoom, "BLE", BLE))
            stack.enter_context(patch.object(st.Monitor, "pause", lambda self, seconds: self.gate()))
            with redirect_stdout(io.StringIO()): code = st.run(args)
            session = next((base / "vision/sessions").iterdir())
            result = json.loads((session / "result.json").read_text())
            manifest = json.loads((session / "ptp-manifest-private.json").read_text())
            return code, result, manifest, events

    def test_both_50_captures_exactly_100_in_one_session(self):
        code, r, m, e = self.run_fake()
        self.assertEqual(code, 0)
        self.assertEqual((r["verified_shots"], r["full_press_requests"], len(m["shots"])), (100, 100, 100))
        self.assertEqual(r["status"], "PENDING_SD")
        self.assertEqual([a["phase"] for a in r["attempts"]], ["fixed"] * 50 + ["zoom"] * 50)
        self.assertEqual((e["presses"], e["zoom_releases"]), (49, 49))
        self.assertFalse(e["debug"])
        self.assertEqual(e["frame_count"], 0)
        self.assertTrue(e["camera_closed"] and e["uvc_closed"] and e["ble_closed"])

    def test_both_100_captures_exactly_200(self):
        code, r, m, e = self.run_fake(shots=100)
        self.assertEqual((code, r["verified_shots"], len(m["shots"]), e["presses"]), (0, 200, 200, 99))

    def test_fixed_does_not_create_ble_or_send_zoom(self):
        code, r, m, e = self.run_fake(mode="fixed")
        self.assertEqual((code, e["ble_instances"], e["presses"], r["verified_shots"]), (0, 0, 0, 50))

    def test_af_failure_does_not_retry_or_start_remaining_photos(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="af")
        self.assertEqual((code, e["shutters"], r["full_press_requests"], r["verified_shots"]), (1, 1, 1, 1))
        self.assertTrue(e["camera_closed"] and e["uvc_closed"])

    def test_zoom_timeout_attempts_release_and_blocks_next_shutter(self):
        code, r, m, e = self.run_fake(mode="zoom", fault="zoom")
        self.assertEqual((code, e["shutters"], e["presses"], e["zoom_releases"]), (1, 1, 1, 1))
        self.assertEqual(r["zoom_pulses"][0]["status"], "FAIL")

    def test_no_exif_change_fails_and_preserves_downloaded_pair(self):
        code, r, m, e = self.run_fake(mode="zoom", fault="no_motion")
        self.assertEqual((code, e["shutters"], r["verified_shots"], len(m["shots"])), (1, 2, 1, 2))

    def test_fixed_exif_drift_fails_and_stops(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="fixed_exif")
        self.assertEqual((code, e["shutters"]), (1, 2))
        self.assertEqual(r["error"], "FIXED_ZOOM_EXIF_CHANGED")

    def test_ble_loss_after_zoom_blocks_second_shutter(self):
        code, r, m, e = self.run_fake(mode="zoom", fault="ble")
        self.assertEqual((code, e["shutters"]), (1, 1))
        self.assertTrue(e["ble_closed"])

    def test_uvc_loss_stops_and_releases(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="uvc")
        self.assertEqual((code, e["shutters"]), (1, 1))
        self.assertIn(("capture", 0), e["releases"])

    def test_incomplete_pair_never_retries_shutter(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="pair")
        self.assertEqual((code, e["shutters"], r["verified_shots"]), (1, 2, 1))

    def test_final_release_failure_denies_capture_pass(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="release")
        self.assertEqual((code, r["verified_shots"]), (1, 50))
        self.assertFalse(r["ptp_release_ack"])
        self.assertIn(("autofocus", 0), e["releases"])

    def test_interrupt_after_marker_retains_one_ambiguous_attempt(self):
        code, r, m, e = self.run_fake(mode="fixed", fault="interrupt")
        self.assertEqual((code, r["full_press_requests"], e["shutters"]), (1, 1, 1))
        self.assertEqual(r["status"], "FAIL")


class MonitorTests(unittest.TestCase):
    def fake(self):
        return SimpleNamespace(rows=[{"receive_s": 2.0}], pattern_checks=0, gate=lambda: None)

    def test_gap_during_blocking_download_is_not_hidden_by_later_frames(self):
        u = self.fake(); m = st.Monitor(u, None)
        u.rows += [{"receive_s": 4.0}, {"receive_s": 4.03}]
        with self.assertRaisesRegex(st.af.GateError, "GAP"): m.gate()

    def test_pattern_after_ready_stops_even_if_latest_frame_is_good(self):
        u = self.fake(); m = st.Monitor(u, None)
        u.pattern_checks = 1
        with self.assertRaisesRegex(st.af.GateError, "PATTERN"): m.gate()

    def test_warmup_pattern_does_not_fail_post_ready_monitor(self):
        u = self.fake(); u.pattern_checks = 1
        st.Monitor(u, None).gate()


class AssessmentTests(unittest.TestCase):
    def source(self):
        return {"mode": "fixed", "shots_per_mode": 50, "planned_shots": 50,
                "session": "fixture", "capture_status": "PASS", "ptp_release_ack": True,
                "uvc_final_gate": "PASS", "automatic_shutter_retries": 0, "zoom_pulses": [],
                "attempts": [{"phase": "fixed", "number": n, "full_press_requests": 1,
                              "status": "PASS", "af_confirmation_s": n / 10, "complete_pair_s": 5}
                             for n in range(1, 51)]}
    def compared(self):
        return {"status": "PASS", "verified_pairs": 50, "raw_exact_files": 50,
                "jpeg_exact_files": 0, "jpeg_zero_padding_only": 50,
                "shots": [{"session": "fixture/fixed", "shot": n, "status": "PASS"} for n in range(1, 51)]}
    def test_capture_alone_is_pending_not_pass(self):
        self.assertEqual(st.assessment(self.source())["status"], "PENDING_SD")
    def test_complete_integrity_and_import_can_pass(self):
        r = st.assessment(self.source(), self.compared(), {"verified_files": 100, "reverification": "PASS"})
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["phases"]["fixed"]["af"]["p95_s"], 4.8)
    def test_partial_run_never_becomes_pass_after_successful_partial_sd(self):
        c = self.source(); c["attempts"] = c["attempts"][:3]; c["capture_status"] = "FAIL"
        self.assertEqual(st.assessment(c, self.compared(), {"verified_files": 100, "reverification": "PASS"})["status"], "FAIL")
    def test_comparison_for_another_session_is_rejected(self):
        d = self.compared(); d["shots"][0]["session"] = "other/fixed"
        self.assertEqual(st.assessment(self.source(), d, {"verified_files": 100, "reverification": "PASS"})["status"], "FAIL")
    def test_duplicate_comparison_rows_are_rejected(self):
        d = self.compared(); d["shots"][1] = d["shots"][0]
        self.assertEqual(st.assessment(self.source(), d, {"verified_files": 100, "reverification": "PASS"})["status"], "FAIL")
    def test_import_corruption_denies_pass(self):
        self.assertEqual(st.assessment(self.source(), self.compared(), {"verified_files": 100, "reverification": "FAIL"})["status"], "FAIL")
    def test_identical_scene_is_review_warning_not_a_proven_freeze(self):
        c = self.source(); c["uvc"] = {"longest_identical_run_after_3s": {"span_s": 3}}
        r = st.assessment(c)
        self.assertEqual(r["status"], "PENDING_SD")
        self.assertEqual(len(r["warnings"]), 1)
        self.assertEqual(r["scene_freshness"], "NOT_PROVEN")


class EntryAndStorageTests(unittest.TestCase):
    def test_help_does_not_open_hardware(self):
        with patch.object(st, "run") as run, redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e: st.main(["--help"])
        self.assertEqual(e.exception.code, 0); run.assert_not_called()
    def test_invalid_arguments_fail_before_hardware(self):
        for argv in (["run", "--shots", "10"], ["run", "--interval", "nan"], ["run", "--pulse", "inf"]):
            with patch.object(st, "run") as run, patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit): st.main(argv)
                run.assert_not_called()
    def test_unavailable_nvme_blocks_before_camera_lock_or_session_creation(self):
        args = SimpleNamespace(mode="both", shots=100)
        with patch.object(st.af, "nvme_guard", side_effect=st.af.GateError("NVME_UNAVAILABLE")), patch.object(st.af, "Shell") as camera:
            with self.assertRaises(st.af.GateError): st.run(args)
            camera.assert_not_called()
    def test_space_reserve_covers_all_remaining_pairs(self):
        with patch.object(st.af, "nvme_guard"), patch.object(st.os, "statvfs", return_value=SimpleNamespace(f_bavail=3*1024**3, f_frsize=1)):
            with self.assertRaisesRegex(st.af.GateError, "RESERVE"): st.space_guard(200)
            st.space_guard(1)
    def test_changed_sd_import_is_detected_by_offline_assessment(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Path(directory); (s / "sd-originals").mkdir()
            (s / "sd-originals/a.ARW").write_bytes(b"changed")
            c = AssessmentTests().source()
            (s / "result.json").write_text(json.dumps(c))
            (s / "sd-comparison.json").write_text(json.dumps(AssessmentTests().compared()))
            (s / "sd-import.json").write_text(json.dumps({"verified_files": 100, "files": [{"file": "a.ARW", "sha256": "wrong", "bytes": 7}]}))
            with patch.object(st, "session_guard", return_value=s), patch.object(st.af, "nvme_guard"), redirect_stdout(io.StringIO()):
                self.assertEqual(st.assess(s), 1)
            r = json.loads((s / "assessment.json").read_text())
            self.assertEqual(r["import"]["reverification"], "FAIL")


class SharedCollectorTests(unittest.TestCase):
    def test_interrupted_shell_command_requires_owner_recovery(self):
        c = st.af.Shell.__new__(st.af.Shell)
        c.usable = True; c.process = SimpleNamespace(stdin=io.BytesIO())
        c._prompt = MagicMock(side_effect=InterruptedError())
        with self.assertRaises(InterruptedError): c.command("wait-event-and-download 1s")
        self.assertFalse(c.usable)
        with self.assertRaisesRegex(st.af.GateError, "UNUSABLE"): c.command("set-config /main/actions/capture=1")

    def test_long_collector_explicitly_requests_unbounded_stream(self):
        with tempfile.TemporaryDirectory() as d, patch.object(st.af.subprocess, "Popen") as popen, patch.object(st.af.threading, "Thread") as thread:
            u = st.af.UVC(Path(d), {}, frame_count=0)
            self.assertIn("--stream-count=0", popen.call_args.args[0])
            u.log.close()
    def test_long_shell_disables_raw_debug_dump_without_changing_original_default(self):
        with tempfile.TemporaryDirectory() as d, patch.object(st.af.subprocess, "Popen") as popen, patch.object(st.af.Shell, "_prompt"):
            c = st.af.Shell(Path(d), "fake", "fake", "fake", debug=False)
            self.assertNotIn("--debug", popen.call_args.args[0]); c.log.close()
            c = st.af.Shell(Path(d), "fake", "fake", "fake")
            self.assertIn("--debug", popen.call_args.args[0]); c.log.close()


class ComparatorTests(unittest.TestCase):
    def compare_fixture(self, count, fault=None, legacy=False):
        # Real file matching/checksums/JPEG marker parsing and raw equality;
        # metadata and RGB decoder are stubbed to keep 200-pair tests small.
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            base = Path(directory); root = base / "sd"; dcim = root / "DCIM"
            dcim.mkdir(parents=True); ptp = base / "ptp"; ptp.mkdir()
            shots = []
            image = b"\xff\xd8\xff\xda\x00\x02pixels\xff\xd9"
            def metadata(path):
                num = int(path.stem.replace("DSC", ""))
                if fault == "ambiguous" and num == count + 1: num = 1
                return str(num), 50.0
            for n in range(1, count + 1):
                folder = ptp / str(n); folder.mkdir(); files = []
                for ext, data in (("arw", b"II*\x00" + str(n).encode()), ("jpg", image)):
                    path = folder / ("original." + ext); path.write_bytes(data)
                    files.append({"path": str(path), "size_bytes": len(data), "sha256": st.sd.sha_file(path), "exif_datetime": str(n) if ext == "jpg" else None})
                    if not (fault == "missing" and n == count):
                        tail = b"\x01" if fault == "nonzero" and n == count else bytes(8)
                        (dcim / ("DSC%05d.%s" % (n, ext))).write_bytes(data + tail if ext == "jpg" else data)
                shots.append({"session": "fixture/fixed", "shot": n, "focal_mm": 50., "files": files})
            if fault == "changed_ptp": (ptp / "1/original.arw").write_bytes(b"changed")
            if fault == "ambiguous": (dcim / ("DSC%05d.jpg" % (count + 1))).write_bytes(image)
            manifest = base / "manifest.json"; manifest.write_text(json.dumps({"status": "PASS", "shots": shots}))
            for obj, name, val in ((st.af, "BASE", base), (st.af, "nvme_guard", lambda: None),
                                  (st.sd, "sd_guard", lambda p: {"readonly": True}),
                                  (st.sd, "metadata", metadata), (st.sd, "decode_rgb", lambda data: {"dimensions": [6000, 4000], "decoded_rgb_sha256": "same"})):
                stack.enter_context(patch.object(obj, name, val))
            with redirect_stdout(io.StringIO()):
                code = st.sd.compare(manifest, root, base / "out.json", **({} if legacy else {"expected_pairs": count}))
            return code, json.loads((base / "out.json").read_text())

    def test_variable_counts_50_100_and_200_preserve_padding_classification(self):
        for n in (50, 100, 200):
            with self.subTest(n=n):
                code, r = self.compare_fixture(n)
                self.assertEqual((code, r["verified_pairs"], r["raw_exact_files"], r["jpeg_zero_padding_only"]), (0, n, n, n))
    def test_legacy_default_still_requires_13(self):
        code, r = self.compare_fixture(13, legacy=True)
        self.assertEqual((code, r["verified_pairs"]), (0, 13))
    def test_missing_sd_pair_is_fail(self):
        code, r = self.compare_fixture(50, "missing")
        self.assertEqual((code, r["verified_pairs"]), (1, 49))
    def test_ambiguous_same_exposure_is_fail(self):
        code, r = self.compare_fixture(50, "ambiguous")
        self.assertEqual((code, r["verified_pairs"]), (1, 49))
    def test_nonzero_extra_jpeg_byte_fails(self):
        code, r = self.compare_fixture(50, "nonzero")
        self.assertEqual((code, r["verified_pairs"]), (1, 49))
    def test_mutated_ptp_original_cannot_be_compared(self):
        with self.assertRaisesRegex(st.af.GateError, "PTP_ORIGINAL_CHANGED"):
            self.compare_fixture(50, "changed_ptp")


class ImportBoundaryTests(unittest.TestCase):
    def test_decoder_or_comparator_failure_gets_explicit_fail_result(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            s = Path(directory)
            (s / "ptp-manifest-private.json").write_text(json.dumps({"shots": [{}]}))
            def assess(path):
                self.assertEqual(json.loads((path / "sd-comparison.json").read_text())["status"], "FAIL")
                return 1
            for obj, name, val in ((st, "session_guard", lambda p: s), (st.sd, "sd_guard", lambda p: None),
                                  (st, "space_guard", lambda n: None), (st.af, "nvme_guard", lambda: None), (st, "assess", assess)):
                stack.enter_context(patch.object(obj, name, val))
            stack.enter_context(patch.object(st.sd, "compare", side_effect=OSError("bad image")))
            with redirect_stdout(io.StringIO()): self.assertEqual(st.compare(s, s), 1)
            self.assertFalse((s / "sd-originals").exists())
    def test_readwrite_sd_rejected_before_comparison_or_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Path(directory); (s / "ptp-manifest-private.json").write_text(json.dumps({"shots": [{}]}))
            mount = json.dumps({"filesystems": [{"target": str(s), "fstype": "exfat", "source": "/dev/sda1", "options": "rw"}]})
            with patch.object(st, "session_guard", return_value=s), patch.object(st.sd.subprocess, "check_output", return_value=mount), patch.object(st.sd, "compare") as comparator:
                with self.assertRaises(st.af.GateError): st.compare(s, s)
                comparator.assert_not_called(); self.assertFalse((s / "sd-originals").exists())
    def test_exact_sd_import_preserves_all_jpeg_bytes(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            s = Path(directory); root = s / "card"; (root / "DCIM").mkdir(parents=True)
            (s / "ptp-manifest-private.json").write_text(json.dumps({"shots": [{}]}))
            rows = {"session": "fixture/fixed", "shot": 1, "sd_stem": "DSC00001", "status": "PASS"}
            for ext, data in (("ARW", b"raw"), ("JPG", b"complete-primary-and-secondary-JPEG" + bytes(256))):
                path = root / "DCIM" / ("DSC00001." + ext); path.write_bytes(data)
                rows["raw" if ext == "ARW" else "jpeg"] = {"sd_sha256": st.sd.sha_file(path)}
            def comparator(manifest, root, output, expected_pairs):
                output.write_text(json.dumps({"status": "PASS", "shots": [rows]}))
            for obj, name, val in ((st, "session_guard", lambda p: s), (st.sd, "sd_guard", lambda p: None),
                                  (st, "space_guard", lambda n: None), (st.af, "nvme_guard", lambda: None),
                                  (st.sd, "compare", comparator), (st, "assess", lambda p: 0)):
                stack.enter_context(patch.object(obj, name, val))
            self.assertEqual(st.compare(s, root), 0)
            for p in (root / "DCIM").iterdir(): self.assertEqual((s / "sd-originals" / p.name).read_bytes(), p.read_bytes())
            self.assertEqual(json.loads((s / "sd-import.json").read_text())["verified_files"], 2)


if __name__ == "__main__":
    unittest.main()
