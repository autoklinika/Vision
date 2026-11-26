"""Read-only service liveness tests: no real service or hardware commands."""
import subprocess
import unittest
from unittest.mock import patch

from vision_station.inspection import DEVICES, UNITS, systemd_diagnostics

SCENE, SCENE_800 = UNITS["luxonis"]
GUARD, = UNITS["nero"]


def block(name, load="loaded", state="inactive"):
    return f"Id={name}\nLoadState={load}\nActiveState={state}\n"


class ServiceDiagnosticsTests(unittest.TestCase):
    def snapshot(self, stdout="", *, error=None, returncode=0):
        with patch("vision_station.inspection.usb_hardware_connections", return_value=dict.fromkeys(DEVICES,"UNKNOWN")), \
                patch("vision_station.inspection.subprocess.run") as run:
            if error is not None:
                run.side_effect = error
            else:
                run.return_value = subprocess.CompletedProcess([], returncode, stdout, "")
            report = systemd_diagnostics()
            command = run.call_args.args[0]
            self.assertEqual(command[:4], ["systemctl", "--user", "show", "--property=Id,LoadState,ActiveState"])
            self.assertCountEqual(command[4:], [SCENE, SCENE_800, GUARD])
            self.assertFalse(run.call_args.kwargs.get("shell", False))
            self.assertEqual(run.call_args.kwargs["timeout"], 0.65)
        self.assertEqual(tuple(item.device for item in report), DEVICES)
        self.assertTrue(all(item.readiness == "UNKNOWN" for item in report))
        return {item.device: item.availability for item in report}

    def test_current_guard_active_and_scene_services_stopped(self):
        self.assertEqual(self.snapshot("\n".join([block(GUARD,state="active"),block(SCENE),block(SCENE_800,state="failed")])),
            {"luxonis":"INACTIVE","nero":"ACTIVE","moveit":"INACTIVE","sony":"UNKNOWN"})

    def test_active_alternative_never_establishes_readiness(self):
        self.assertEqual(self.snapshot("\n".join([block(SCENE_800,state="active"),block(GUARD,state="inactive")])),
            {"luxonis":"ACTIVE","nero":"INACTIVE","moveit":"ACTIVE","sony":"UNKNOWN"})

    def test_not_found_and_transitional_states_are_unknown(self):
        self.assertEqual(self.snapshot("\n".join([block(GUARD,load="not-found"),block(SCENE),block(SCENE_800,state="activating")]),returncode=1),
            dict.fromkeys(DEVICES,"UNKNOWN"))

    def test_missing_duplicate_and_unrelated_units_do_not_establish_liveness(self):
        self.assertEqual(self.snapshot("\n".join([block(GUARD,state="active"),block(GUARD),block("unrelated.service",state="active")])),
            dict.fromkeys(DEVICES,"UNKNOWN"))

    def test_timeout_and_unavailable_manager_fail_closed(self):
        for error in (OSError(),subprocess.TimeoutExpired("systemctl",0.65)):
            with self.subTest(error=type(error)):
                self.assertEqual(self.snapshot(error=error),dict.fromkeys(DEVICES,"UNKNOWN"))
