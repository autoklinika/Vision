"""DepthAI v3 / RVC2 vendor StereoDepth profiles for OAK-D Pro AF.

Do not copy preset filter constants: Luxonis SDK owns that policy.
Keep rectified-left (mm) for camera.frame_bundle.v1 and Perception.
No pipeline, device access, robot motion, EEPROM writes or IR control here.

Docs: https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/stereo_depth
      https://docs.luxonis.com/hardware/platform/depth/configuring-stereo-depth
"""
from __future__ import annotations

# These names exist in the pinned DepthAI 3.12.0 PresetMode on VENTUNO Q.
# FAST_ACCURACY is deprecated upstream, but is still a supported RVC2 preset
# with FULL depth resolution and no temporal smoothing in the pinned SDK.
# Do not substitute RVC4-only ACCURACY for this RVC2 camera.
STEREO_PRESETS = {
    "balanced": "FAST_ACCURACY",  # full depth resolution, static ECU geometry
    "detail": "FAST_ACCURACY",    # 4K RGB; same rectified depth geometry
    "near": "HIGH_DETAIL",        # closer range, 1/2 depth resolution
    "robotics": "ROBOTICS",       # motion oriented, 1/2 depth resolution, NON SAFETY
}


def preset_for_profile(acquisition_profile: str) -> str:
    """Explicit profile mapping, independent of device and driver."""
    try:
        return STEREO_PRESETS[acquisition_profile]
    except KeyError as exc:
        raise ValueError(f"Unsupported Luxonis acquisition profile: {acquisition_profile}") from exc


def apply_stereo_preset(stereo, dai, acquisition_profile: str) -> str:
    """Apply Luxonis preset FIRST, then explicit invariant frame-alignment rules.

    No manual subpixel, extended disparity, median, temporal, speckle or
    decimation edits: the SDK owns those combinations. A profile may change
    RAW16 depth dimensions; consumers MUST use frame.getTransformation()
    for the output K and frame shape. NEVER reuse RGB K for rectified depth.
    """
    preset_name = preset_for_profile(acquisition_profile)
    try:
        preset_enum = getattr(dai.node.StereoDepth.PresetMode, preset_name)
        left = dai.StereoDepthConfig.AlgorithmControl.DepthAlign.RECTIFIED_LEFT
    except AttributeError as exc:
        raise RuntimeError(f"DepthAI v3 incompatible with {preset_name}/RECTIFIED_LEFT") from exc
    stereo.setDefaultProfilePreset(preset_enum)
    stereo.setDepthAlign(left)
    stereo.setRectification(True)
    stereo.setLeftRightCheck(True)
    return preset_name
