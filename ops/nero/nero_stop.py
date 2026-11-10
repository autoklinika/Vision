#!/usr/bin/env python3
"""NERO software STOP requested from Stream Deck Plus.
Not a safety-rated emergency stop. No motor enable or motion operations.
"""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("/srv/vision-data/tools/streamdeck-prod")
LATCH = ROOT / "state/nero-software-stop-latched.json"
LOG = ROOT / "logs/nero-software-stop.jsonl"
LOCK = ROOT / "state/stop.lock"
CAN_IFACE = "can0"
ADAPTER = {
    "ID_VENDOR_ID": "1d50",
    "ID_MODEL_ID": "606f",
    "ID_SERIAL_SHORT": os.environ.get("VISION_NERO_CAN_SERIAL", ""),
}

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def record(event, **fields):
    line = {"utc": utc(), "event": event, **fields}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(line, ensure_ascii=False), flush=True)

def update_latch(status, **fields):
    v = {"utc": utc(), "status": status, **fields}
    temp = LATCH.with_suffix(".tmp")
    temp.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    temp.replace(LATCH)

def validate_transport():
    p = Path("/sys/class/net") / CAN_IFACE
    if not p.exists():
        raise RuntimeError("CAN interface missing")
    q = subprocess.check_output(
        ["udevadm", "info", "-q", "property", "-p", str(p)], text=True, timeout=3
    )
    got = dict(row.split("=", 1) for row in q.splitlines() if "=" in row)
    for key, expected in ADAPTER.items():
        if got.get(key, "").lower() != expected.lower():
            raise RuntimeError(f"Wrong USB-CAN adapter {key}: {got.get(key)}")
    j = json.loads(subprocess.check_output(
        ["ip", "-j", "link", "show", "dev", CAN_IFACE], text=True, timeout=3
    ))
    if "UP" not in j[0]["flags"]:
        raise RuntimeError("CAN interface is DOWN")
    return got["ID_SERIAL_SHORT"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.send:
        parser.error("Choose exactly one: --dry-run or --send")

    if args.dry_run:
        from pyAgxArm import AgxArmFactory, ArmModel, NeroFW
        print("DRY_RUN_OK sdk_import=True method=electronic_emergency_stop no_CAN_TX=True")
        return 0

    with LOCK.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Fail-closed request flag is written before any device I/O.
        update_latch("STOP_REQUESTED")
        record("STOP_REQUESTED")
        robot = None
        try:
            serial = validate_transport()
            from pyAgxArm import AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config
            robot = AgxArmFactory.create_arm(create_agx_arm_config(
                robot=ArmModel.NERO,
                firmeware_version=NeroFW.V121,
                interface="socketcan",
                channel=CAN_IFACE,
            ))
            robot.connect()
            robot.electronic_emergency_stop()
            # Return value of this SDK call is not an acknowledgement.
            update_latch("STOP_COMMAND_SENT_UNVERIFIED", usb_serial=serial)
            record("STOP_COMMAND_SENT_UNVERIFIED", usb_serial=serial)
            time.sleep(0.25)
            s = robot.get_arm_status()
            if s is not None:
                code = str(getattr(s.msg, "arm_status", "UNKNOWN"))
                record("ARM_STATUS_AFTER_STOP", arm_status=code,
                       error_code=getattr(s.msg, "err_code", None))
                if "EMERGENCY_STOP" in code:
                    update_latch("STOP_CONFIRMED_BY_ARM_STATUS", arm_status=code)
            else:
                record("ARM_STATUS_AFTER_STOP_MISSING")
            return 0
        except Exception as exc:
            update_latch("STOP_DELIVERY_FAILED", error=str(exc))
            record("STOP_DELIVERY_FAILED", error=str(exc))
            print(f"STOP DELIVERY FAILED: {exc}", file=sys.stderr)
            return 2
        finally:
            if robot is not None:
                try:
                    robot.disconnect()
                except Exception as exc:
                    record("DISCONNECT_WARNING", error=str(exc))

if __name__ == "__main__":
    sys.exit(main())
