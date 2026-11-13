"""Experimental opt-in OAK-D camera features; NO implicit production changes.

IR doses here are bounded test candidates, NOT calibrated recommendations.
Calls affecting hardware are made only by the camera's unique USB owner.
No network endpoints in this module; not a safety system.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from camera_optics import roi_from_normalized


@dataclass(frozen=True)
class FeatureProfile:
    name: str
    acquisition_profile: str
    ir_dot: float = 0.0
    ir_flood: float = 0.0
    af_mode: str = "unchanged"
    roi: tuple[float, float, float, float] | None = None
    hardware_validated: bool = False


# These profiles are not activated by the existing production systemd unit.
# Dot 0.15 and flood 0.20 are research levels, not a metrology setting.
EXPERIMENTAL_PROFILES = {
    "survey": FeatureProfile("survey", "balanced"),
    "depth_precision": FeatureProfile("depth_precision", "balanced", ir_dot=.15),
    "detail": FeatureProfile("detail", "detail", af_mode="auto",
                             roi=(.25, .25, .5, .5)),
    "low_light": FeatureProfile("low_light", "balanced", ir_flood=.2),
}


def get_profile(name: str) -> FeatureProfile:
    if name not in EXPERIMENTAL_PROFILES:
        raise ValueError(f"unsupported experimental profile: {name}")
    return EXPERIMENTAL_PROFILES[name]


def validate_ir_levels(dot: float, flood: float, limit: float = .35) -> None:
    """Use only in a controlled test; power supply/thermal impact unverified."""
    if (not math.isfinite(dot) or not math.isfinite(flood)
            or dot < 0 or flood < 0 or dot > limit or flood > limit):
        raise ValueError("IR pilot outside safe bounded test envelope")


def apply_ir_test_levels(device, dot: float, flood: float) -> dict:
    """Apply explicit test-only levels on already-open OAK; caller restores to 0."""
    validate_ir_levels(dot, flood)
    device.setIrLaserDotProjectorIntensity(float(dot))
    try:
        device.setIrFloodLightIntensity(float(flood))
    except Exception:
        try:
            device.setIrLaserDotProjectorIntensity(0.)
        finally:
            raise
    return {"dot": float(dot), "flood": float(flood),
            "status": "COMMAND_SENT_NOT_PHOTOMETRICALLY_VERIFIED"}


def reset_ir_test_levels(device):
    """Best effort: call from a finally block before camera shutdown."""
    failures = []
    for name, setter in (
        ("dot", device.setIrLaserDotProjectorIntensity),
        ("flood", device.setIrFloodLightIntensity),
    ):
        try:
            setter(0.0)
        except Exception:
            failures.append(name)
    return failures


def af_sensor_roi_from_transform(transform, normalized_roi):
    """Map image ROI through ImgTransformation inverse, not arbitrary x/y scale.

    Crop/letterbox/stretched RGB may have different principal point and FOV.
    Input ROI refers to the output RGB optical image. AF coordinates refer
    to the source sensor; never apply AF ROI directly to depth.
    """
    import numpy as np
    width, height = map(int, transform.getSize())
    sw, sh = map(int, transform.getSourceSize())
    x, y, w, h = roi_from_normalized(*normalized_roi, width, height)
    inv = np.asarray(transform.getMatrixInv(), dtype=float)
    if inv.shape != (3, 3) or not np.all(np.isfinite(inv)):
        raise ValueError("invalid image->sensor transform")
    corners = np.asarray([[x, y, 1], [x+w, y, 1],
                          [x, y+h, 1], [x+w, y+h, 1]], dtype=float)
    mapped = corners @ inv.T
    if not np.all(np.abs(mapped[:, 2]) > 1e-10):
        raise ValueError("nonprojectable ROI")
    mapped = mapped[:, :2] / mapped[:, 2, None]
    left = int(np.floor(mapped[:, 0].min()))
    top = int(np.floor(mapped[:, 1].min()))
    right = int(np.ceil(mapped[:, 0].max()))
    bottom = int(np.ceil(mapped[:, 1].max()))
    if (left < 0 or top < 0 or right > sw or bottom > sh
            or right <= left or bottom <= top):
        raise ValueError("ROI maps outside sensor; do not silently clamp")
    return left, top, right-left, bottom-top


def make_focus_control(dai, mode: str, sensor_roi=None):
    """Build DepthAI CameraControl offline; sending is separate and opt-in."""
    modes = {
        "auto": dai.CameraControl.AutoFocusMode.AUTO,
        "continuous_video": dai.CameraControl.AutoFocusMode.CONTINUOUS_VIDEO,
        "macro": dai.CameraControl.AutoFocusMode.MACRO,
        "off": dai.CameraControl.AutoFocusMode.OFF,
    }
    if mode not in modes:
        raise ValueError("invalid AF mode")
    ctrl = dai.CameraControl()
    ctrl.setAutoFocusMode(modes[mode])
    if sensor_roi is not None:
        x, y, w, h = sensor_roi
        if any(not isinstance(i, int) for i in sensor_roi) or min(sensor_roi) < 0 or w <= 0 or h <= 0:
            raise ValueError("invalid AF sensor ROI")
        ctrl.setAutoFocusRegion(x, y, w, h)
    if mode == "auto":
        ctrl.setAutoFocusTrigger()
    return ctrl
