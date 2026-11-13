"""Optical metadata, pixel geometry and diagnostic JPEG ROI for OAK-D Pro AF.

Read-only. No device operations, calibration writes or robot coordinates.
Use per-ImgFrame transformation for the image actually produced, never
assume raw sensor K is identical to rectified/cropped/downsized output K.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math


class OpticalMetadataError(ValueError):
    """Optical data cannot be trusted enough for XYZ generation."""


def _matrix3(raw):
    matrix = [[float(v) for v in row] for row in raw]
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise OpticalMetadataError("intrinsics must be 3x3")
    if not all(math.isfinite(v) for row in matrix for v in row):
        raise OpticalMetadataError("nonfinite intrinsics")
    if matrix[0][0] <= 0 or matrix[1][1] <= 0 or abs(matrix[2][2] - 1.) > .001:
        raise OpticalMetadataError("invalid focal lengths or projection")
    if any(abs(matrix[2][k]) > .001 for k in (0, 1)):
        raise OpticalMetadataError("non-pinhole K")
    return matrix


def describe_output_transform(img_frame, width: int, height: int,
                              role: str) -> dict:
    """Read DepthAI 3 ImgFrame transformation without touching the device.

    A reported K is NOT metrological validation. On rectified depth streams,
    the camera-frame transform must still be compared with the actual
    undistortion/rectification mapping and checked against a physical target.
    """
    if role not in ("rgb", "stereo_depth"):
        raise OpticalMetadataError("unsupported camera stream")
    if width <= 0 or height <= 0:
        raise OpticalMetadataError("invalid output dimensions")
    tr = img_frame.getTransformation()
    if tr is None or not tr.isValid():
        raise OpticalMetadataError("missing/invalid frame transformation")
    size = list(map(int, tr.getSize()))
    if size != [width, height]:
        raise OpticalMetadataError(f"frame transformation size mismatch {size} != {(width,height)}")
    intrinsic = _matrix3(tr.getIntrinsicMatrix())
    source_intrinsic = _matrix3(tr.getSourceIntrinsicMatrix())
    source_size = list(map(int, tr.getSourceSize()))
    if min(source_size) <= 0:
        raise OpticalMetadataError("invalid optical sensor dimensions")
    blob = json.dumps({"role": role, "size": size, "K": intrinsic,
                       "source_size": source_size, "source_K": source_intrinsic},
                      sort_keys=True, separators=(",", ":"))
    revision = sha256(blob.encode("ascii")).hexdigest()[:16]
    return {
        "frame_of_reference": (
            "stereo_left_rectified_optical" if role == "stereo_depth"
            else "rgb_optical"),
        "resolution": size,
        "source_resolution": source_size,
        "K": intrinsic,
        "source_K": source_intrinsic,
        "source": "depthai_3_imgframe_transformation",
        "intrinsics_id": f"{role}_output_{revision}",
        "validity": "FRAME_METADATA_REPORTED_NOT_METROLOGICALLY_VERIFIED",
    }


def roi_from_normalized(x: float, y: float, width: float, height: float,
                        image_width: int, image_height: int) -> tuple[int, int, int, int]:
    """Normalized ROI to image pixels. Fail closed instead of clipping silently."""
    vals = (x, y, width, height)
    if (not all(math.isfinite(v) for v in vals)
            or x < 0 or y < 0 or width <= 0 or height <= 0
            or x + width > 1.000001 or y + height > 1.000001
            or image_width < 1 or image_height < 1):
        raise ValueError("invalid normalized ROI")
    x0 = min(int(round(x * image_width)), image_width - 1)
    y0 = min(int(round(y * image_height)), image_height - 1)
    x1 = min(int(round((x + width) * image_width)), image_width)
    y1 = min(int(round((y + height) * image_height)), image_height)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("ROI too small at current resolution")
    return x0, y0, x1 - x0, y1 - y0


def crop_diagnostic_jpeg(jpeg: bytes, roi: tuple[float, float, float, float],
                         quality: int = 85) -> tuple[bytes, dict]:
    """Pure on-demand digital zoom crop. No interpolation, no camera controls.

    Requires source RGB JPEG. Caller is responsible for bounding concurrency.
    Returns metadata with precise ROI in source RGB pixels. This crop does not
    change the stereo-depth intrinsics or create RGB/depth spatial alignment.
    """
    import cv2
    import numpy as np
    if not jpeg.startswith(b"\xff\xd8") or not (40 <= quality <= 95):
        raise ValueError("invalid JPEG or quality")
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.ndim != 3:
        raise ValueError("corrupt RGB JPEG")
    ih, iw = frame.shape[:2]
    x, y, w, h = roi_from_normalized(*roi, iw, ih)
    crop = frame[y:y+h, x:x+w]
    ok, arr = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("ROI JPEG encoding failed")
    return arr.tobytes(), {
        "crop_frame": "rgb_optical",
        "source_resolution": [iw, ih],
        "roi_pixels": [x, y, w, h],
        "output_resolution": [w, h],
        "interpolated": False,
        "zoom_type": "digital_crop",
        "depth_registration": "NOT_ALIGNED",
    }


def intrinsics_for_crop(original_k, roi_pixels):
    """K for cropped RGB only; never re-label it as aligned to stereo depth."""
    k = _matrix3(original_k)
    x, y, w, h = (int(v) for v in roi_pixels)
    if x < 0 or y < 0 or w < 1 or h < 1:
        raise ValueError("invalid ROI")
    out = [row[:] for row in k]
    out[0][2] -= x
    out[1][2] -= y
    return out
