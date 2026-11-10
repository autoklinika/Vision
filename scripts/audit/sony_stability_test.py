#!/usr/bin/env python3
"""Explicit Sony stability acquisition, read-only SD comparison and assessment.

No hardware is opened on import/help/assess. `run` explicitly captures 50/100
photos PER mode. `compare` requires an operator-mounted read-only Sony SD.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import signal
import statistics
import time
from pathlib import Path

import sony_af_prototype as af
import sony_zoom_af_test as zoom
import sony_ptp_sd_compare as sd

EXPECTED_CONFIG = {"focusmode": "AF-A", "capturemode": "Single Shot",
                   "capturetarget": "card+sdram", "imagequality": "RAW+JPEG (X.Fine)"}
MIB = 1024**2


def modes(name):
    return ["fixed", "zoom"] if name == "both" else [name]


def session_guard(path):
    af.nvme_guard()
    path = path.resolve(strict=True)
    if not path.is_relative_to((af.BASE / "vision/sessions").resolve()):
        raise af.GateError("SESSION_OUTSIDE_VISION_NVME")
    return path


def space_guard(remaining):
    af.nvme_guard()
    v = os.statvfs(af.BASE)
    # 64 MiB per remaining RAW+JPEG pair, plus a 2 GiB reserve.
    if v.f_bavail * v.f_frsize < remaining * 64 * MIB + 2 * 1024**3:
        raise af.GateError("NVME_REMAINING_SERIES_RESERVE")


def config_gate(camera):
    observed = {key: camera.current(key, fresh=True) for key in EXPECTED_CONFIG}
    if observed != EXPECTED_CONFIG or camera.buffer() != 0:
        raise af.GateError("CONFIG_OR_PENDING_BUFFER")
    return observed


class Monitor:
    """Check live reception and all logged gaps/pattern detections after ready."""
    def __init__(self, uvc, ble, gap_limit=1.0):
        self.uvc, self.ble, self.gap_limit = uvc, ble, gap_limit
        self.cursor = len(uvc.rows)
        self.previous = uvc.rows[-1]["receive_s"] if uvc.rows else None
        self.pattern_baseline = uvc.pattern_checks
        self.max_gap = 0.0

    def gate(self):
        self.uvc.gate()
        if self.ble is not None:
            self.ble.gate()
        self.observe()

    def observe(self):
        # Also usable after intentional collector shutdown to inspect its tail.
        if self.uvc.pattern_checks > self.pattern_baseline:
            raise af.GateError("UVC_PATTERN_AFTER_READY")
        end = len(self.uvc.rows)
        for row in self.uvc.rows[self.cursor:end]:
            if self.previous is not None:
                self.max_gap = max(self.max_gap, row["receive_s"] - self.previous)
            self.previous = row["receive_s"]
        self.cursor = end
        if self.max_gap > self.gap_limit:
            raise af.GateError("UVC_RECEIVE_GAP_EXCEEDS_LIMIT")

    def pause(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.gate()
            remaining = max(0, deadline - time.monotonic())
            if self.ble is None:
                time.sleep(min(.25, remaining))
            else:
                self.ble.pause(min(.25, remaining))
        self.gate()


def durable_marker(folder):
    path = folder / "full-press-attempted"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write("One full-press attempt; never automatically retry.\n")
        handle.flush()
        os.fsync(handle.fileno())
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def execute_series(camera, monitor, ble, args, session, report):
    total = args.shots * len(modes(args.mode))
    for phase in modes(args.mode):
        phase_frame_start = len(monitor.uvc.rows)
        config_gate(camera)
        baseline = previous = None
        for number in range(1, args.shots + 1):
            space_guard(total - len(report["attempts"]))
            monitor.gate()
            if camera.buffer() != 0:
                raise af.GateError("BUFFER_BEFORE_NEXT_SHOT")
            folder = session / ("%s-shot-%03d" % (phase, number))
            folder.mkdir()
            camera.command("lcd " + str(folder))
            direction = None
            if phase == "zoom" and number > 1:
                direction = zoom.direction_for(number, baseline)
                movement = zoom.pulse(ble.write, direction, args.pulse, ble.pause)
                movement.update(phase=phase, before_shot=number)
                report["zoom_pulses"].append(movement)
                af.write_json(session / "checkpoint.json", report)
                if movement["status"] != "PASS":
                    raise af.GateError("ZOOM_FAILED_NO_NEXT_SHUTTER")
                monitor.pause(args.settle)
            attempt = {"phase": phase, "number": number, "folder": folder.name,
                       "zoom_direction": direction, "status": "IN_PROGRESS",
                       "full_press_requests": 0}
            report["attempts"].append(attempt)
            af.write_json(session / "checkpoint.json", report)
            started = time.monotonic()
            print("SHOT %s %03d/%03d AF_STARTED" % (phase, number, args.shots), flush=True)

            def mark():
                space_guard(total - len(report["attempts"]) + 1)
                monitor.gate()
                durable_marker(folder)

            try:
                attempt.update(af.af_then_shutter(camera, mark, args.af_timeout))
            finally:
                # Preserve conservative attempt count after signal/exception.
                if (folder / "full-press-attempted").exists():
                    attempt["full_press_requests"] = 1
            af.write_json(session / "checkpoint.json", report)
            if attempt["status"] != "SHUTTER_REQUESTED":
                raise af.GateError("AF_SHUTTER_OR_RELEASE_FAILED")
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                af.nvme_guard()
                monitor.gate()
                camera.command("wait-event-and-download 1s", timeout=20)
                if len(af.photo_paths(folder)) > 2:
                    raise af.GateError("EXTRA_IMAGE_OBJECTS")
                if len(af.photo_paths(folder)) == 2:
                    break
            attempt["files"] = af.validate_pair(folder)
            attempt["buffer_settle_samples"] = af.wait_buffer_idle(camera)
            monitor.gate()
            focal = zoom.focal_length(attempt["files"])
            attempt["focal_mm"] = focal
            if baseline is None:
                baseline = focal
            elif phase == "fixed" and focal != baseline:
                raise af.GateError("FIXED_ZOOM_EXIF_CHANGED")
            elif phase == "zoom":
                attempt["focal_delta_mm"] = zoom.verify_motion(previous, focal, direction)
            previous = focal
            attempt["complete_pair_s"] = round(time.monotonic() - started, 6)
            attempt["status"] = "PASS"
            af.write_json(session / "checkpoint.json", report)
            print("SHOT %s %03d PASS AF=%.3fs PAIR=%.3fs focal=%.1fmm" %
                  (phase, number, attempt["af_confirmation_s"], attempt["complete_pair_s"], focal), flush=True)
            if len(report["attempts"]) < total:
                monitor.pause(args.interval)
        report.setdefault("phase_postflight", {})[phase] = config_gate(camera)
        rows = monitor.uvc.rows[phase_frame_start:]
        gaps = [b["receive_s"] - a["receive_s"] for a, b in zip(rows, rows[1:])]
        report.setdefault("phase_uvc", {})[phase] = {
            "frames_received": len(rows), "unique_payloads": len({r["sha256"] for r in rows}),
            "max_receive_gap_s": max(gaps) if gaps else None,
            "host_span_s": rows[-1]["receive_s"] - rows[0]["receive_s"] if len(rows) > 1 else None}


def make_manifest(session, report):
    shots = []
    for a in report["attempts"]:
        # Even a zoom/QC failure after download leaves comparable originals.
        if not a.get("files") or a.get("focal_mm") is None:
            continue
        files = []
        for f in a["files"]:
            files.append({"path": str(session / a["folder"] / f["file"]),
                          "size_bytes": f["size_bytes"], "sha256": f["sha256"],
                          "exif_datetime": f.get("exif", {}).get("datetime_original")})
        shots.append({"session": session.name + "/" + a["phase"], "shot": a["number"],
                      "focal_mm": a["focal_mm"], "files": files})
    return {"status": "PASS" if shots else "EMPTY", "shots": shots,
            "scope": "validated_downloaded_pairs_only; not_an_acquisition_PASS"}


def run(args):
    space_guard(args.shots * len(modes(args.mode)))
    locks = []
    camera = uvc = ble = monitor = None
    try:
        lock_paths = [af.BASE / "tools/sony-af-prototype/camera.lock"]
        if args.mode != "fixed":
            lock_paths.append(af.BASE / "tools/streamdeck-eval/sony-ble-one-shot.lock")
        for path in lock_paths:
            handle = path.open("a")
            locks.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        session = af.create_session(af.BASE / "vision/sessions" / ("sony-stability-" + stamp))
        report = {"schema": 1, "test": "SONY_STABILITY", "status": "FAIL",
                  "capture_status": "FAIL", "sd_comparison": "PENDING",
                  "session": session.name, "utc_start": stamp, "mode": args.mode,
                  "shots_per_mode": args.shots, "planned_shots": args.shots * len(modes(args.mode)),
                  "attempts": [], "zoom_pulses": [], "automatic_shutter_retries": 0,
                  "interval_after_pair_s": args.interval, "pulse_s": args.pulse,
                  "zoom_settle_s": args.settle, "af_timeout_s": args.af_timeout,
                  "uvc_gap_limit_s": args.uvc_gap_limit, "uvc_frame_limit": 0,
                  "raw_full_decode": "NOT_TESTED", "optical_pcb_qc": "NOT_TESTED",
                  "ptp_debug_enabled": False,
                  "source_sha256": {p.name: sd.sha_file(p) for p in
                       [Path(__file__), Path(af.__file__), Path(zoom.__file__), Path(sd.__file__)]}}
        old_signals = {s: signal.signal(s, zoom.interrupted) for s in (signal.SIGINT, signal.SIGTERM)}
        start = time.monotonic()
        try:
            if args.mode != "fixed":
                ble = zoom.BLE()
            camera = af.Shell(session, args.gphoto, args.library_dir, af.detect_port(), debug=False)
            if not re.search(r"Model:\s*ILCE-6100A\b", camera.command("summary")):
                raise af.GateError("MODEL_GATE")
            report["config"] = config_gate(camera)
            uvc = af.UVC(session, camera.env, frame_count=0)
            if not uvc.ready.wait(25):
                raise af.GateError("UVC_WARMUP_TIMEOUT")
            monitor = Monitor(uvc, ble, args.uvc_gap_limit)
            monitor.gate()
            execute_series(camera, monitor, ble, args, session, report)
            monitor.gate()
            report["capture_status"] = "PASS"
        except BaseException as error:
            report["error_type"] = type(error).__name__
            report["error"] = str(error) if isinstance(error, af.GateError) else "SEE_PRIVATE_LOG"
            try:
                af.nvme_guard()
                (session / "error-private.log").write_text(repr(error) + "\n")
            except Exception:
                pass  # Storage guard failure must not cause eMMC fallback writes.
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
                try:
                    camera.close()
                except Exception:
                    report["ptp_close_failed"] = True
                    report["capture_status"] = "FAIL"
            if uvc is not None:
                try:
                    if monitor is not None:
                        monitor.gate()
                    report["uvc_final_gate"] = "PASS"
                except Exception:
                    report["uvc_final_gate"] = "FAIL"
                    report["capture_status"] = "FAIL"
                try:
                    uvc.close()
                except Exception:
                    report["uvc_close_failed"] = True
                    report["capture_status"] = "FAIL"
                if monitor is not None:
                    try:
                        monitor.observe()
                    except Exception:
                        report["capture_status"] = "FAIL"
                report["uvc"] = uvc.report()
                report["uvc"]["post_ready_max_receive_gap_s"] = monitor.max_gap if monitor else None
                report["uvc"]["post_ready_test_pattern_checks"] = (
                    uvc.pattern_checks - monitor.pattern_baseline if monitor else None)
                if uvc.errors:
                    report["capture_status"] = "FAIL"
            if ble is not None:
                try:
                    ble.gate()
                    report["ble_postflight"] = "PASS"
                except Exception:
                    report["ble_postflight"] = "FAIL"
                    report["capture_status"] = "FAIL"
                try:
                    ble.close()
                except Exception:
                    report["ble_close_failed"] = True
                    report["capture_status"] = "FAIL"
            if not report.get("ptp_release_ack", False):
                report["capture_status"] = "FAIL"
            report["full_press_requests"] = sum(a["full_press_requests"] for a in report["attempts"])
            report["verified_shots"] = sum(a["status"] == "PASS" for a in report["attempts"])
            if report["verified_shots"] != report["planned_shots"]:
                report["capture_status"] = "FAIL"
            report["status"] = "PENDING_SD" if report["capture_status"] == "PASS" else "FAIL"
            report["elapsed_s"] = round(time.monotonic() - start, 6)
            report["utc_end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            try:
                af.write_json(session / "result.json", report)
                af.write_json(session / "ptp-manifest-private.json", make_manifest(session, report))
                if uvc is not None:
                    af.write_json(session / "uvc-frames.json", uvc.rows)
            finally:
                for s, handler in old_signals.items():
                    signal.signal(s, handler)
        print("RESULT " + str(session / "result.json"), flush=True)
        print("CAPTURE " + report["capture_status"] + "; FINAL " + report["status"], flush=True)
        return 0 if report["capture_status"] == "PASS" else 1
    finally:
        for handle in reversed(locks):
            handle.close()


def distribution(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and math.isfinite(v))
    if not values:
        return None
    return {"n": len(values), "min_s": min(values), "median_s": statistics.median(values),
            "p95_s": values[math.ceil(.95 * len(values)) - 1], "max_s": max(values)}


def assessment(capture, comparison=None, imported=None):
    phases = {}
    for phase in modes(capture["mode"]):
        rows = [a for a in capture["attempts"] if a["phase"] == phase]
        phases[phase] = {"planned": capture["shots_per_mode"], "attempts": len(rows),
                         "full_press_requests": sum(a["full_press_requests"] for a in rows),
                         "passed": sum(a["status"] == "PASS" for a in rows),
                         "af": distribution([a.get("af_confirmation_s") for a in rows]),
                         "pair": distribution([a.get("complete_pair_s") for a in rows]),
                         "uvc": capture.get("phase_uvc", {}).get(phase),
                         "early_10_pairs": distribution([a.get("complete_pair_s") for a in rows[:10]]),
                         "late_10_pairs": distribution([a.get("complete_pair_s") for a in rows[-10:]]) if len(rows) >= 20 else None}
    pulses = capture.get("zoom_pulses", [])
    expected_pulses = capture["shots_per_mode"] - 1 if capture["mode"] != "fixed" else 0
    captured = (capture["capture_status"] == "PASS" and capture.get("ptp_release_ack") is True
                and capture.get("uvc_final_gate") == "PASS"
                and capture.get("automatic_shutter_retries") == 0
                and len(pulses) == expected_pulses and all(p["status"] == "PASS" for p in pulses)
                and all(p["passed"] == p["planned"] == p["full_press_requests"] for p in phases.values()))
    expected_keys = {(capture["session"] + "/" + a["phase"], a["number"])
                     for a in capture["attempts"] if a["status"] == "PASS"}
    sd_keys = [(r["session"], r["shot"]) for r in comparison["shots"]] if comparison else []
    sd_pass = (comparison is not None and comparison["status"] == "PASS"
               and comparison["verified_pairs"] == capture["planned_shots"]
               and len(sd_keys) == len(set(sd_keys)) == capture["planned_shots"]
               and set(sd_keys) == expected_keys and all(r["status"] == "PASS" for r in comparison["shots"]))
    import_pass = (imported is not None and imported.get("status", "PASS") == "PASS"
                   and imported.get("verified_files") == 2 * capture["planned_shots"]
                   and imported.get("reverification") == "PASS")
    warnings = []
    same = capture.get("uvc", {}).get("longest_identical_run_after_3s")
    if same and same["span_s"] > 2:
        warnings.append("IDENTICAL_UVC_PAYLOAD_OVER_2S_REVIEW; static_scene_can_also_cause_this")
    state = "FAIL" if not captured else "PENDING_SD"
    if comparison is not None:
        state = "PASS" if captured and sd_pass and import_pass else "FAIL"
    return {"schema": 1, "status": state, "session": capture["session"], "phases": phases,
            "capture_status": "PASS" if captured else "FAIL", "sd_status": comparison["status"] if comparison else "PENDING",
            "sd_counts": {k: comparison[k] for k in ("verified_pairs", "raw_exact_files", "jpeg_exact_files", "jpeg_zero_padding_only")} if comparison else None,
            "import": imported, "uvc": capture.get("uvc"), "warnings": warnings,
            "scope": "acquisition_transport_stability_only; not_full_production_qualification",
            "optical_pcb_qc": "NOT_TESTED", "raw_full_decode": "NOT_TESTED",
            "sensor_to_screen_latency": "NOT_MEASURED", "scene_freshness": "NOT_PROVEN",
            "phase_order": modes(capture["mode"]), "causal_zoom_latency_effect": "NOT_ESTABLISHED"}


def assess(session):
    session = session_guard(session)
    capture = json.loads((session / "result.json").read_text())
    comparison = json.loads((session / "sd-comparison.json").read_text()) if (session / "sd-comparison.json").exists() else None
    imported = json.loads((session / "sd-import.json").read_text()) if (session / "sd-import.json").exists() else None
    if imported is not None:
        imported["reverification"] = "PASS"
        entries = imported.get("files", [])
        if len(entries) != imported.get("verified_files") or len({f["file"] for f in entries}) != len(entries):
            imported["reverification"] = "FAIL"
        for f in entries:
            path = (session / "sd-originals" / f["file"]).resolve()
            if (not path.is_relative_to((session / "sd-originals").resolve())
                    or not path.is_file() or path.stat().st_size != f["bytes"] or sd.sha_file(path) != f["sha256"]):
                imported["reverification"] = "FAIL"
    # An offline reassessment also rejects PTP files changed since comparison.
    for a in capture["attempts"]:
        for f in a.get("files", []):
            path = (session / a["folder"] / f["file"]).resolve()
            if (not path.is_relative_to(session) or not path.is_file()
                    or path.stat().st_size != f["size_bytes"] or sd.sha_file(path) != f["sha256"]):
                capture["capture_status"] = "FAIL"
    result = assessment(capture, comparison, imported)
    af.write_json(session / "assessment.json", result)
    text = "# Sony — ocena stabilności\n\nStatus: **%s**. Sesja: %s.\n\n" % (result["status"], result["session"])
    text += "| Tryb | Plan | Zaliczone | Żądania migawki | AF mediana / p95, s | Para mediana / p95, s |\n|---|---|---|---|---|---|\n"
    for name, phase in result["phases"].items():
        def timing(key):
            value = phase[key]
            return "brak" if value is None else "%.3f / %.3f" % (value["median_s"], value["p95_s"])
        text += "| %s | %s | %s | %s | %s | %s |\n" % (name, phase["planned"], phase["passed"], phase["full_press_requests"], timing("af"), timing("pair"))
    text += "\nPorównanie SD: **%s**. Zweryfikowane kopie SD: %s.\n\n" % (result["sd_status"], imported.get("verified_files") if imported else "brak")
    text += "## Podgląd UVC\n\n```json\n%s\n```\n\n" % json.dumps(result["uvc"], indent=2)
    text += "Uwagi: %s\n\n" % ("; ".join(result["warnings"]) or "brak ostrzeżeń progowych")
    text += ("PASS dotyczy akwizycji i integralności transferu w tej serii. Pełne dekodowanie RAW, "
             "optyczne QC PCB, świeżość każdej klatki i opóźnienie sensor→ekran pozostają niezweryfikowane. "
             "Kolejność fixed→zoom nie izoluje wpływu zoomu od rozgrzania/baterii. "
             "Ocena człowieka powinna uwzględnić te granice i zapisane próbki UVC.\n")
    af.nvme_guard()
    (session / "REPORT.md").write_text(text)
    print("ASSESSMENT " + result["status"] + " " + str(session / "REPORT.md"), flush=True)
    return 0 if result["status"] == "PASS" else 2 if result["status"] == "PENDING_SD" else 1


def compare(session, sdroot):
    session = session_guard(session)
    manifest = session / "ptp-manifest-private.json"
    source = json.loads(manifest.read_text())
    count = len(source["shots"])
    if not count:
        raise af.GateError("NO_DOWNLOADED_PAIRS_TO_COMPARE")
    sdroot = sdroot.resolve(strict=True)
    sd.sd_guard(sdroot)
    space_guard(count)
    # Comparator rechecks readonly Sony identity and PTP checksums per pair.
    output = session / "sd-comparison.json"
    if output.exists() or (session / "sd-originals").exists():
        raise af.GateError("COMPARISON_OR_IMPORT_ALREADY_EXISTS_NO_OVERWRITE")
    try:
        sd.compare(manifest, sdroot, output, expected_pairs=count)
    except Exception as error:
        failure = {"status": "FAIL", "verified_pairs": 0, "raw_exact_files": 0,
                   "jpeg_exact_files": 0, "jpeg_zero_padding_only": 0, "shots": [],
                   "error_type": type(error).__name__, "error": "COMPARISON_ABORTED"}
        if not output.exists():
            af.write_json(output, failure)
        print("SD_COMPARISON_ABORTED_NO_SHUTTER", flush=True)
        return assess(session)
    result = json.loads((session / "sd-comparison.json").read_text())
    dest = session / "sd-originals"
    dest.mkdir(exist_ok=False)
    copied = []
    import_error = None
    try:
        for row in result["shots"]:
            if "sd_stem" not in row:
                continue
            for ext in (".arw", ".jpg"):
                sd.sd_guard(sdroot)
                af.nvme_guard()
                candidates = [p for p in (sdroot / "DCIM").rglob("*") if p.is_file()
                              and p.stem == row["sd_stem"] and p.suffix.lower() == ext]
                if len(candidates) != 1:
                    raise af.GateError("SD_IMPORT_NAME_NOT_UNIQUE")
                path = candidates[0]
                expected = row["raw" if ext == ".arw" else "jpeg"]["sd_sha256"]
                target = dest / path.name
                with path.open("rb") as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                if sd.sha_file(target) != expected:
                    raise af.GateError("SD_IMPORT_SHA_MISMATCH")
                copied.append({"file": target.name, "sha256": expected, "bytes": target.stat().st_size})
    except Exception as error:
        import_error = type(error).__name__
        print("SD_IMPORT_ABORTED_NO_SHUTTER", flush=True)
    finally:
        af.write_json(session / "sd-import.json", {
            "status": "PASS" if import_error is None and len(copied) == 2 * count else "FAIL",
            "error_type": import_error, "verified_files": len(copied), "files": copied})
    return assess(session)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Explicitly start hardware acquisition")
    run_parser.add_argument("--mode", choices=("fixed", "zoom", "both"), default="both")
    run_parser.add_argument("--shots", type=int, choices=(50, 100), default=50, help="Photos PER mode")
    run_parser.add_argument("--interval", type=float, default=10)
    run_parser.add_argument("--pulse", type=float, default=.65)
    run_parser.add_argument("--settle", type=float, default=1)
    run_parser.add_argument("--af-timeout", type=float, default=8)
    run_parser.add_argument("--uvc-gap-limit", type=float, default=1)
    run_parser.add_argument("--gphoto", default=str(af.BASE / "tools/sony-a6100-verify/root/usr/bin/gphoto2"))
    run_parser.add_argument("--library-dir", default=str(af.BASE / "tools/sony-a6100-verify/root/usr/lib/aarch64-linux-gnu"))
    compare_parser = commands.add_parser("compare", help="Compare operator-mounted readonly SD and import originals")
    compare_parser.add_argument("--session", type=Path, required=True)
    compare_parser.add_argument("--sd-root", type=Path, required=True)
    assess_parser = commands.add_parser("assess", help="Assess existing results without opening camera")
    assess_parser.add_argument("--session", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        if (not all(math.isfinite(v) for v in (args.interval, args.pulse, args.settle, args.af_timeout, args.uvc_gap_limit))
                or not 10 <= args.interval <= 60 or not 0 < args.pulse <= 1
                or not 1 <= args.settle <= 5 or not 0 < args.af_timeout <= 15
                or not .1 <= args.uvc_gap_limit <= 1):
            parser.error("interval [10,60], pulse (0,1], settle [1,5], AF (0,15], UVC gap [.1,1]; finite")
        return run(args)
    if args.command == "compare":
        return compare(args.session, args.sd_root)
    return assess(args.session)


if __name__ == "__main__":
    raise SystemExit(main())
