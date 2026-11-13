"""Local tabletop and object-top planar geometry in the rectified depth frame.

This module never opens a camera or communicates with a robot. Measurements are
EXPLORATORY until target geometry/intrinsics and repeatability are validated.
The top-plane estimator does not know the reference object's true height.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from perception_engine import fit_plane

SCHEMA = "perception.height_planes.v1"
FRAME = "stereo_left_rectified_optical"


def _box(box, width: int, height: int):
    if len(box) != 4 or any(not isinstance(x, (int, np.integer)) for x in box):
        raise ValueError("ROI xyxy must have four integer coordinates")
    x0, y0, x1, y1 = [int(x) for x in box]
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("ROI outside depth image")
    return x0, y0, x1, y1


def _intrinsics(K: Any) -> np.ndarray:
    K = np.asarray(K, dtype=np.float64)
    if (K.shape != (3, 3) or not np.isfinite(K).all()
            or K[0, 0] <= 0 or K[1, 1] <= 0
            or abs(K[2, 2]-1) > .001):
        raise ValueError("Invalid depth intrinsics")
    return K


def _points(x: np.ndarray, y: np.ndarray, z_m: np.ndarray,
            K: np.ndarray) -> np.ndarray:
    return np.column_stack((
        (x-K[0,2])*z_m/K[0,0],
        (y-K[1,2])*z_m/K[1,1],
        z_m,
    ))


def estimate_height_planes(
    depth_mm: np.ndarray, K: Any,
    object_roi: tuple[int, int, int, int],
    table_roi: tuple[int, int, int, int],
    *,
    table_exclusion_padding_px: int = 18,
    table_stride: int = 3,
    min_relative_height_mm: float = 25.0,
    max_relative_height_mm: float = 120.0,
    top_fraction: float = .40,
    top_max_tilt_deg: float = 14.,
    min_top_points: int = 120,
) -> dict:
    """Estimate signed separation of two fitted planes along table normal.

    The top plane may be slightly tilted. Separation is evaluated at centroid
    of fitted top inliers and expressed in the stereo-left rectified frame.
    This is not a globally defined distance between nonparallel planes.

    Mask the object from table fitting, preselect upper height candidates for
    the top face, and use a second RANSAC 3D fit. Sidewalls are rejected by the
    relative height cut and the near-parallel orientation gate.

    Output contains quality metrics, estimator definition, and conservative
    NOT_READY when geometry is unstable or ambiguous. No ground truth used.
    """
    result = {
        "schema_version": SCHEMA,
        "frame_of_reference": FRAME,
        "validity": "NOT_READY",
        "reason": None,
        "height_mm": None,
        "height_reference_status": "UNVERIFIED",
        "coordinate_frame_table": "UNAVAILABLE",
        "coordinate_frame_robot_base": "UNAVAILABLE",
        "safety_function": False,
        "table_plane": None,
        "top_plane": None,
        "quality": {},
    }
    if depth_mm.ndim != 2 or depth_mm.dtype != np.uint16:
        result["reason"] = "DEPTH_U16_REQUIRED"
        return result
    try:
        K = _intrinsics(K)
        height, width = depth_mm.shape
        ox0, oy0, ox1, oy1 = _box(object_roi, width, height)
        tx0, ty0, tx1, ty1 = _box(table_roi, width, height)
    except (ValueError, TypeError):
        result["reason"] = "INVALID_INTRINSICS_OR_ROI"
        return result
    if (table_stride < 1 or table_stride > 8 or min_top_points < 40 or
            not .15 <= top_fraction <= .75 or
            not 5 <= top_max_tilt_deg <= 35):
        result["reason"] = "INVALID_ESTIMATOR_SETTINGS"
        return result

    # Fit table from an annulus, not including the object's box or its edges.
    ty, tx = np.mgrid[ty0:ty1:table_stride, tx0:tx1:table_stride]
    table_depth = depth_mm[ty0:ty1:table_stride, tx0:tx1:table_stride]
    z_tab = table_depth.astype(np.float64)/1000
    pad = table_exclusion_padding_px
    outside = ((tx < ox0-pad) | (tx >= ox1+pad) |
               (ty < oy0-pad) | (ty >= oy1+pad))
    valid_tab = (z_tab >= .25) & (z_tab < 2.0) & outside
    table_points = _points(tx[valid_tab], ty[valid_tab], z_tab[valid_tab], K)
    if len(table_points) < 800:
        result["reason"] = "INSUFFICIENT_TABLE_POINTS"
        return result
    table = fit_plane(table_points, threshold_m=.006,
                      iterations=110, min_fraction=.55)
    if (table is None or table["residual_rmse_m"] > .005 or
            table["inlier_fraction"] < .65 or table["normal"][2] > -.85):
        result["reason"] = "TABLE_PLANE_UNRELIABLE"
        return result
    n_tab = np.asarray(table["normal"], dtype=np.float64)
    n_tab /= np.linalg.norm(n_tab)
    result["table_plane"] = table
    result["quality"]["table_points"] = len(table_points)
    result["quality"]["table_rmse_mm"] = round(table["residual_rmse_m"]*1000,3)

    oy, ox = np.mgrid[oy0:oy1, ox0:ox1]
    region = depth_mm[oy0:oy1, ox0:ox1]
    z_obj = region.astype(np.float64)/1000
    valid_obj = (z_obj >= .25) & (z_obj < 2.0)
    obj_points = _points(ox[valid_obj], oy[valid_obj], z_obj[valid_obj], K)
    if not len(obj_points):
        result["reason"] = "OBJECT_DEPTH_UNAVAILABLE"
        return result
    signed_heights = (obj_points @ n_tab + table["offset_m"])*1000
    height_candidates = (
        (signed_heights >= min_relative_height_mm) &
        (signed_heights <= max_relative_height_mm)
    )
    candidates = obj_points[height_candidates]
    heights = signed_heights[height_candidates]
    result["quality"]["object_roi_valid_pct"] = round(float(valid_obj.mean()*100),3)
    result["quality"]["object_above_table_count"] = int(len(candidates))
    if len(candidates) < min_top_points:
        result["reason"] = "INSUFFICIENT_OBJECT_ABOVE_TABLE"
        return result

    # Fixed upper band, independent of known reference height.
    cutoff_mm = float(np.quantile(heights, 1-top_fraction))
    upper_mask = heights >= cutoff_mm
    upper_points = candidates[upper_mask]
    result["quality"]["top_candidate_cutoff_mm"] = round(cutoff_mm,3)
    result["quality"]["top_candidate_points"] = int(len(upper_points))
    if len(upper_points) < min_top_points:
        result["reason"] = "INSUFFICIENT_TOP_CANDIDATES"
        return result

    top = fit_plane(upper_points, threshold_m=.004,
                    iterations=125, min_fraction=.45)
    if top is None:
        result["reason"] = "TOP_PLANE_UNRELIABLE"
        return result
    n_top = np.asarray(top["normal"],dtype=np.float64)
    n_top /= np.linalg.norm(n_top)
    # fit_plane orients normal to -Z, same as camera-facing table normal.
    dot = float(np.clip(n_top @ n_tab, -1, 1))
    tilt = math.degrees(math.acos(dot))
    result["quality"]["top_table_normal_angle_deg"] = round(tilt,3)
    result["quality"]["top_rmse_mm"] = round(top["residual_rmse_m"]*1000,3)
    result["quality"]["top_inlier_fraction"] = round(top["inlier_fraction"],4)
    if (tilt > top_max_tilt_deg or
            top["residual_rmse_m"] > .004 or
            top["inlier_fraction"] < .60):
        result["top_plane"] = top
        result["reason"] = "TOP_NOT_RELIABLY_PARALLEL"
        return result

    # Parallel-plane distance at centroid, explicitly NOT a robot Z-axis.
    distances = np.abs(upper_points @ n_top + top["offset_m"])
    inliers = upper_points[distances <= .004]
    if len(inliers) < min_top_points:
        result["top_plane"] = top
        result["reason"] = "INSUFFICIENT_TOP_INLIERS"
        return result
    centroid = inliers.mean(axis=0)
    # Refine to a point ON fitted top plane, then take along table normal.
    on_top = centroid - n_top*float(centroid @ n_top + top["offset_m"])
    h = 1000.0*float(n_tab @ on_top + table["offset_m"])
    if (not math.isfinite(h) or h <= 0 or
            h > max_relative_height_mm):
        result["reason"] = "HEIGHT_OUTSIDE_BOUNDS"
        return result

    result["height_mm"] = round(h,3)
    result["validity"] = "EXPLORATORY_UNVERIFIED_PROJECTION"
    result["reason"] = "TARGET_METROLOGY_NOT_VERIFIED"
    result["top_plane"] = top
    result["quality"]["top_inlier_count"] = int(len(inliers))
    result["quality"]["top_centroid_camera_m"] = np.round(on_top,6).tolist()
    result["quality"]["estimator"] = "RANSAC_TOP_PLANE_MINUS_LOCAL_TABLE_PLANE_AT_TOP_CENTROID"
    result["quality"]["uncertainty_status"] = "RESIDUALS_ONLY_NO_VALIDATED_ERROR_BOUND"
    return result


def evaluate_reference_gate(
    phase_stats: dict, reference_mm: float, *,
    max_abs_bias_mm: float = 1.0,
    max_sample_std_mm: float = 1.0,
    min_valid_fraction: float = .95,
    max_p95_abs_error_mm: float = 2.0,
) -> dict:
    """Offline QA gate against independently measured physical reference.

    Explicitly separate measurement quality from metrological certification.
    This cannot certify camera calibration or robot-base coordinates.
    """
    if not np.isfinite(reference_mm) or reference_mm <= 0:
        raise ValueError("reference height must be positive and finite")
    attempted = int(phase_stats.get("attempted", 0))
    usable = int(phase_stats.get("usable", 0))
    median = phase_stats.get("height_mm_median")
    spread = phase_stats.get("height_mm_sample_std")
    low = phase_stats.get("height_mm_p05")
    high = phase_stats.get("height_mm_p95")
    errors = []
    if not attempted or usable < 15:
        errors.append("INSUFFICIENT_FRAMES")
    if attempted and usable/attempted < min_valid_fraction:
        errors.append("LOW_VALID_FRAME_FRACTION")
    values = (median,spread,low,high)
    if (any(v is None for v in values) or
        not all(np.isfinite(float(v)) for v in values)):
        errors.append("MISSING_DISTRIBUTION")
    else:
        if abs(float(median) - reference_mm) > max_abs_bias_mm:
            errors.append("SYSTEMATIC_BIAS_TOO_LARGE")
        if float(spread) > max_sample_std_mm:
            errors.append("FRAME_REPEATABILITY_TOO_LOW")
        if max(abs(float(low)-reference_mm),
               abs(float(high)-reference_mm)) > max_p95_abs_error_mm:
            errors.append("TAIL_ERROR_TOO_LARGE")
    passed = not errors
    return {
        "reference_mm": float(reference_mm),
        "research_target_pass": passed,
        "metrology_certified": False,
        "robot_ready": False,
        "status": "RESEARCH_GATE_PASS_ONLY" if passed else "RESEARCH_GATE_FAIL",
        "reasons": errors,
        "metrics_are_correlated_frames": True,
        "limits": {
            "max_abs_bias_mm": max_abs_bias_mm,
            "max_sample_std_mm": max_sample_std_mm,
            "min_valid_fraction": min_valid_fraction,
            "max_p95_abs_error_mm": max_p95_abs_error_mm,
        },
    }
