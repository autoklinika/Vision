#!/usr/bin/env python3
"""Vision Station Calibration V1: prepare and freeze immutable profiles. No ROS/CAN control."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "vision_station_v1"
EXPECTED = {"C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"}

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def files_under(path):
    return sorted(p for p in path.rglob("*") if p.is_file() and p.name != "manifest.json")

def load_yaml(p):
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)

def prepare(args):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{4,79}", args.session):
        raise ValueError("Session ID requires 5-80 safe characters")
    path = Path(args.storage).resolve() / "sessions" / args.session
    if path.exists():
        raise FileExistsError("Session exists: never overwrite raw measurements")
    path.mkdir(parents=True)
    (path / "captures" / "charuco").mkdir(parents=True)
    (path / "captures" / "depth").mkdir(parents=True)
    (path / "validation").mkdir()
    for src, dst in [("session_template.yaml", "session.yaml"),
                     ("source_register.yaml", "sources.yaml"),
                     ("measurements_template.csv", "measurements.csv"),
                     ("obstacles_template.yaml", "obstacles.yaml"),
                     ("approval_template.yaml", "approval.yaml")]:
        shutil.copyfile(CONFIG / src, path / dst)
    session = load_yaml(path / "session.yaml")
    session["session_id"] = args.session
    session["date_local"] = dt.datetime.now().astimezone().isoformat()
    (path / "session.yaml").write_text(yaml.safe_dump(session, allow_unicode=True, sort_keys=False))
    print(json.dumps({"status": "CAPTURE_READY", "session": str(path)}, ensure_ascii=False))

def check(args):
    path = Path(args.session_dir).resolve()
    errors = []
    if not path.is_dir():
        raise FileNotFoundError(path)
    must = ["session.yaml", "sources.yaml", "measurements.csv", "obstacles.yaml", "approval.yaml",
            "validation/report.json"]
    for name in must:
        if not (path / name).is_file():
            errors.append("Missing " + name)
    if errors:
        return errors
    ses = load_yaml(path / "session.yaml")
    approval = load_yaml(path / "approval.yaml")
    for key in ("session_id", "date_local", "operator"):
        if not ses.get(key):
            errors.append("session.yaml: missing " + key)
    if ses.get("status") != "VALIDATED":
        errors.append("session.status must be VALIDATED")
    if not ses.get("hardware", {}).get("camera_fixed_during_session"):
        errors.append("camera fixation not confirmed")
    if not ses.get("hardware", {}).get("camera_settings_id"):
        errors.append("missing camera configuration ID")
    for key, value in ses.get("acceptance_thresholds", {}).items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append("missing positive acceptance threshold: " + key)
    for key in ("length_instrument", "height_instrument"):
        if not ses.get("instruments", {}).get(key):
            errors.append("missing instrument: " + key)
    for key in ("actual_grid_long_mm", "actual_grid_short_mm", "dictionary"):
        if not ses.get("charuco", {}).get(key):
            errors.append("missing charuco input: " + key)
    with (path / "measurements.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    stages = {r.get("stage", "").split("-")[0] for r in rows if r.get("reading")}
    for stage in EXPECTED:
        if stage not in stages:
            errors.append("No recorded measured evidence for " + stage)
    report = json.loads((path / "validation" / "report.json").read_text())
    if report.get("status") != "PASS":
        errors.append("validation report not PASS")
    for group in ("tf", "camera", "depth", "tool", "moveit_offline"):
        if report.get("checks", {}).get(group) != "PASS":
            errors.append("validation check not PASS: " + group)
    if not report.get("independent_control_points"):
        errors.append("no independent control points")
    if approval.get("status") != "APPROVED" or not approval.get("reviewer"):
        errors.append("explicit operator approval missing")
    if approval.get("session_id") != ses.get("session_id"):
        errors.append("approval session ID mismatch")
    return errors

def freeze(args):
    session = Path(args.session_dir).resolve()
    issues = check(args)
    if issues:
        print(json.dumps({"status": "REJECTED", "issues": issues}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    release = Path(args.storage).resolve() / "approved" / session.name
    if release.exists():
        raise FileExistsError("Approved profile already exists; immutable by policy")
    staging = release.parent / (".pending-" + session.name)
    if staging.exists():
        raise FileExistsError("Unexpected pending release; investigate")
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(session, staging)
        src_files = files_under(staging)
        manifest = {
            "profile_id": "vision-station-v1",
            "session_id": session.name,
            "status": "APPROVED_SNAPSHOT",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "artifact_count": len(src_files),
            "sha256": {str(p.relative_to(staging)): sha(p) for p in src_files},
            "manual_activation_required": True,
            "robot_motion_permitted_by_this_tool": False,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        staging.rename(release)
        for directory, dirs, names in os.walk(release):
            for name in names:
                os.chmod(Path(directory) / name, 0o444)
            os.chmod(directory, 0o555)
        print(json.dumps({"status": "APPROVED_SNAPSHOT_CREATED", "path": str(release), "files": len(src_files)}))
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

def verify(args):
    path = Path(args.approved_dir).resolve()
    manifest = json.loads((path / "manifest.json").read_text())
    expected = manifest["sha256"]
    actual_files = {str(p.relative_to(path)): sha(p) for p in files_under(path)}
    issues = []
    for k, v in expected.items():
        if actual_files.get(k) != v:
            issues.append("MISMATCH_OR_MISSING: " + k)
    for k in actual_files.keys() - expected.keys():
        issues.append("EXTRA: " + k)
    print(json.dumps({"status": "PASS" if not issues else "FAIL", "artifact_count": len(expected),
                      "issues": issues}, ensure_ascii=False))
    if issues:
        raise SystemExit(2)

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--session", required=True)
    p.add_argument("--storage", default="/srv/vision-data/calibration")
    p.set_defaults(func=prepare)
    p = sub.add_parser("check")
    p.add_argument("--session-dir", required=True)
    p.set_defaults(func=lambda a: print(json.dumps({"issues": check(a)}, ensure_ascii=False)))
    p = sub.add_parser("freeze")
    p.add_argument("--session-dir", required=True)
    p.add_argument("--storage", default="/srv/vision-data/calibration")
    p.set_defaults(func=freeze)
    p = sub.add_parser("verify")
    p.add_argument("--approved-dir", required=True)
    p.set_defaults(func=verify)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
