#!/usr/bin/env python3
"""Controlled OAK camera pilot on VENTUNO. Single USB owner; restore service.

Run in camera production venv. Reports metrics only. Never publishes photographs,
changes EEPROM, moves NERO or modifies the production service files.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
# The smoke imports Perception for replay; include its isolated script directory
# regardless of the caller's current working directory.
sys.path.insert(0, str(ROOT.parents[1] / "perception"))
VENV = Path("/srv/vision-data/tools/vision-camera-service/venv/bin/python")
ENV_FILE = Path("/srv/vision-data/tools/vision-camera-service/camera.env")
OUT_DIR = Path("/srv/vision-data/staging/oak-optics-live-20261113")
UNIT = "vision-oak-camera.service"
CANDIDATE = "http://127.0.0.1:18111"
PROFILE = {
    "survey": "balanced",
    "depth_precision": "balanced",
    "low_light": "balanced",
    "detail": "detail",
}
ABORT_CHIP_TEMP_C = 62.0

os.umask(0o077)
os.environ["XDG_RUNTIME_DIR"] = "/run/user/" + str(os.getuid())
os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + os.environ["XDG_RUNTIME_DIR"] + "/bus"


def unit(*args):
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True, timeout=30)


def local_prod_url():
    values = {}
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return "http://" + values["VISION_BIND"] + ":" + values["VISION_PORT"]


def get_json(url, timeout=3):
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def get_bytes(url, timeout=6):
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def stat_keys(status):
    return {k: status.get(k) for k in ("online", "profile", "usb", "rgb_fps",
            "depth_fps", "chip_temp_C", "rss_mb", "pilot_status", "focus_device_metadata", "optics_captured",
            "optics_errors", "depth_projection_status", "error")}


def wait_online(url, proc=None, limit_s=25):
    for _ in range(int(limit_s * 4)):
        if proc is not None and proc.poll() is not None:
            break
        try:
            s = get_json(url + "/api/status", timeout=1)
            if s.get("online") and s.get("usb") == "UsbSpeed.SUPER":
                return s
        except Exception:
            pass
        time.sleep(.25)
    return None


def safe_stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=4)


def summarize_camera(s, metadata):
    cal = metadata.get("calibration", {}) if metadata else {}
    k = cal.get("intrinsics", {})
    return {
        "rgb_transform": k.get("rgb_optical"),
        "depth_transform": k.get("stereo_left_rectified_optical"),
        "eeprom_read_state": cal.get("state"),
        "rectified_status": cal.get("depth_projection_status"),
        "table": (metadata or {}).get("transform_status", {}).get("table"),
        "robot_base": (metadata or {}).get("transform_status", {}).get("robot_base"),
        "sync": (metadata or {}).get("sync_state"),
        "delta_ms": (metadata or {}).get("pairing_delta_ms"),
    }


def sample_phase(name, run_seconds=10):
    import cv2
    import numpy as np
    from camera_sync import decode_replay_npz
    from perception_engine import observe_scene
    profile = PROFILE[name]
    logfile = OUT_DIR / ("candidate_" + name + ".log")
    cmd = [str(VENV), "-u", str(ROOT / "camera_service_prod.py"),
           "--bind", "127.0.0.1", "--port", "18111",
           "--profile", profile, "--pilot-profile", name]
    if name == "detail":
        cmd.append("--af-actuator-diagnostic")
    with logfile.open("w") as log:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True)
    phase = {"profile": name, "acquisition": profile}
    try:
        start = wait_online(CANDIDATE, proc=proc)
        phase["started"] = bool(start)
        if start is None:
            phase["failure"] = "UNAVAILABLE_OR_PIPELINE_CRASH"
            return phase
        values = []
        for _ in range(run_seconds):
            if proc.poll() is not None:
                phase["failure"] = "PROCESS_EXITED_EARLY"
                break
            s = get_json(CANDIDATE + "/api/status", timeout=3)
            values.append(s)
            if not s["online"]:
                phase["failure"] = "NOT_READY"
                break
            if (s.get("chip_temp_C") is not None
                    and s["chip_temp_C"] >= ABORT_CHIP_TEMP_C):
                phase["failure"] = "CHIP_TEMP_ABORT"
                break
            time.sleep(1)
        if values:
            phase["last"] = stat_keys(values[-1])
            phase["focus"] = values[-1].get("focus_device_metadata")
            for metric in ("rgb_fps", "depth_fps", "depth_valid_pct",
                           "chip_temp_C", "rss_mb"):
                available = [v[metric] for v in values if v.get(metric) is not None]
                phase[metric + "_median"] = (
                    round(statistics.median(available), 3) if available else None)
            phase["sync_paired"] = values[-1].get("rgbd_sync", {}).get("paired_count")
            phase["lost_sequences"] = values[-1].get("rgbd_sync", {}).get("lost_sequences")
        try:
            metadata = get_json(CANDIDATE + "/api/frame-bundle/latest", timeout=3)
            phase["optics"] = summarize_camera(values[-1] if values else start, metadata)
        except Exception as exc:
            phase["optics_error"] = type(exc).__name__
            metadata = None
        try:
            image = get_bytes(CANDIDATE +
                "/snapshot/rgb-roi.jpg?x=0.25&y=0.25&w=0.5&h=0.5", timeout=8)
            roi = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
            phase["roi"] = {"shape": list(roi.shape) if roi is not None else None,
                            "bytes": len(image)}
        except Exception as exc:
            phase["roi_error"] = type(exc).__name__
        try:
            payload = get_bytes(CANDIDATE + "/snapshot/frame-bundle.npz", timeout=9)
            meta, jpeg, depth = decode_replay_npz(payload)
            phase["replay"] = {
                "rgb_jpeg_bytes": len(jpeg), "depth_shape": list(depth.shape),
                "depth_dtype": str(depth.dtype),
                "depth_valid_pct": round(float(((depth > 0) & (depth < 5000)).mean() * 100), 3)
            }
            if name == "survey":
                scene = observe_scene(meta, depth, replay=True, stride=4)
                phase["perception"] = {
                    "state": scene["validity"],
                    "points": scene["quality"]["point_count"],
                    "planes_found": scene["plane"] is not None,
                    "plane_rmse_m": (scene["plane"]["residual_rmse_m"] if scene["plane"] else None),
                    "objects_unknown": len(scene["objects"]),
                    "robot": scene["robot_base_frame"]["status"],
                }
        except Exception as exc:
            phase["replay_error"] = type(exc).__name__
        phase["passed"] = (bool(values) and not phase.get("failure")
                           and phase.get("replay", {}).get("depth_dtype") == "uint16"
                           and phase.get("roi", {}).get("shape") is not None
                           and (values[-1].get("rgbd_sync", {}).get("paired_count") or 0) > 30
                           and phase.get("optics", {}).get("sync") == "SYNCED")
        return phase
    finally:
        safe_stop(proc)
        phase["process_exitcode"] = proc.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phases", default="survey",
                    help="Comma separated: survey,depth_precision,low_light,detail")
    args = ap.parse_args()
    phases = [x.strip() for x in args.phases.split(",")]
    if not phases or any(p not in PROFILE for p in phases):
        ap.error("invalid phases")
    OUT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    local_url = local_prod_url()
    baseline = get_json(local_url + "/api/status")
    result = {"phases_requested": phases,
              "baseline": stat_keys(baseline),
              "phases": []}
    if not baseline.get("online") or baseline.get("usb") != "UsbSpeed.SUPER":
        raise RuntimeError("production not ready; refusing to interrupt")
    if unit("is-active", UNIT).stdout.strip() != "active":
        raise RuntimeError("systemd camera not active; refusing to interrupt")
    stopped = False
    try:
        outcome = unit("stop", UNIT)
        if outcome.returncode != 0:
            raise RuntimeError("failed to stop production camera")
        stopped = True
        if unit("is-active", UNIT).stdout.strip() == "active":
            raise RuntimeError("production owner still active")
        for name in phases:
            phase = sample_phase(name)
            result["phases"].append(phase)
            if not phase.get("passed"):
                result["failure"] = "HARDWARE_PILOT_FAILED_AT_" + name
                break
    finally:
        if stopped:
            restoration = unit("start", UNIT)
            result["production_restart_command_ok"] = restoration.returncode == 0
            online = wait_online(local_url, limit_s=35)
            result["production_restored"] = bool(online)
            if online:
                result["production_after"] = stat_keys(online)
        out = OUT_DIR / ("results_" + "_".join(phases) + ".json")
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        out.chmod(0o600)
        # Never print private images/addresses or full camera metadata.
        simple = {"requested": phases,
                  "baseline": result["baseline"],
                  "production_restored": result.get("production_restored"),
                  "production_after": result.get("production_after"),
                  "phases": [{k: p.get(k) for k in
                     ("profile", "started", "passed", "failure", "rgb_fps_median",
                      "depth_fps_median", "depth_valid_pct_median", "chip_temp_C_median",
                      "sync_paired", "roi", "replay", "perception", "optics_error", "focus",
                      "lost_sequences")}
                    for p in result["phases"]]}
        print("VISION_OPTICS_SMOKE_RESULT=" + json.dumps(simple, ensure_ascii=False),
              flush=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT.parent.parent / "perception"))
    main()
