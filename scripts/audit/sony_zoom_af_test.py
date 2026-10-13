#!/usr/bin/env python3
"""Diagnostic BLE zoom + fresh PTP AF + original RAW/JPEG + continuous UVC.

--inspect performs GATT inventory/read/passive notifications, without lens or
shutter commands. --run explicitly starts a new 3- or 10-shot hardware test.
"""
import argparse
import datetime
import fcntl
import math
import os
import re
import signal
import time

import sony_af_prototype as af

SERVICE = "8000ff00-ff00-ffff-ffff-ffffffffffff"
WRITE = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000ff02-0000-1000-8000-00805f9b34fb"
DD21 = "0000dd21-0000-1000-8000-00805f9b34fb"
COMMANDS = {"WIDE": (bytes.fromhex("02 47 10"), bytes.fromhex("02 46 00")),
            "TELE": (bytes.fromhex("02 45 10"), bytes.fromhex("02 44 00"))}


def pulse(write, direction, seconds, pause=time.sleep, clock=time.monotonic):
    """Never retry PRESS. Even an ambiguous PRESS must be followed by RELEASE.

    Failure of the first RELEASE remains FAIL even if its safety retry succeeds.
    Neither ACK nor this function confirms optical motion or a mechanical stop.
    """
    if direction not in COMMANDS or not math.isfinite(seconds) or not 0 < seconds <= 1:
        raise af.GateError("ZOOM_ARGUMENTS")
    press, release = COMMANDS[direction]
    row = {"direction": direction, "hold_after_ack_s": seconds,
           "press_requests": 1, "release_ack": False, "status": "FAIL"}
    start = clock()
    try:
        write(press)
        row["press_ack"] = True
        pause(seconds)
    except BaseException as error:
        row["error"] = type(error).__name__  # No private D-Bus paths in report.
    finally:
        # A second stop signal cannot interrupt the bounded release attempts.
        handlers = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            write(release)
            row["release_ack"] = True
        except BaseException as error:
            row["release_error"] = type(error).__name__
            try:
                write(release)
                row["safety_release_retry_ack"] = True
            except BaseException as retry_error:
                row["safety_release_retry_error"] = type(retry_error).__name__
        finally:
            for s, handler in handlers.items():
                signal.signal(s, handler)
        row["elapsed_s"] = round(clock() - start, 6)
    if row.get("press_ack") and row["release_ack"] and "error" not in row:
        row["status"] = "PASS"
    return row


def focal_length(files):
    jpeg = [f for f in files if f["file"].lower().endswith(".jpg")]
    if len(jpeg) != 1:
        raise af.GateError("EXIF_JPEG_NOT_UNIQUE")
    try:
        value = float(jpeg[0]["exif"]["focal_length_mm"])
    except (KeyError, TypeError, ValueError):
        raise af.GateError("EXIF_FOCAL_MISSING") from None
    if not math.isfinite(value) or not 16 <= value <= 50:
        raise af.GateError("EXIF_FOCAL_OUTSIDE_TESTED_16_50_LENS")
    return value


def verify_motion(before, after, direction):
    if direction not in COMMANDS:
        raise af.GateError("ZOOM_DIRECTION_UNKNOWN")
    delta = after - before
    if (direction == "WIDE" and delta >= 0) or (direction == "TELE" and delta <= 0):
        raise af.GateError("ZOOM_DIRECTION_OR_NO_EXIF_CHANGE")
    return round(delta, 6)


def direction_for(number, baseline):
    # Start away from the nearer endpoint. No estimated absolute positioning.
    first = "WIDE" if baseline >= 33 else "TELE"
    return first if number % 2 == 0 else ("TELE" if first == "WIDE" else "WIDE")


class BLE:
    def __init__(self):
        # System dbus-python / PyGObject already installed on VENTUNO; no pip.
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
        DBusGMainLoop(set_as_default=True)
        self.dbus, self.context = dbus, GLib.MainContext.default()
        self.bus = dbus.SystemBus()
        self.manager = dbus.Interface(self.bus.get_object("org.bluez", "/"),
                                      "org.freedesktop.DBus.ObjectManager")
        self.notifications, self.inventory = [], []
        self.started = time.monotonic()
        self.notify_started = False
        self.receiver = None
        objects = self.manager.GetManagedObjects(timeout=3)
        candidates = [p for p, i in objects.items() if "org.bluez.Device1" in i
                      and str(i["org.bluez.Device1"].get("Name", "")) == "ILCE-6100A"
                      and bool(i["org.bluez.Device1"].get("Paired", False))]
        if len(candidates) != 1:
            raise af.GateError("PAIRED_SONY_NOT_UNIQUE")
        self.device = candidates[0]
        self.gate()
        services = {p: str(i["org.bluez.GattService1"]["UUID"])
                    for p, i in objects.items() if "org.bluez.GattService1" in i
                    and i["org.bluez.GattService1"]["Device"] == self.device}
        remote = [p for p, uuid in services.items() if uuid == SERVICE]
        if len(remote) != 1:
            raise af.GateError("REMOTE_SERVICE_NOT_UNIQUE")
        chars = {}
        self.dd21_path = None
        for path, interfaces in objects.items():
            data = interfaces.get("org.bluez.GattCharacteristic1")
            if data is None or data["Service"] not in services:
                continue
            uuid, flags = str(data["UUID"]), list(map(str, data["Flags"]))
            self.inventory.append({"service_uuid": services[data["Service"]],
                                   "uuid": uuid, "flags": flags})
            if data["Service"] == remote[0]:
                if uuid in chars:
                    raise af.GateError("REMOTE_CHARACTERISTIC_NOT_UNIQUE")
                chars[uuid] = (path, flags)
            if uuid == DD21 and "read" in flags:
                self.dd21_path = path
        if WRITE not in chars or "write" not in chars[WRITE][1]:
            raise af.GateError("REMOTE_WRITE_MISSING")
        if NOTIFY not in chars or "notify" not in chars[NOTIFY][1]:
            raise af.GateError("REMOTE_NOTIFY_MISSING")
        self.writer = dbus.Interface(self.bus.get_object("org.bluez", chars[WRITE][0]),
                                     "org.bluez.GattCharacteristic1")
        self.notify = dbus.Interface(self.bus.get_object("org.bluez", chars[NOTIFY][0]),
                                     "org.bluez.GattCharacteristic1")
        properties = dbus.Interface(self.bus.get_object("org.bluez", chars[NOTIFY][0]),
                                     "org.freedesktop.DBus.Properties")
        if properties.Get("org.bluez.GattCharacteristic1", "Notifying", timeout=2):
            raise af.GateError("REMOTE_NOTIFY_ALREADY_OWNED")
        self.receiver = self.bus.add_signal_receiver(
            self.changed, signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties", path=str(chars[NOTIFY][0]))
        try:
            self.notify_started = True  # Stop also after an ambiguous StartNotify.
            self.notify.StartNotify(timeout=2)
        except BaseException:
            self.close()
            raise

    def gate(self):
        d = self.dbus.Interface(self.bus.get_object("org.bluez", self.device),
                                "org.freedesktop.DBus.Properties").GetAll("org.bluez.Device1", timeout=2)
        if str(d.get("Name", "")) != "ILCE-6100A" or d.get("Blocked", False):
            raise af.GateError("BLE_DEVICE_GATE")
        if not all(d.get(k, False) for k in ("Paired", "Connected", "ServicesResolved")):
            raise af.GateError("BLE_NOT_READY_NO_RECONNECT_DURING_RUN")

    def changed(self, interface, changed, invalid):
        if interface == "org.bluez.GattCharacteristic1" and "Value" in changed:
            value = bytes(changed["Value"])
            self.notifications.append({"callback_s": round(time.monotonic() - self.started, 6),
                                       "hex": value.hex(), "position_interpretation": "NONE"})

    def pause(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while self.context.pending():
                self.context.iteration(False)
            time.sleep(min(.02, max(0, deadline - time.monotonic())))

    def write(self, data):
        # RELEASE must bypass the connection gate: attempt it even after failure.
        self.writer.WriteValue(self.dbus.Array(data, signature="y"),
                               self.dbus.Dictionary({"type": self.dbus.String("request")},
                                                    signature="sv"), timeout=2)

    def read_location_flags(self):
        if self.dd21_path is None:
            return {"status": "ABSENT"}
        value = self.dbus.Interface(self.bus.get_object("org.bluez", self.dd21_path),
                                   "org.bluez.GattCharacteristic1").ReadValue(
                                       self.dbus.Dictionary({}, signature="sv"), timeout=2)
        return {"status": "PASS", "length": len(value), "hex": bytes(value).hex(),
                "meaning": "location_feature_flags_not_lens_position"}

    def close(self):
        try:
            if self.notify_started:
                self.notify.StopNotify(timeout=2)
        finally:
            self.notify_started = False
            if self.receiver is not None:
                self.receiver.remove()
                self.receiver = None


def interrupted(sig, frame):
    raise InterruptedError("SIGNAL_" + str(sig))


def run(args):
    af.nvme_guard()
    # Same PTP lock as PR #11, plus the prior BLE diagnostic's lock.
    locks = []
    try:
        for path in (af.BASE / "tools/sony-af-prototype/camera.lock",
                     af.BASE / "tools/streamdeck-eval/sony-ble-one-shot.lock"):
            handle = path.open("a")
            locks.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        session = af.create_session(af.BASE / "vision/sessions" / ("sony-zoom-af-" + stamp))
        report = {"test": "BLE_INSPECT" if args.inspect else "BLE_ZOOM_AF_RAW_JPEG_UVC",
                  "status": "FAIL", "session": session.name, "utc_start": stamp,
                  "planned_shots": 0 if args.inspect else args.shots, "attempts": [],
                  "zoom_pulses": [], "automatic_shutter_retries": 0,
                  "ble_position_readout": "NOT_AVAILABLE_IN_TESTED_REMOTE_PROTOCOL",
                  "optical_measurement": "JPEG_EXIF_AFTER_EACH_PHOTO",
                  "raw_full_decode": "UNKNOWN", "sd_comparison": "UNKNOWN",
                  "zoom_settle_s": args.settle, "zoom_pulse_s": args.pulse,
                  "interval_after_pair_s": args.interval, "af_timeout_s": args.af_timeout}
        camera, uvc, ble = None, None, None
        start = time.monotonic()
        old_signals = {s: signal.signal(s, interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            ble = BLE()
            report["gatt_inventory"] = ble.inventory
            if args.inspect:
                report["location_feature_read"] = ble.read_location_flags()
                ble.pause(10)
                ble.gate()
                report["status"] = "PASS"
            else:
                camera = af.Shell(session, args.gphoto, args.library_dir, af.detect_port())
                if not re.search(r"Model:\s*ILCE-6100A\b", camera.command("summary")):
                    raise af.GateError("MODEL_GATE")
                expected = {"focusmode": "AF-A", "capturemode": "Single Shot",
                            "capturetarget": "card+sdram", "imagequality": "RAW+JPEG (X.Fine)"}
                report["config"] = {key: camera.current(key, fresh=True) for key in expected}
                if report["config"] != expected or camera.buffer() != 0:
                    raise af.GateError("CONFIG_OR_BUFFER_GATE")
                uvc = af.UVC(session, camera.env)
                if not uvc.ready.wait(25):
                    raise af.GateError("UVC_WARMUP_TIMEOUT")
                uvc.gate()
                previous, baseline = None, None
                for number in range(1, args.shots + 1):
                    af.nvme_guard()
                    ble.gate()
                    uvc.gate()
                    if camera.buffer() != 0:
                        raise af.GateError("BUFFER_BEFORE_ZOOM")
                    folder = session / ("shot-%02d" % number)
                    folder.mkdir()
                    camera.command("lcd " + str(folder))
                    direction = None
                    if number > 1:
                        direction = direction_for(number, baseline)
                        movement = pulse(ble.write, direction, args.pulse, ble.pause)
                        report["zoom_pulses"].append(movement)
                        af.write_json(session / "checkpoint.json", report)
                        if movement["status"] != "PASS":
                            raise af.GateError("ZOOM_PRESS_OR_RELEASE_FAILED_NO_SHUTTER")
                        ble.pause(args.settle)  # Bounded delay, no mechanical-position ACK.
                        ble.gate()
                        uvc.gate()
                    shot_start = time.monotonic()
                    print("SHOT %02d %s AF_STARTED" % (number, direction or "BASELINE"), flush=True)
                    def mark():
                        af.nvme_guard()
                        uvc.gate()
                        ble.gate()
                        fd = os.open(folder / "full-press-attempted", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "w") as handle:
                            handle.write("One full-press request; no retry.\n")
                            handle.flush()
                            os.fsync(handle.fileno())
                    attempt = af.af_then_shutter(camera, mark, args.af_timeout)
                    attempt.update(number=number, zoom_direction=direction)
                    report["attempts"].append(attempt)
                    af.write_json(session / "checkpoint.json", report)
                    if attempt["status"] != "SHUTTER_REQUESTED":
                        raise af.GateError(attempt.get("error", "SHUTTER_OR_RELEASE_FAILED"))
                    deadline = time.monotonic() + 40
                    while time.monotonic() < deadline:
                        af.nvme_guard()
                        uvc.gate()
                        ble.gate()
                        camera.command("wait-event-and-download 1s", timeout=20)
                        ble.pause(.001)
                        if len(af.photo_paths(folder)) > 2:
                            raise af.GateError("EXTRA_IMAGE_OBJECTS")
                        if len(af.photo_paths(folder)) == 2:
                            break
                    attempt["files"] = af.validate_pair(folder)
                    attempt["buffer_settle_samples"] = af.wait_buffer_idle(camera)
                    current = focal_length(attempt["files"])
                    attempt["focal_mm"] = current
                    if previous is not None:
                        attempt["focal_delta_mm"] = verify_motion(previous, current, direction)
                    else:
                        baseline = current
                    previous = current
                    attempt["status"] = "PASS"
                    attempt["complete_pair_s"] = round(time.monotonic() - shot_start, 6)
                    af.write_json(session / "checkpoint.json", report)
                    print("SHOT %02d PASS focal=%.1fmm" % (number, current), flush=True)
                    if number < args.shots:
                        ble.pause(args.interval)
                report["status"] = "PASS"
        except BaseException as error:
            # Keep exception details only in private log; D-Bus paths contain MACs.
            af.nvme_guard()
            (session / "error-private.log").write_text(repr(error) + "\n")
            report["error_type"] = type(error).__name__
            report["error"] = str(error) if isinstance(error, af.GateError) else "SEE_PRIVATE_LOG"
            print("STOP_NO_RETRY " + report["error"], flush=True)
        finally:
            for s in old_signals:
                signal.signal(s, signal.SIG_IGN)
            if camera is not None:
                try:
                    if camera.usable:
                        failures = []
                        for action in ("capture", "autofocus"):
                            try:
                                camera.set_action(action, 0)
                            except Exception:
                                failures.append(action)
                        report["ptp_release_ack"] = not failures
                    else:
                        report["ptp_release_ack"] = camera.recover_release()
                except Exception:
                    report["ptp_release_ack"] = False
                if not report["ptp_release_ack"]:
                    report["status"] = "FAIL"
                camera.close()
            if uvc is not None:
                uvc.close()
                report["uvc"] = uvc.report()
                af.write_json(session / "uvc-frames.json", uvc.rows)
                if uvc.errors:
                    report["status"] = "FAIL"
            if ble is not None:
                report["ble_notifications"] = ble.notifications
                try:
                    ble.gate()
                    report["ble_postflight"] = "PASS"
                except Exception:
                    report["ble_postflight"] = "FAIL"
                    report["status"] = "FAIL"
                try:
                    ble.close()
                except Exception:
                    report["notify_stop"] = "FAIL"
                    report["status"] = "FAIL"
            report["full_press_requests"] = sum(a["full_press_requests"] for a in report["attempts"])
            report["verified_shots"] = sum(a["status"] == "PASS" for a in report["attempts"])
            report["elapsed_s"] = round(time.monotonic() - start, 6)
            af.write_json(session / "result.json", report)
            for s, previous_handler in old_signals.items():
                signal.signal(s, previous_handler)
        print("RESULT " + str(session / "result.json"), flush=True)
        print("FINAL " + report["status"], flush=True)
        return 0 if report["status"] == "PASS" else 1
    finally:
        for handle in reversed(locks):
            handle.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--shots", type=int, choices=(3, 10), default=3)
    parser.add_argument("--pulse", type=float, default=.65)
    parser.add_argument("--settle", type=float, default=1)
    parser.add_argument("--af-timeout", type=float, default=8)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--gphoto", default=str(af.BASE / "tools/sony-a6100-verify/root/usr/bin/gphoto2"))
    parser.add_argument("--library-dir", default=str(af.BASE / "tools/sony-a6100-verify/root/usr/lib/aarch64-linux-gnu"))
    args = parser.parse_args()
    if (not all(math.isfinite(x) for x in (args.pulse, args.settle, args.af_timeout, args.interval))
            or not 0 < args.pulse <= 1 or not 1 <= args.settle <= 5
            or not 0 < args.af_timeout <= 15 or not 10 <= args.interval <= 60):
        parser.error("pulse (0,1], settle [1,5], AF (0,15], interval [10,60], all finite")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
