"""Static and mocked offline checks for the Vision hardware snapshot.

Does not open CAN, USB, serial, GPIO or other real hardware.
"""
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
STOP = ROOT / "ops/nero/nero_stop.py"
PROBE = ROOT / "scripts/robot/nero_sdk_readonly_probe.py"
PROFILE = ROOT / "ops/streamdeck/profile/Default.example.json"


class TestNeroSoftwareStopSnapshot(unittest.TestCase):
    def test_stop_source_syntax_and_no_motion_or_disable(self):
        source = STOP.read_text()
        tree = ast.parse(source)
        forbidden = {"disable", "enable", "move_j", "move_js", "move_p", "reset"}
        invoked = {
            n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        self.assertFalse(invoked & forbidden)
        self.assertIn("electronic_emergency_stop", invoked)
        self.assertIn("STOP_COMMAND_SENT_UNVERIFIED", source)
        self.assertIn("STOP_CONFIRMED_BY_ARM_STATUS", source)

    def test_serial_is_external_configuration(self):
        for p in (STOP, PROBE):
            source = p.read_text()
            self.assertIn("VISION_NERO_CAN_SERIAL", source)
            self.assertNotRegex(source, r'(?i)\b[0-9a-f]{24,}\b')
            ast.parse(source)

    def test_dry_run_avoids_hardware_io(self):
        spec = importlib.util.spec_from_file_location("vision_nero_stop_offline", STOP)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        dummy = types.ModuleType("pyAgxArm")
        dummy.AgxArmFactory = object()
        dummy.ArmModel = object()
        dummy.NeroFW = object()
        with patch.dict(sys.modules, {"pyAgxArm": dummy}), \
             patch.object(sys, "argv", ["nero_stop.py", "--dry-run"]), \
             patch.object(mod, "validate_transport", side_effect=AssertionError("unexpected hardware access")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0, mod.main())
        self.assertIn("no_CAN_TX=True", out.getvalue())


class TestStreamDeckSnapshot(unittest.TestCase):
    def test_exactly_one_bottom_right_stop(self):
        p = json.loads(PROFILE.read_text())
        self.assertEqual(len(p["keys"]), 8)
        self.assertEqual(len(p["sliders"]), 4)
        self.assertEqual(p["keys"][:7], [None] * 7)
        k = p["keys"][7]
        self.assertEqual(k["context"], "Keypad.7.0")
        self.assertTrue(k["settings"]["down"].endswith("nero_stop.py --send"))
        self.assertFalse(k["settings"]["up"])
        self.assertEqual(k["action"]["uuid"], "com.amansprojects.starterpack.runcommand")

    def test_udev_targets_specific_device(self):
        rule = (ROOT / "ops/streamdeck/71-vision-streamdeck-plus.rules").read_text()
        self.assertIn('ATTRS{idVendor}=="0fd9"', rule)
        self.assertIn('ATTRS{idProduct}=="0084"', rule)
        self.assertNotIn('MODE="0666"', rule)

    def test_repository_links_in_readme(self):
        import re
        text = (ROOT / "README.md").read_text()
        for dest in re.findall(r'\]\(([^)]+)\)', text):
            if "://" in dest or dest.startswith("#"): continue
            self.assertTrue((ROOT / dest.split("#")[0]).exists(), dest)


if __name__ == "__main__":
    unittest.main()
