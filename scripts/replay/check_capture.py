#!/usr/bin/env python3
"""Offline-only verification of a frozen Vision RGB-D/RAW16 capture (.npz).

No ROS, camera SDK, USB, network, robot, or actuator imports. Validates metadata
and binary evidence; it does not infer camera-to-robot extrinsics or certify depth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

SCHEMA = "vision.capture-baseline.v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_CAPTURE_BYTES = 1_000_000_000  # Stop accidentally unpacking huge experiments.


def _number(value: object) -> bool:
    return type(value) in (int, float) and np.isfinite(value)


def _validate_manifest(doc: object) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return {}, ["MANIFEST_NOT_OBJECT"]
    if doc.get("schema_version") != SCHEMA:
        errors.append("SCHEMA_VERSION_UNSUPPORTED")
    if not isinstance(doc.get("session_id"), str) or not doc["session_id"].strip():
        errors.append("SESSION_ID_REQUIRED")
    capture = doc.get("capture")
    if not isinstance(capture, dict):
        return {}, errors + ["CAPTURE_SECTION_REQUIRED"]
    rel = capture.get("file")
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or Path(rel).suffix != ".npz":
        errors.append("CAPTURE_PATH_UNSAFE_OR_INVALID")
    digest = capture.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        errors.append("CAPTURE_SHA256_REQUIRED")
    if capture.get("format") != "npz-raw16-v1":
        errors.append("CAPTURE_FORMAT_UNSUPPORTED")
    expected = doc.get("expected")
    if not isinstance(expected, dict):
        return {}, errors + ["EXPECTED_SECTION_REQUIRED"]
    frames = expected.get("frames")
    if type(frames) is not int or not (1 <= frames <= 256):
        errors.append("EXPECTED_FRAME_COUNT_INVALID")
    size = expected.get("depth_hw")
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or not (1 <= v <= 4096) for v in size):
        errors.append("EXPECTED_DEPTH_SHAPE_INVALID")
    if expected.get("depth_dtype") != "uint16":
        errors.append("EXPECTED_DTYPE_UNSUPPORTED")
    frame_id = expected.get("declared_optical_frame")
    if not isinstance(frame_id, str) or not frame_id.strip():
        errors.append("DECLARED_OPTICAL_FRAME_REQUIRED")
    # The manifest declares a frame; NPZ alone cannot prove optical registration.
    k = expected.get("K")
    if not isinstance(k, list) or len(k) != 4 or any(not _number(v) for v in k) or (len(k) == 4 and any(v <= 0 for v in k[:2])):
        errors.append("EXPECTED_INTRINSICS_INVALID")
    eps = expected.get("K_tolerance_px", 0.2)
    if not _number(eps) or not (0 <= eps <= 3):
        errors.append("K_TOLERANCE_INVALID")
    quality = doc.get("quality")
    if not isinstance(quality, dict):
        return {}, errors + ["QUALITY_SECTION_REQUIRED"]
    depth_range = quality.get("valid_depth_mm")
    if not isinstance(depth_range, list) or len(depth_range) != 2 or any(type(v) is not int for v in depth_range) or not (0 <= depth_range[0] < depth_range[1] <= 65535):
        errors.append("VALID_DEPTH_RANGE_INVALID")
    threshold = quality.get("min_valid_fraction")
    if not _number(threshold) or not (0 <= threshold <= 1):
        errors.append("MIN_VALID_FRACTION_INVALID")
    return capture, errors


def inspect_capture(manifest_path: Path, capture_root: Path) -> dict:
    """Return structured PASS/FAIL; don't disclose local filenames or sensitive images."""
    report: dict = {"schema_version": "vision.capture-check.v1", "status": "FAIL", "errors": [], "metrics": {}}
    errors: list[str] = report["errors"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append("MANIFEST_UNREADABLE")
        return report
    capture, failures = _validate_manifest(manifest)
    errors.extend(failures)
    report["session_id"] = manifest.get("session_id") if isinstance(manifest, dict) else None
    if errors:
        return report
    root = capture_root.resolve()
    target = (root / capture["file"]).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        errors.append("CAPTURE_MISSING_OR_OUTSIDE_ROOT")
        return report
    if target.stat().st_size > MAX_CAPTURE_BYTES:
        errors.append("CAPTURE_EXCEEDS_SIZE_LIMIT")
        return report
    with target.open("rb") as stream:
        actual_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    report["metrics"]["capture_sha256"] = actual_sha
    if actual_sha != capture["sha256"]:
        errors.append("CAPTURE_HASH_MISMATCH")
        return report
    try:
        with np.load(target, allow_pickle=False) as packed:
            if "depth_mm" not in packed.files or "K" not in packed.files:
                errors.append("REQUIRED_ARRAYS_MISSING")
                return report
            depth = packed["depth_mm"]
            k = packed["K"]
            times = packed["device_timestamp_ns"] if "device_timestamp_ns" in packed.files else None
    except (OSError, ValueError, KeyError, EOFError, TypeError):
        errors.append("CAPTURE_FORMAT_CORRUPT")
        return report
    expected = manifest["expected"]
    if depth.ndim != 3 or list(depth.shape) != [expected["frames"], *expected["depth_hw"]]:
        errors.append("FRAME_COUNT_OR_RESOLUTION_REGRESSION")
    if depth.dtype != np.uint16:
        errors.append("DEPTH_DTYPE_REGRESSION")
    if k.shape != (3, 3) or not np.isfinite(k).all() or not np.allclose(k[2], [0, 0, 1], atol=1e-4):
        errors.append("INTRINSICS_MATRIX_INVALID")
    else:
        actual_k = [float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2])]
        report["metrics"]["K"] = actual_k
        if any(abs(a - b) > expected.get("K_tolerance_px", 0.2) for a, b in zip(actual_k, expected["K"])):
            errors.append("INTRINSICS_REGRESSION")
    if times is not None and (times.shape != (len(depth),) or not np.issubdtype(times.dtype, np.integer) or np.any(np.diff(times.astype(np.int64)) <= 0)):
        errors.append("TIMESTAMPS_NONMONOTONIC")
    if depth.ndim == 3 and depth.dtype == np.uint16:
        lo, hi = manifest["quality"]["valid_depth_mm"]
        frac = float(np.count_nonzero((depth >= lo) & (depth <= hi)) / depth.size)
        report["metrics"]["valid_depth_fraction"] = round(frac, 6)
        if frac < manifest["quality"]["min_valid_fraction"]:
            errors.append("DEPTH_COVERAGE_BELOW_BASELINE")
    report["metrics"]["shape"] = list(depth.shape)
    report["metrics"]["dtype"] = str(depth.dtype)
    report["metrics"]["declared_optical_frame"] = expected["declared_optical_frame"]
    # Never claim this checks pixel-to-RGB extrinsics or physical metrology.
    report["status"] = "PASS" if not errors else "FAIL"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--capture-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Optional local JSON report (keep private)")
    args = parser.parse_args(argv)
    try:
        result = inspect_capture(args.manifest, args.capture_root)
    except (OSError, ValueError, TypeError):
        result = {"schema_version": "vision.capture-check.v1", "status": "FAIL", "errors": ["UNEXPECTED_CAPTURE_IO_ERROR"], "metrics": {}}
    rendered = json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
