"""Hardware-free regression tests for zoom ambiguity and EXIF measurement."""
import importlib.util
import json
import tempfile
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/audit"))
import sony_zoom_af_test as zoom


class PulseTests(unittest.TestCase):
    def test_normal_pulse_pairs_press_release(self):
        sent, sleeps = [], []
        row = zoom.pulse(sent.append, "WIDE", .65, sleeps.append)
        self.assertEqual(sent, list(zoom.COMMANDS["WIDE"]))
        self.assertEqual(sleeps, [.65])
        self.assertEqual(row["status"], "PASS")

    def test_ambiguous_press_is_not_retried_and_release_is_attempted(self):
        sent = []
        def write(data):
            sent.append(data)
            if len(sent) == 1:
                raise TimeoutError("private-device-address")
        row = zoom.pulse(write, "TELE", .65, lambda s: self.fail("must not wait"))
        self.assertEqual(sent, list(zoom.COMMANDS["TELE"]))
        self.assertEqual(row["status"], "FAIL")
        self.assertTrue(row["release_ack"])
        self.assertNotIn("private-device-address", str(row))

    def test_sleep_interrupt_releases_without_second_press(self):
        sent = []
        def pause(seconds):
            raise InterruptedError()
        row = zoom.pulse(sent.append, "WIDE", .65, pause)
        self.assertEqual(sent, list(zoom.COMMANDS["WIDE"]))
        self.assertEqual(row["status"], "FAIL")

    def test_failed_release_retries_only_release_and_still_fails(self):
        sent = []
        def write(data):
            sent.append(data)
            if len(sent) == 2:
                raise TimeoutError()
        row = zoom.pulse(write, "TELE", .65, lambda s: None)
        press, release = zoom.COMMANDS["TELE"]
        self.assertEqual(sent, [press, release, release])
        self.assertEqual(row["status"], "FAIL")
        self.assertTrue(row["safety_release_retry_ack"])

    def test_invalid_pulse_never_writes(self):
        for value in (0, -1, 1.01, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(zoom.af.GateError):
                zoom.pulse(lambda data: self.fail("unexpected write"), "WIDE", value)


class FocalTests(unittest.TestCase):
    def files(self, value):
        return [{"file": "original.jpg", "exif": {"focal_length_mm": value}}]

    def test_focal_is_read_from_jpeg_exif(self):
        self.assertEqual(zoom.focal_length(self.files("20.0")), 20)

    def test_invalid_exif_cannot_verify_zoom(self):
        for value in ("None", "", "nan", "inf", "0", "51"):
            with self.subTest(value=value), self.assertRaises(zoom.af.GateError):
                zoom.focal_length(self.files(value))

    def test_no_change_or_wrong_direction_fails(self):
        for direction, before, after in (("WIDE", 20, 20), ("TELE", 20, 20),
                                         ("WIDE", 20, 21), ("TELE", 20, 19)):
            with self.subTest(direction=direction), self.assertRaises(zoom.af.GateError):
                zoom.verify_motion(before, after, direction)

    def test_both_directions_can_be_verified(self):
        self.assertEqual(zoom.verify_motion(20, 16, "WIDE"), -4)
        self.assertEqual(zoom.verify_motion(16, 20, "TELE"), 4)

    def test_plan_starts_away_from_near_endpoint(self):
        self.assertEqual([zoom.direction_for(n, 16) for n in (2, 3, 4)], ["TELE", "WIDE", "TELE"])
        self.assertEqual([zoom.direction_for(n, 50) for n in (2, 3, 4)], ["WIDE", "TELE", "WIDE"])


class RunnerBoundaryTests(unittest.TestCase):
    def run_fake(self, fault):
        """Exercise real runner gates/checkpoints with fake hardware only."""
        class Camera:
            usable = True
            env = {}
            def __init__(self, *args): pass
            def command(self, command, **kwargs): return "Model: ILCE-6100A"
            def current(self, key, **kwargs):
                return {"focusmode": "AF-A", "capturemode": "Single Shot",
                        "capturetarget": "card+sdram", "imagequality": "RAW+JPEG (X.Fine)"}[key]
            def buffer(self): return 0
            def set_action(self, *args): pass
            def close(self): pass
        class UVC:
            errors = []
            rows = []
            ready = SimpleNamespace(wait=lambda s: True)
            def __init__(self, *args): pass
            def gate(self): pass
            def close(self): pass
            def report(self): return {}
        class BLE:
            inventory = []
            notifications = []
            after_pulse_gates = 0
            moving = False
            def gate(self):
                if self.moving:
                    self.after_pulse_gates += 1
                    if fault == "disconnect_at_shutter" and self.after_pulse_gates == 2:
                        raise zoom.af.GateError("BLE_DISCONNECTED")
            def pause(self, seconds): pass
            def write(self, data):
                if data[1] in (0x45, 0x47) and fault == "press_timeout":
                    raise TimeoutError()
                if data[1] in (0x44, 0x46): self.moving = True
            def close(self): pass
        def shutter(camera, before, limit):
            try:
                before()
                return {"status": "SHUTTER_REQUESTED", "full_press_requests": 1}
            except zoom.af.GateError as error:
                return {"status": "FAIL", "error": str(error), "full_press_requests": 0}
        def pair(folder):
            # No change after WIDE: hardware ACK must not pass the series.
            value = "46.0" if fault == "normal" and folder.name == "shot-02" else "50.0"
            return [{"file": "original.jpg", "exif": {"focal_length_mm": value}},
                    {"file": "original.arw"}]
        args = SimpleNamespace(inspect=False, shots=3, pulse=.65, settle=1,
                               interval=10, af_timeout=8, gphoto="fake", library_dir="fake")
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            base = Path(directory)
            for path in ("tools/sony-af-prototype", "tools/streamdeck-eval", "vision/sessions"):
                (base / path).mkdir(parents=True)
            for target, value in (("BASE", base), ("nvme_guard", lambda: None),
                                  ("Shell", Camera), ("UVC", UVC), ("detect_port", lambda: "fake"),
                                  ("af_then_shutter", shutter), ("validate_pair", pair),
                                  ("photo_paths", lambda folder: ["jpg", "arw"]),
                                  ("wait_buffer_idle", lambda camera: [0])):
                stack.enter_context(patch.object(zoom.af, target, value))
            stack.enter_context(patch.object(zoom, "BLE", BLE))
            # create_session's default guard was bound when the AF module loaded.
            stack.enter_context(patch.object(zoom.af, "create_session",
                lambda path: (path.mkdir(), path)[1]))
            code = zoom.run(args)
            result_path = next((base / "vision/sessions").glob("*/result.json"))
            return code, json.loads(result_path.read_text())

    def test_failed_zoom_stops_after_baseline_without_another_shutter(self):
        code, report = self.run_fake("press_timeout")
        self.assertEqual(code, 1)
        self.assertEqual(report["full_press_requests"], 1)
        self.assertEqual(len(report["attempts"]), 1)
        self.assertTrue(report["zoom_pulses"][0]["release_ack"])

    def test_unchanged_exif_stops_without_third_shutter(self):
        code, report = self.run_fake("unchanged_exif")
        self.assertEqual(code, 1)
        self.assertEqual(report["full_press_requests"], 2)
        self.assertEqual(report["verified_shots"], 1)
        self.assertIn("NO_EXIF_CHANGE", report["error"])

    def test_ble_lost_after_af_blocks_full_press(self):
        code, report = self.run_fake("disconnect_at_shutter")
        self.assertEqual(code, 1)
        self.assertEqual(report["full_press_requests"], 1)
        self.assertEqual(report["attempts"][1]["full_press_requests"], 0)

    def test_complete_three_shot_run_verifies_both_zoom_directions(self):
        code, report = self.run_fake("normal")
        self.assertEqual(code, 0)
        self.assertEqual(report["verified_shots"], 3)
        self.assertEqual(report["full_press_requests"], 3)
        self.assertEqual([a["focal_mm"] for a in report["attempts"]], [50, 46, 50])
        self.assertEqual([p["direction"] for p in report["zoom_pulses"]], ["WIDE", "TELE"])


if __name__ == "__main__":
    unittest.main()
