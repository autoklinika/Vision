"""Hardware-free tests for the AF/shutter safety boundary."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/audit/sony_af_prototype.py"
spec = importlib.util.spec_from_file_location("sony_af_prototype", SOURCE)
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Camera:
    def __init__(self, clock, focus_after=3, baseline=1, pending=0, focus_value=2,
                 fail_full_press=False, fail_release=False):
        self.clock, self.focus_after, self.baseline = clock, focus_after, baseline
        self.pending, self.focus_value = pending, focus_value
        self.fail_full_press, self.fail_release = fail_full_press, fail_release
        self.half_start = None
        self.actions = []
        self.reads = []

    def set_action(self, name, value):
        self.actions.append((name, value, self.clock()))
        if name == "autofocus" and value == 1:
            self.half_start = self.clock()
        if name == "capture" and value == 1 and self.fail_full_press:
            raise prototype.GateError("AMBIGUOUS_USB_ACK")
        if name == "capture" and value == 0 and self.half_start is not None and self.fail_release:
            raise prototype.GateError("RELEASE_FAILED")

    def buffer(self):
        return self.pending

    def focus(self):
        self.clock.sleep(.02)
        value = self.baseline if self.half_start is None else (
            self.focus_value if self.clock() - self.half_start >= self.focus_after else 1)
        self.reads.append((self.clock(), value))
        return value


class AFGateTests(unittest.TestCase):
    def run_shot(self, camera, limit=8, before=None):
        return prototype.af_then_shutter(
            camera, before or (lambda: None), limit,
            clock=camera.clock, pause=camera.clock.sleep)

    def full_presses(self, camera):
        return [action for action in camera.actions if action[:2] == ("capture", 1)]

    def test_delayed_focus_is_confirmed_before_exactly_one_shutter(self):
        camera = Camera(Clock(), focus_after=3)
        result = self.run_shot(camera)
        self.assertEqual(result["status"], "SHUTTER_REQUESTED")
        self.assertGreaterEqual(result["af_confirmation_s"], 3)
        self.assertEqual(len(self.full_presses(camera)), 1)
        self.assertGreaterEqual(self.full_presses(camera)[0][2] - camera.half_start, 3)
        self.assertEqual([a[:2] for a in camera.actions[-2:]],
                         [("capture", 0), ("autofocus", 0)])

    def test_one_second_deadline_refuses_slow_af_without_shutter(self):
        camera = Camera(Clock(), focus_after=3)
        result = self.run_shot(camera, limit=1)
        self.assertIn("AF_TIMEOUT_NO_SHUTTER", result["error"])
        self.assertEqual(self.full_presses(camera), [])
        self.assertEqual(result["full_press_requests"], 0)

    def test_never_confirmed_af_releases_half_press_without_shutter(self):
        camera = Camera(Clock(), focus_after=100)
        result = self.run_shot(camera)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(self.full_presses(camera), [])
        self.assertEqual(camera.actions[-1][:2], ("autofocus", 0))

    def test_stale_focused_baseline_cannot_authorize_new_exposure(self):
        camera = Camera(Clock(), baseline=2)
        result = self.run_shot(camera)
        self.assertIn("FOCUS_BASELINE_NOT_RESET", result["error"])
        self.assertEqual(self.full_presses(camera), [])
        self.assertFalse(any(a[:2] == ("autofocus", 1) for a in camera.actions))

    def test_unknown_focus_value_three_is_not_accepted_for_this_model(self):
        camera = Camera(Clock(), focus_after=.1, focus_value=3)
        result = self.run_shot(camera, limit=1)
        self.assertEqual(result["full_press_requests"], 0)
        self.assertEqual(result["status"], "FAIL")

    def test_pending_original_blocks_focus_and_new_shutter(self):
        camera = Camera(Clock(), pending=0x8001)
        result = self.run_shot(camera)
        self.assertIn("PENDING_IMAGE_RECOVERY_REQUIRED", result["error"])
        self.assertEqual(self.full_presses(camera), [])
        self.assertFalse(any(a[:2] == ("autofocus", 1) for a in camera.actions))

    def test_storage_or_uvc_guard_failure_blocks_full_press(self):
        camera = Camera(Clock(), focus_after=.1)
        def denied():
            raise prototype.GateError("NVME_OR_UVC_UNAVAILABLE")
        result = self.run_shot(camera, before=denied)
        self.assertEqual(result["full_press_requests"], 0)
        self.assertEqual(self.full_presses(camera), [])
        self.assertEqual(camera.actions[-1][:2], ("autofocus", 0))

    def test_ambiguous_shutter_ack_is_recorded_once_and_never_retried(self):
        camera = Camera(Clock(), focus_after=.1, fail_full_press=True)
        result = self.run_shot(camera)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["full_press_requests"], 1)
        self.assertEqual(len(self.full_presses(camera)), 1)
        self.assertEqual(camera.actions[-1][:2], ("autofocus", 0))

    def test_release_failure_still_attempts_half_release_and_fails(self):
        camera = Camera(Clock(), focus_after=.1, fail_release=True)
        result = self.run_shot(camera)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["release_errors"])
        self.assertEqual(camera.actions[-1][:2], ("autofocus", 0))


class StorageGateTests(unittest.TestCase):
    def test_no_mount_means_no_session_directory_created(self):
        response = json.dumps({"filesystems": [{
            "target": "/", "source": "/dev/mmcblk0p1", "fstype": "ext4",
            "label": "VISION_DATA", "options": "rw"}]})
        with patch.object(prototype.subprocess, "check_output", return_value=response), \
                patch.object(Path, "mkdir") as mkdir:
            with self.assertRaises(prototype.GateError):
                prototype.create_session(Path("/srv/vision-data/vision/sessions/never-created"))
            mkdir.assert_not_called()

    def test_readonly_nvme_is_rejected_before_write(self):
        response = json.dumps({"filesystems": [{
            "target": "/srv/vision-data", "source": "/dev/nvme0n1p1", "fstype": "ext4",
            "label": "VISION_DATA", "options": "ro"}]})
        with patch.object(prototype.subprocess, "check_output", return_value=response), \
                patch.object(Path, "mkdir") as mkdir:
            with self.assertRaises(prototype.GateError):
                prototype.create_session(Path("/srv/vision-data/vision/sessions/never-created"))
            mkdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
