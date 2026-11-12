"""Hardware-independent 3D scene interpretation from camera.frame_bundle.v1.

No DepthAI, USB, neural networks, motion interfaces, or safety function.
All XYZ values use the stereo-left camera optical frame, in meters.
"""
from __future__ import annotations

import math
import numpy as np
import cv2

SCHEMA = "perception.scene_observation.v1"
FRAME = "stereo_left_rectified_optical"


def deproject_depth(depth_mm: np.ndarray, k: np.ndarray, stride: int = 4):
    """Return sampled XYZ points [m], pixel coordinates and valid fraction."""
    if depth_mm.dtype != np.uint16 or depth_mm.ndim != 2:
        raise ValueError("depth must be 2D uint16 mm")
    k = np.asarray(k, dtype=np.float64)
    if (k.shape != (3, 3) or not np.all(np.isfinite(k)) or
            k[0, 0] <= 0 or k[1, 1] <= 0 or not 1 <= stride <= 32):
        raise ValueError("invalid camera intrinsics or stride")
    h, w = depth_mm.shape
    v, u = np.mgrid[0:h:stride, 0:w:stride]
    z = depth_mm[::stride, ::stride].astype(np.float64) / 1000
    valid = (z > 0) & np.isfinite(z)
    xyz = np.column_stack((
        (u[valid] - k[0, 2]) * z[valid] / k[0, 0],
        (v[valid] - k[1, 2]) * z[valid] / k[1, 1],
        z[valid],
    ))
    uv = np.column_stack((u[valid], v[valid]))
    return xyz, uv, float(valid.mean())


def fit_plane(points: np.ndarray, threshold_m: float = 0.012,
              iterations: int = 100, min_fraction: float = 0.30):
    """Deterministic RANSAC + PCA refinement; returned normal faces the camera."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 40:
        return None
    rng = np.random.default_rng(12)
    sample = pts[rng.choice(len(pts), min(len(pts), 6000), replace=False)]
    best_mask = None
    best_count = 0
    for _ in range(iterations):
        tri = sample[rng.choice(len(sample), 3, replace=False)]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        length = np.linalg.norm(normal)
        if length < 1e-9:
            continue
        normal /= length
        dist = np.abs((sample - tri[0]) @ normal)
        mask = dist <= threshold_m
        n = int(mask.sum())
        if n > best_count:
            best_count, best_mask = n, mask
    if best_mask is None or best_count < len(sample) * min_fraction:
        return None
    inliers = sample[best_mask]
    center = inliers.mean(axis=0)
    _, _, axes = np.linalg.svd(inliers - center, full_matrices=False)
    normal = axes[-1]
    if normal[2] > 0:
        normal = -normal
    offset = -float(normal @ center)
    all_res = np.abs(pts @ normal + offset)
    accepted = all_res <= threshold_m
    if accepted.mean() < min_fraction:
        return None
    return {
        "normal": normal.tolist(),
        "offset_m": offset,
        "inlier_fraction": float(accepted.mean()),
        "inlier_count": int(accepted.sum()),
        "residual_rmse_m": float(np.sqrt(np.mean(all_res[accepted] ** 2))),
        "frame_of_reference": FRAME,
    }


def find_objects(depth_mm: np.ndarray, k: np.ndarray, plane: dict,
                 step: int = 4, min_height_m: float = .025,
                 min_area_pixels: int = 35, max_objects: int = 8):
    """Classical depth protrusions above the dominant plane, no ECU label claim."""
    sub = depth_mm[::step, ::step].astype(np.float64) / 1000
    h, w = sub.shape
    v, u = np.mgrid[0:depth_mm.shape[0]:step, 0:depth_mm.shape[1]:step]
    xyz = np.stack(((u-k[0, 2])*sub/k[0, 0],
                    (v-k[1, 2])*sub/k[1, 1], sub), axis=-1)
    normal = np.asarray(plane["normal"])
    signed_distance = xyz @ normal + plane["offset_m"]
    mask = ((sub > 0) & (signed_distance > min_height_m)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    objects = []
    candidates = sorted(range(1, count),
                        key=lambda i: stats[i, cv2.CC_STAT_AREA], reverse=True)
    for index in candidates:
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < min_area_pixels or len(objects) >= max_objects:
            continue
        coords = xyz[labels == index]
        coords = coords[np.isfinite(coords).all(axis=1)]
        if len(coords) < 3:
            continue
        center = np.median(coords, axis=0)
        mins, maxs = np.quantile(coords, [0.05, 0.95], axis=0)
        xy = coords[:, :2] - coords[:, :2].mean(axis=0)
        covariance = xy.T @ xy / len(xy)
        eigval, eigvec = np.linalg.eigh(covariance)
        principal = eigvec[:, int(np.argmax(eigval))]
        yaw = float(math.atan2(principal[1], principal[0]))
        objects.append({
            "object_id": "geometry_" + str(index),
            "class": "unknown_object",
            "candidate_ecu": "UNCONFIRMED",
            "position_camera_m": center.round(5).tolist(),
            "size_visible_aabb_m": (maxs - mins).round(5).tolist(),
            "yaw_camera_rad": round(yaw, 5),
            "orientation_quality": "IN_PLANE_AXIS_ONLY_180_DEG_AMBIGUITY",
            "pixel_area_sampled": area,
            "frame_of_reference": FRAME,
            "uncertainty": {
                "status": "NOT_METROLOGICALLY_VALIDATED",
                "plane_residual_rmse_m": plane["residual_rmse_m"],
            },
        })
    return objects


def scene_change(current_mm: np.ndarray, previous_mm: np.ndarray | None,
                 min_change_mm: int = 25):
    """Non-safety depth difference; caller must guarantee fixed camera pose."""
    if previous_mm is None or previous_mm.shape != current_mm.shape:
        return {"state": "BASELINE_UNAVAILABLE", "changed_fraction": None}
    common = (previous_mm > 0) & (current_mm > 0)
    if not common.any():
        return {"state": "INSUFFICIENT_VALID_DEPTH", "changed_fraction": None}
    diff = np.abs(current_mm.astype(np.int32) -
                  previous_mm.astype(np.int32))
    changed = float(np.count_nonzero((diff > min_change_mm) & common) /
                    np.count_nonzero(common))
    return {"state": "MEASURED_NON_SAFETY", "changed_fraction": round(changed, 6),
            "threshold_mm": min_change_mm}


def observe_scene(frame_bundle: dict, depth_mm: np.ndarray,
                  previous_depth_mm: np.ndarray | None = None,
                  replay: bool = False, stride: int = 4) -> dict:
    """Versioned scene observation, refusing invalid or unsynchronized frames."""
    base = {
        "schema_version": SCHEMA,
        "source_bundle_id": frame_bundle.get("bundle_id"),
        "source_frame_ids": {
            "rgb": frame_bundle.get("rgb", {}).get("frame_id"),
            "depth": frame_bundle.get("depth", {}).get("frame_id"),
        },
        "camera_session_id": frame_bundle.get("session_id"),
        "source_timestamps": frame_bundle.get("device_timestamp"),
        "source_host_timestamps": frame_bundle.get("host_timestamp"),
        "source_capture_age_ms": frame_bundle.get("capture_age_ms"),
        "age_basis": frame_bundle.get("age_basis"),
        "calibration_revision": frame_bundle.get("calibration_revision"),
        "frame_of_reference": FRAME,
        "units": {"position": "m", "angle": "rad"},
        "table_frame": {"status": "UNAVAILABLE"},
        "robot_base_frame": {"status": "UNAVAILABLE"},
        "safety_function": False,
        "objects": [],
        "plane": None,
        "change": {"state": "NOT_READY"},
        "validity": "NOT_READY",
        "reasons": [],
        "quality": {"point_count": 0, "valid_depth_fraction_sampled": None,
                    "uncertainty_status": "NOT_METROLOGICALLY_VALIDATED"},
    }
    if (frame_bundle.get("schema_version") != "camera.frame_bundle.v1"
            or frame_bundle.get("sync_state") != "SYNCED"
            or frame_bundle.get("depth", {}).get("coordinate_frame") != FRAME):
        base["reasons"].append("INVALID_CAMERA_FRAME_BUNDLE")
        return base
    if not replay and frame_bundle.get("capture_age_ms", 1e9) > 300:
        base["reasons"].append("STALE_FRAME_BUNDLE")
        return base
    h, w = depth_mm.shape
    if (depth_mm.dtype != np.uint16 or
            frame_bundle["depth"]["resolution"] != [w, h]):
        base["reasons"].append("INVALID_DEPTH_LAYOUT")
        return base
    cal = frame_bundle.get("calibration", {})
    k_data = cal.get("intrinsics", {}).get("stereo_left_rectified_optical")
    verified = k_data is not None
    if k_data is None:
        k_data = cal.get("intrinsics", {}).get("stereo_left_raw_optical")
    if not k_data:
        base["reasons"].append("MISSING_DEPTH_INTRINSICS")
        return base
    k = np.asarray(k_data["K"], dtype=np.float64)
    if k_data.get("resolution") != [w, h]:
        base["reasons"].append("DEPTH_INTRINSICS_RESOLUTION_MISMATCH")
        return base
    try:
        pts, _, valid_fraction = deproject_depth(depth_mm, k, stride)
    except ValueError:
        base["reasons"].append("INVALID_INTRINSICS")
        return base
    base["quality"] = {
        "valid_depth_fraction_sampled": round(valid_fraction, 5),
        "point_count": len(pts),
        "uncertainty_status": "NOT_METROLOGICALLY_VALIDATED",
        "reprojection_intrinsics": "RECTIFIED_VERIFIED" if verified
            else "RAW_LEFT_EXPLORATORY_NOT_RECTIFIED_VERIFIED",
    }
    plane = fit_plane(pts)
    base["plane"] = plane
    base["change"] = scene_change(depth_mm, previous_depth_mm)
    if plane is None:
        base["reasons"].append("NO_RELIABLE_PLANE")
        return base
    base["objects"] = find_objects(depth_mm, k, plane, step=stride)
    base["validity"] = ("CAMERA_FRAME_ONLY" if verified
                        else "EXPLORATORY_UNVERIFIED_PROJECTION")
    base["reasons"].append("TABLE_AND_ROBOT_TRANSFORMS_UNAVAILABLE")
    if not verified:
        base["reasons"].append("RECTIFIED_DEPTH_INTRINSICS_NOT_VERIFIED")
    return base
