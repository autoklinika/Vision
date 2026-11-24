"""Structural and freshness checks, separate from external authentication.

Passing these checks does not establish sensor provenance or authorize Core evidence.
"""
import math
from .contracts import ObservationReceipt, ReadinessReceipt


def validate_readiness(receipt, context, calibrations, *, now, max_age):
    if not isinstance(receipt, ReadinessReceipt): raise ValueError('readiness receipt required')
    if type(now) not in (int, float) or not math.isfinite(now) or type(max_age) not in (int, float) or not math.isfinite(max_age) or max_age <= 0: raise ValueError('invalid clock')
    if receipt.session_id != context.session_id or receipt.profile_revisions != context.profile_revisions: raise ValueError('context mismatch')
    if dict(receipt.calibration_ids) != dict(calibrations): raise ValueError('calibration mismatch')
    if not 0 <= now - receipt.timestamp <= max_age or not receipt.quality: raise ValueError('stale or low-quality readiness')


def validate_observation(receipt, context, calibrations, *, now, max_age, max_skew, sensor_frame, scene_frame, known_transforms, capabilities):
    if not isinstance(receipt, ObservationReceipt): raise ValueError('observation receipt required')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (now, max_age, max_skew)) or max_age <= 0 or max_skew < 0: raise ValueError('invalid clock limits')
    if receipt.session_id != context.session_id or receipt.profile_revisions != context.profile_revisions: raise ValueError('context mismatch')
    if dict(receipt.calibration_ids) != dict(calibrations): raise ValueError('calibration mismatch')
    if receipt.frame_id != scene_frame or receipt.tf.frame_id != scene_frame or receipt.tf_source_frame != sensor_frame: raise ValueError('transform frame mismatch')
    if (sensor_frame, scene_frame) not in known_transforms: raise ValueError('unknown transform')
    if any(s.frame_id != sensor_frame for s in (receipt.rgb, receipt.camera_info)): raise ValueError('sensor frame mismatch')
    extra = []
    if receipt.depth.frame_id != sensor_frame:
        if receipt.depth_camera_info is None or receipt.depth_to_rgb_tf is None: raise ValueError('depth calibration required')
        if (receipt.depth_camera_info.frame_id != receipt.depth.frame_id or receipt.depth_to_rgb_tf.frame_id != sensor_frame or receipt.depth_to_rgb_source_frame != receipt.depth.frame_id): raise ValueError('relative transform frame mismatch')
        if (receipt.depth.frame_id, sensor_frame) not in known_transforms or receipt.relative_calibration_id not in calibrations.values(): raise ValueError('unpinned relative calibration')
        extra = [receipt.depth_camera_info, receipt.depth_to_rgb_tf]
    elif receipt.depth_camera_info is not None:
        if receipt.depth_camera_info.frame_id != sensor_frame or receipt.depth_to_rgb_tf.frame_id != sensor_frame or receipt.depth_to_rgb_source_frame != sensor_frame or receipt.relative_calibration_id not in calibrations.values(): raise ValueError('invalid depth calibration')
        extra = [receipt.depth_camera_info, receipt.depth_to_rgb_tf]
    if not {'rgb', 'depth', 'camera_info', 'tf'} <= set(capabilities): raise ValueError('missing sensor capability')
    stamps = [s.timestamp for s in (receipt.rgb, receipt.depth, receipt.camera_info, receipt.tf)]
    stamps += [s.timestamp for s in extra]
    if any(not 0 <= now - stamp <= max_age for stamp in stamps) or max(stamps) - min(stamps) > max_skew: raise ValueError('stale or unsynchronized sensor data')
    if not receipt.quality: raise ValueError('low-quality observation')
