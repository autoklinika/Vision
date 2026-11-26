"""Synthetic sysfs inventory fixtures; no USB opens or CAN/ROS operations."""
from pathlib import Path
import tempfile
import time
import unittest

from vision_station.hardware_presence import usb_hardware_connections
from vision_station.host import CoreHost
from vision_station.inspection import DEVICES, DeviceStatus, validate_inspection_report


class HardwarePresenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.device("usb1", "1d6b", "0002")
        self.device("1-2", "1d50", "606f")  # Adapter only, not NERO identity.
        (self.root / "1-2:1.0").mkdir()  # Interface nodes are not devices.

    def device(self, name, vendor, product):
        path = self.root / name
        path.mkdir(exist_ok=True)
        (path / "idVendor").write_text(vendor + "\n", encoding="ascii")
        (path / "idProduct").write_text(product + "\n", encoding="ascii")

    def test_oak_modes_and_sony_modes(self):
        for oak_pid in ("2485", "f63b", "f63c"):
            for sony_pid in ("0f0b", "0f0d"):
                with self.subTest(oak_pid=oak_pid, sony_pid=sony_pid):
                    self.device("1-3", "03e7", oak_pid)
                    self.device("1-4", "054c", sony_pid)
                    self.assertEqual(usb_hardware_connections(self.root), {
                        "luxonis": "USB_DETECTED", "nero": "UNKNOWN",
                        "moveit": "NOT_APPLICABLE", "sony": "USB_DETECTED",
                    })

    def test_complete_negative_inventory_and_unrelated_usb_ids(self):
        self.device("1-3", "054c", "9999")
        self.device("1-4", "03e7", "9999")
        self.assertEqual(usb_hardware_connections(self.root), {
            "luxonis": "USB_NOT_DETECTED", "nero": "UNKNOWN",
            "moveit": "NOT_APPLICABLE", "sony": "USB_NOT_DETECTED",
        })

    def test_partial_inventory_cannot_prove_absence(self):
        self.device("1-3", "03e7", "2485")
        (self.root / "1-4").mkdir()
        report = usb_hardware_connections(self.root)
        self.assertEqual(report["luxonis"], "USB_DETECTED")
        self.assertEqual(report["sony"], "UNKNOWN")

    def test_missing_inventory_and_no_root_hub(self):
        empty = self.root / "empty"
        empty.mkdir()
        for root in (empty, self.root / "missing"):
            with self.subTest(root=root.name):
                self.assertEqual(usb_hardware_connections(root), {
                    "luxonis":"UNKNOWN", "nero":"UNKNOWN",
                    "moveit":"NOT_APPLICABLE", "sony":"UNKNOWN",
                })

    def test_hardware_metadata_never_authorizes_inspection(self):
        states = {"luxonis":"USB_DETECTED", "nero":"UNKNOWN",
                  "moveit":"NOT_APPLICABLE", "sony":"USB_NOT_DETECTED"}
        host = CoreHost(self.root / "isolated-library", diagnostics=lambda: tuple(
            DeviceStatus(d, "ACTIVE", "UNKNOWN", time.time(), states[d]) for d in DEVICES))
        report = host.inspection_report()
        self.assertTrue(validate_inspection_report(report))
        self.assertFalse(report["startAllowed"])
        self.assertEqual({d["device"]:d["hardwareConnection"] for d in report["devices"]}, states)
        for row in report["devices"]:
            row.pop("hardwareConnection")
        self.assertTrue(validate_inspection_report(report))
        report["devices"][1]["hardwareConnection"] = "USB_DETECTED"
        self.assertFalse(validate_inspection_report(report))
        report["devices"][1]["hardwareConnection"] = "UNKNOWN"
        report["devices"][0]["hardwareConnection"] = "READY"
        self.assertFalse(validate_inspection_report(report))
