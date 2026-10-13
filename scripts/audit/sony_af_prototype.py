#!/usr/bin/env python3
"""Diagnostic Sony ILCE-6100A AF-before-shutter prototype. No service integration."""
import argparse
import datetime
import fcntl
import hashlib
import io
import json
import os
import re
import select
import subprocess
import threading
import time
from pathlib import Path

BASE = Path("/srv/vision-data")
FOCUSED = 2  # Only the value observed on this ILCE-6100A; other values fail closed.


class GateError(RuntimeError):
    pass


def nvme_guard(base=BASE):
    mount = json.loads(subprocess.check_output(
        ["findmnt", "-J", "-T", str(base), "-o", "TARGET,SOURCE,FSTYPE,OPTIONS,LABEL"],
        text=True))["filesystems"][0]
    valid = (mount["target"] == str(base)
             and mount["source"].startswith("/dev/nvme")
             and mount["fstype"] == "ext4" and mount["label"] == "VISION_DATA"
             and "rw" in mount["options"].split(","))
    if not valid:
        raise GateError("NVME_UNAVAILABLE")
    if os.statvfs(base).f_bavail * os.statvfs(base).f_frsize < 2 * 1024**3:
        raise GateError("NVME_FREE_SPACE_LOW")


def create_session(path, guard=nvme_guard):
    guard()
    path = Path(path)
    if not path.resolve().is_relative_to(BASE.resolve()):
        raise GateError("SESSION_OUTSIDE_NVME")
    path.mkdir(exist_ok=False)
    return path


def write_json(path, value):
    nvme_guard()
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class Shell:
    """Exactly one camera owner; shell commands never invoke generic capture."""
    def __init__(self, session, binary, library_dir, port):
        self.session, self.port, self.binary = session, port, binary
        self.env = os.environ.copy()
        self.env["LD_LIBRARY_PATH"] = library_dir
        for key in ("TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            self.env[key] = str(session)
        self.log = (session / "ptp-shell-private.log").open("wb")
        self.usable = True
        self.process = subprocess.Popen(
            [binary, "--port=" + port, "--camera=USB PTP Class Camera", "--keep",
             "--filename=original.%C", "--debug", "--debug-loglevel=debug",
             "--debug-logfile=" + str(session / "ptp-debug-private.log"), "--shell"],
            cwd=session, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0)
        try:
            self._prompt(20)
        except BaseException:
            self.close()
            raise

    def _prompt(self, timeout):
        deadline = time.monotonic() + timeout
        data = b""
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.usable = False
                raise GateError("PTP_PROCESS_EXIT")
            readable, _, _ = select.select([self.process.stdout], [], [], 0.1)
            if not readable:
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                self.usable = False
                raise GateError("PTP_EOF")
            self.log.write(chunk)
            self.log.flush()
            data += chunk
            if len(data) > 1024 * 1024:
                self.usable = False
                raise GateError("PTP_RESPONSE_LIMIT")
            if re.search(rb"gphoto2: [^\r\n]*> $", data):
                return data.decode(errors="replace")
        self.usable = False
        raise GateError("PTP_COMMAND_TIMEOUT_NO_RETRY")

    def command(self, command, timeout=20):
        if not self.usable:
            raise GateError("PTP_SESSION_UNUSABLE")
        self.process.stdin.write((command + "\n").encode())
        self.process.stdin.flush()
        response = self._prompt(timeout)
        if re.search(r"ERROR:|Could not", response, re.I):
            raise GateError("PTP_COMMAND_ERROR:" + command.split()[0])
        return response

    def current(self, name, fresh=False):
        # Two serial reads account for the one-response lag seen in this driver.
        value = None
        for _ in range(2 if fresh else 1):
            response = self.command("get-config " + name)
            matches = re.findall(r"^Current: (.*)$", response, re.M)
            if len(matches) != 1:
                raise GateError("CONFIG_VALUE_MISSING:" + name)
            value = matches[0].strip()
        return value

    def focus(self):
        return int(self.current("d213", fresh=True))

    def buffer(self):
        return int(self.current("d215", fresh=True))

    def set_action(self, name, value):
        if name not in ("autofocus", "capture") or value not in (0, 1):
            raise GateError("ACTION_NOT_ALLOWED")
        self.command("set-config /main/actions/" + name + "=" + str(value))

    def close(self):
        if self.process.poll() is None:
            if self.usable:
                try:
                    self.process.stdin.write(b"exit\n")
                    self.process.stdin.flush()
                    self.process.wait(timeout=3)
                except Exception:
                    pass
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        self.log.close()

    def recover_release(self):
        # Only after the original owner has exited, never another exposure.
        self.close()
        result = subprocess.run(
            [self.binary, "--port=" + self.port, "--camera=USB PTP Class Camera",
             "--set-config=/main/actions/capture=0",
             "--set-config=/main/actions/autofocus=0"],
            cwd=self.session, env=self.env, capture_output=True, text=True, timeout=20)
        nvme_guard()
        (self.session / "emergency-release-private.log").write_text(
            result.stdout + result.stderr)
        return result.returncode == 0 and not re.search(
            r"ERROR:|Could not", result.stdout + result.stderr, re.I)


def af_then_shutter(camera, before_shutter, af_timeout=8.0,
                    clock=time.monotonic, pause=time.sleep):
    """A failed/stale AF gate sends zero full-press requests; never retries."""
    result = {"status": "FAIL", "phase": "RESET", "full_press_requests": 0,
              "af_samples": [], "release_errors": []}
    half_attempted = False
    start = clock()
    try:
        camera.set_action("capture", 0)
        camera.set_action("autofocus", 0)
        if camera.buffer() != 0:
            raise GateError("PENDING_IMAGE_RECOVERY_REQUIRED")
        baseline = camera.focus()
        result["focus_baseline"] = baseline
        if baseline != 1:
            raise GateError("FOCUS_BASELINE_NOT_RESET")
        result["phase"] = "AF_WAIT"
        half_attempted = True
        af_start = clock()
        camera.set_action("autofocus", 1)
        previous_confirmed = None
        deadline = af_start + af_timeout
        while clock() < deadline:
            value = camera.focus()
            observed = clock()
            result["af_samples"].append(
                {"since_halfpress_s": round(observed - af_start, 6), "value": value})
            if observed >= deadline:
                break
            if value == FOCUSED:
                if previous_confirmed is not None and observed - previous_confirmed >= .05:
                    result["af_confirmation_s"] = round(observed - af_start, 6)
                    break
                previous_confirmed = observed
            else:
                previous_confirmed = None
            pause(.1)
        else:
            raise GateError("AF_TIMEOUT_NO_SHUTTER")
        if "af_confirmation_s" not in result:
            raise GateError("AF_TIMEOUT_NO_SHUTTER")
        result["phase"] = "SHUTTER"
        before_shutter()  # Storage, UVC and durable one-attempt marker.
        result["full_press_requests"] = 1  # Outcome ambiguous even on command failure.
        camera.set_action("capture", 1)
        pause(.15)  # Single Shot gate is required by preflight.
        result["status"] = "SHUTTER_REQUESTED"
        result["phase"] = "RELEASE"
    except Exception as error:
        result["error"] = type(error).__name__ + ":" + str(error)
    finally:
        if half_attempted or result["full_press_requests"]:
            for action in ("capture", "autofocus"):
                try:
                    camera.set_action(action, 0)
                except Exception as error:
                    result["release_errors"].append(action + ":" + str(error))
        result["elapsed_s"] = round(clock() - start, 6)
        if result["release_errors"]:
            result["status"] = "FAIL"
    return result


class UVC:
    def __init__(self, session, env):
        from PIL import Image
        self.Image, self.session = Image, session
        self.rows, self.samples, self.errors = [], [], []
        self.ready, self.stop = threading.Event(), threading.Event()
        self.started = time.monotonic()
        self.last = None
        self.log = (session / "uvc-stream.log").open("wb")
        self.process = subprocess.Popen(
            ["v4l2-ctl", "-d", "/dev/video0",
             "--set-fmt-video=width=1920,height=1080,pixelformat=MJPG",
             "--set-parm=30", "--stream-mmap", "--stream-count=12600", "--stream-to=-"],
            cwd=session, env=env, stdout=subprocess.PIPE, stderr=self.log,
            bufsize=0, start_new_session=True)
        self.thread = threading.Thread(target=self._collect, daemon=True)
        self.thread.start()

    def sample(self, payload, role, index):
        with self.Image.open(io.BytesIO(payload)) as image:
            image.load()
            dimensions = list(image.size)
        if dimensions != [1920, 1080]:
            raise GateError("UVC_DIMENSIONS")
        nvme_guard()
        (self.session / ("uvc-" + role + ".jpg")).write_bytes(payload)
        self.samples.append({"role": role, "index": index, "dimensions": dimensions})

    def _collect(self):
        buffer = b""
        try:
            while not self.stop.is_set():
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    break
                received = time.monotonic()
                buffer += chunk
                while True:
                    begin = buffer.find(b"\xff\xd8")
                    if begin < 0:
                        buffer = buffer[-1:]
                        break
                    end = buffer.find(b"\xff\xd9", begin + 2)
                    if end < 0:
                        buffer = buffer[begin:]
                        break
                    payload = buffer[begin:end + 2]
                    buffer = buffer[end + 2:]
                    index = len(self.rows)
                    self.rows.append({"index": index,
                                      "receive_s": round(received - self.started, 6),
                                      "bytes": len(payload),
                                      "sha256": hashlib.sha256(payload).hexdigest()})
                    self.last = payload
                    if index == 119:
                        self.sample(payload, "before", index)
                        self.ready.set()
                if len(buffer) > 4 * 1024**2:
                    raise GateError("UVC_BUFFER_LIMIT")
        except Exception as error:
            self.errors.append(type(error).__name__ + ":" + str(error))

    def gate(self):
        if (self.errors or self.process.poll() is not None or not self.rows
                or time.monotonic() - self.started - self.rows[-1]["receive_s"] > 1):
            raise GateError("UVC_UNAVAILABLE")

    def close(self):
        if self.last and not self.errors:
            try:
                self.sample(self.last, "after", len(self.rows) - 1)
            except Exception as error:
                self.errors.append(str(error))
        self.stop.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.thread.join(timeout=3)
        self.log.close()

    def report(self):
        gaps = [b["receive_s"] - a["receive_s"]
                for a, b in zip(self.rows, self.rows[1:])]
        runs, first = [], 0
        for index in range(1, len(self.rows) + 1):
            if index == len(self.rows) or self.rows[index]["sha256"] != self.rows[first]["sha256"]:
                if index - first > 1 and self.rows[first]["receive_s"] >= 3:
                    runs.append({"count": index - first,
                                 "start_s": self.rows[first]["receive_s"],
                                 "span_s": round(self.rows[index - 1]["receive_s"]
                                                 - self.rows[first]["receive_s"], 6)})
                first = index
        return {"frames_received": len(self.rows),
                "unique_payloads": len({row["sha256"] for row in self.rows}),
                "max_receive_gap_s": round(max(gaps), 6) if gaps else None,
                "longest_identical_run_after_3s": max(runs, key=lambda x: x["span_s"]) if runs else None,
                "samples": self.samples, "collector_errors": self.errors,
                "timing_method": "host_pipe_receipt_not_sensor_timestamp"}


def photo_paths(folder):
    return sorted(path for path in folder.iterdir()
                  if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".arw"))


def validate_pair(folder):
    from PIL import Image
    paths = photo_paths(folder)
    if len(paths) != 2 or {p.suffix.lower() for p in paths} != {".jpg", ".arw"}:
        raise GateError("PAIR_INCOMPLETE_OR_EXTRA")
    files = []
    for path in paths:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            header = handle.read(4)
            handle.seek(0)
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        item = {"file": path.name, "size_bytes": path.stat().st_size,
                "sha256": digest.hexdigest()}
        if path.suffix.lower() == ".jpg":
            with Image.open(path) as image:
                image.load()
                item["dimensions"] = list(image.size)
                exif = image.getexif().get_ifd(34665)
                item["exif"] = {name: str(exif.get(key)) for name, key in (
                    ("datetime_original", 36867), ("exposure_s", 33434),
                    ("f_number", 33437), ("iso", 34855), ("focal_length_mm", 37386))}
            if item["dimensions"] != [6000, 4000]:
                raise GateError("JPEG_DIMENSIONS")
            item["full_decode"] = "PASS"
        else:
            if header not in (b"II*\x00", b"MM\x00*"):
                raise GateError("RAW_HEADER")
            item["tiff_header"] = "PASS"
            item["raw_full_decode"] = "UNKNOWN"
        files.append(item)
    return files


def detect_port():
    ports = []
    for device in Path("/sys/bus/usb/devices").iterdir():
        try:
            if ((device / "idVendor").read_text().strip() == "054c"
                    and (device / "idProduct").read_text().strip() == "0f0d"):
                ports.append("usb:%03d,%03d" % (
                    int((device / "busnum").read_text()), int((device / "devnum").read_text())))
        except (FileNotFoundError, NotADirectoryError):
            pass
    if len(ports) != 1:
        raise GateError("SONY_PC_REMOTE_NOT_UNIQUE")
    return ports[0]


def run(args):
    nvme_guard()
    lock_path = BASE / "tools/sony-af-prototype/camera.lock"
    lock_path.parent.mkdir(exist_ok=True)
    lock = lock_path.open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session = create_session(BASE / "vision/sessions" / ("sony-af-prototype-" + stamp))
    report = {"test": "AF_BEFORE_SINGLE_SHOT", "utc_start": stamp,
              "session": session.name, "planned_shots": args.shots, "af_timeout_s": args.af_timeout,
              "interval_after_verified_pair_s": args.interval, "status": "FAIL",
              "attempts": [], "automatic_retries": 0, "settings_changed": False,
              "raw_full_decode": "UNKNOWN", "sd_comparison": "UNKNOWN",
              "limits": ["AF state is a protocol confirmation, not optical quality validation.",
                         "No full RAW decode or direct SD comparison.",
                         "UVC receipts do not prove scene freshness or sensor-to-screen latency.",
                         "Private shell/debug logs and samples must not be committed."]}
    camera, uvc = None, None
    start = time.monotonic()
    try:
        camera = Shell(session, args.gphoto, args.library_dir, detect_port())
        summary = camera.command("summary")
        if not re.search(r"Model:\s*ILCE-6100A\b", summary):
            raise GateError("MODEL_GATE")
        config = {key: camera.current(key, fresh=True) for key in (
            "focusmode", "capturemode", "capturetarget", "imagequality")}
        report["config"] = config
        if config != {"focusmode": "AF-A", "capturemode": "Single Shot",
                      "capturetarget": "card+sdram", "imagequality": "RAW+JPEG (X.Fine)"}:
            raise GateError("CONFIG_GATE")
        if camera.buffer() != 0:
            raise GateError("PENDING_IMAGE_RECOVERY_REQUIRED")
        uvc = UVC(session, camera.env)
        if not uvc.ready.wait(14):
            raise GateError("UVC_WARMUP_TIMEOUT")
        uvc.gate()
        for number in range(1, args.shots + 1):
            nvme_guard()
            folder = session / ("shot-%02d" % number)
            folder.mkdir()
            camera.command("lcd " + str(folder))
            shot_start = time.monotonic()
            print("SHOT %02d AF_STARTED" % number, flush=True)
            def mark():
                nvme_guard()
                uvc.gate()
                fd = os.open(folder / "full-press-attempted", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as handle:
                    handle.write("One distinct diagnostic full-press request; no automatic retry.\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            attempt = af_then_shutter(camera, mark, args.af_timeout)
            attempt["number"] = number
            attempt["start_s"] = round(shot_start - start, 6)
            report["attempts"].append(attempt)
            write_json(session / "checkpoint.json", report)
            if attempt["status"] != "SHUTTER_REQUESTED":
                raise GateError(attempt.get("error", "SHUTTER_OR_RELEASE_FAILED"))
            download_start = time.monotonic()
            while time.monotonic() - download_start < 40:
                nvme_guard()
                uvc.gate()
                camera.command("wait-event-and-download 1s", timeout=20)
                if len(photo_paths(folder)) > 2:
                    raise GateError("EXTRA_IMAGE_OBJECTS")
                if len(photo_paths(folder)) == 2:
                    break
            attempt["files"] = validate_pair(folder)
            if camera.buffer() != 0:
                raise GateError("UNEXPECTED_PENDING_OBJECT_NO_NEXT_SHOT")
            attempt["status"] = "PASS"
            attempt["complete_pair_s"] = round(time.monotonic() - shot_start, 6)
            write_json(session / "checkpoint.json", report)
            print("SHOT %02d PASS; AF=%.3fs; PAIR=%.3fs" % (
                number, attempt["af_confirmation_s"], attempt["complete_pair_s"]), flush=True)
            if number < args.shots:
                time.sleep(args.interval)
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = type(error).__name__ + ":" + str(error)
        print("STOP_NO_RETRY " + report["error"], flush=True)
    finally:
        if camera is not None:
            # Always release after an exception, including a stalled shell.
            try:
                if camera.usable:
                    release_failures = []
                    for action in ("capture", "autofocus"):
                        try:
                            camera.set_action(action, 0)
                        except Exception as error:
                            release_failures.append(action + ":" + str(error))
                    report["release_confirmed"] = not release_failures
                    if release_failures:
                        report["release_errors"] = release_failures
                else:
                    report["release_confirmed"] = camera.recover_release()
            except Exception as error:
                report["release_confirmed"] = False
                report["release_error"] = str(error)
            if not report["release_confirmed"]:
                report["status"] = "FAIL"
            camera.close()
        if uvc is not None:
            uvc.close()
            report["uvc"] = uvc.report()
            write_json(session / "uvc-frames.json", uvc.rows)
            if uvc.errors:
                report["status"] = "FAIL"
        report["full_press_requests"] = sum(a["full_press_requests"] for a in report["attempts"])
        report["verified_pairs"] = sum(a["status"] == "PASS" for a in report["attempts"])
        report["elapsed_s"] = round(time.monotonic() - start, 6)
        report["utc_end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(session / "result.json", report)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    print("FINAL " + json.dumps(report), flush=True)
    return 0 if report["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly run the authorized hardware diagnostic")
    parser.add_argument("--shots", type=int, choices=(1, 10), default=1)
    parser.add_argument("--af-timeout", type=float, default=8)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--gphoto", default=str(BASE / "tools/sony-a6100-verify/root/usr/bin/gphoto2"))
    parser.add_argument("--library-dir", default=str(BASE / "tools/sony-a6100-verify/root/usr/lib/aarch64-linux-gnu"))
    args = parser.parse_args()
    if not args.run:
        parser.error("--run is required; importing this module never controls hardware")
    if not 0 < args.af_timeout <= 15 or args.interval < 10:
        parser.error("AF timeout must be (0,15] and interval at least 10 seconds")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
