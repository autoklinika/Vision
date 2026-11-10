#!/usr/bin/env python3
"""Read-only NERO precommissioning check with official pyAgxArm SDK.
No enable, disable, motion, reset, mode change, or calibration calls.
Required privilege: sudo, only to configure the Linux CAN interface.
"""
import json
import math
import os
import subprocess
import sys
import time

from pyAgxArm import ArmModel, AgxArmFactory, NeroFW, create_agx_arm_config, resolve_firmware_profile

IFACE = "can0"
USB_VID = "1d50"
USB_PID = "606f"
USB_SERIAL = os.environ.get("VISION_NERO_CAN_SERIAL", "")
BASE = "/sys/class/net/" + IFACE
STATUS = {
    0: "NORMAL", 1: "EMERGENCY_STOP", 2: "NO_SOLUTION",
    3: "SINGULARITY", 4: "TARGET_POS_EXCEEDS_LIMIT",
    5: "JOINT_COMMUNICATION_ERR", 6: "JOINT_BRAKE_NOT_RELEASED",
    7: "COLLISION", 8: "OVERSPEED", 9: "JOINT_STATUS_ERR",
    10: "OTHER_ERROR", 14: "MAIN_CONTROLLER_OVER_TEMP", 15: "RESISTOR_OVER_TEMP"
}

def system(*args):
    print("$", " ".join(args), flush=True)
    subprocess.run(args, check=True, timeout=10)

def can_device_guard():
    props = subprocess.check_output(
        ["udevadm", "info", "-q", "property", "-p", BASE], text=True, timeout=8
    ).splitlines()
    d = dict(l.split("=", 1) for l in props if "=" in l)
    for key, value in (
        ("ID_VENDOR_ID", USB_VID), ("ID_MODEL_ID", USB_PID),
        ("ID_SERIAL_SHORT", USB_SERIAL)
    ):
        if d.get(key, "").lower() != value.lower():
            raise RuntimeError("WRONG_ADAPTER: " + key + " got " + str(d.get(key)))
    print("AGILEX_USB_CAN_CONFIRMED", IFACE, d["ID_SERIAL_SHORT"], flush=True)

def link_flags():
    j = subprocess.check_output(
        ["ip", "-j", "link", "show", "dev", IFACE], text=True, timeout=8
    )
    return json.loads(j)[0].get("flags", [])

def make_robot(profile):
    cfg = create_agx_arm_config(
        robot=ArmModel.NERO, firmeware_version=profile,
        interface="socketcan", channel=IFACE
    )
    return AgxArmFactory.create_arm(cfg)

def print_state(robot, label):
    msg = robot.get_arm_status()
    if msg is None:
        print(label, "ARM_STATUS=NO_DATA", flush=True)
        return
    s = msg.msg
    code = getattr(s, "arm_status", None)
    print(label, "ARM_STATUS", code, STATUS.get(code, "UNKNOWN"),
          "CONTROL", getattr(s, "ctrl_mode", None),
          "ERROR_MASK", hex(getattr(s, "err_code", 0) or 0), flush=True)

def print_joints(robot):
    angles = robot.get_joint_angles()
    if angles is not None:
        print("JOINT_ANGLES_DEG", [round(math.degrees(x), 3) for x in angles.msg], flush=True)
    else:
        print("JOINT_ANGLES=NO_DATA", flush=True)
    for i in range(1, 8):
        ds, ms = robot.get_driver_states(i), robot.get_motor_states(i)
        if ds is None or ms is None:
            print("J", i, "DRIVER_DATA", bool(ds), "MOTOR_DATA", bool(ms), flush=True)
            continue
        d, m = ds.msg, ms.msg
        print("J", i,
              "voltage_V", getattr(d, "vol", None),
              "drive_temp_C", getattr(d, "foc_temp", None),
              "motor_temp_C", getattr(d, "motor_temp", None),
              "foc_status_code", getattr(d, "foc_status_code", None),
              "motor_current_A", getattr(m, "current", None),
              "motor_velocity_rad_s", getattr(m, "velocity", None),
              flush=True)

def main():
    if os.geteuid() != 0:
        raise SystemExit("RUN_AS_SUDO")
    can_device_guard()
    if "UP" in link_flags():
        raise SystemExit("REFUSE_CAN_ALREADY_UP: leaving existing owner untouched")

    robot = None
    up_attempted = False
    try:
        up_attempted = True
        system("ip", "link", "set", IFACE, "type", "can", "bitrate", "1000000", "restart-ms", "0")
        system("ip", "link", "set", IFACE, "up")

        # Firmware query 0x4AF is an official SDK read-only request.
        robot = make_robot(NeroFW.DEFAULT)
        robot.connect()
        time.sleep(0.4)
        fw = robot.get_firmware(timeout=2.0)
        print("FW_RESPONSE", repr(fw), flush=True)
        robot.disconnect()
        robot = None
        if not fw or not fw.get("software_version"):
            print("FW_NOT_CONFIRMED: skipping profile-dependent telemetry", flush=True)
            return 3

        profile = resolve_firmware_profile(ArmModel.NERO, fw["software_version"])
        print("NERO_FIRMWARE_PROFILE", profile, flush=True)
        robot = make_robot(profile)
        robot.connect()
        time.sleep(1.5)
        print_state(robot, "FIRST")
        print_joints(robot)
        time.sleep(1.0)
        print_state(robot, "FINAL")
        print("SDK_READ_ONLY_TEST_PASS", flush=True)
        return 0
    finally:
        if robot is not None:
            try:
                robot.disconnect()
            except Exception as e:
                print("SDK_DISCONNECT_WARNING", str(e), flush=True)
        if up_attempted:
            print("RESTORE_CAN_DOWN", flush=True)
            try:
                system("ip", "link", "set", IFACE, "down")
                print("CAN_DOWN_CONFIRMED", "UP" not in link_flags(), flush=True)
            except Exception as e:
                print("CAN_DOWN_FAILURE", str(e), flush=True)

if __name__ == "__main__":
    sys.exit(main())
