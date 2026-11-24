"""Transport-neutral, bounded normalization of ROS image and transform messages."""
from dataclasses import dataclass
import hashlib
import json
import math
import struct
from .contracts import SensorStamp

MAX_IMAGE_BYTES = 64 * 1024 * 1024


def _ref(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _time(header):
    sec, ns = header.stamp.sec, header.stamp.nanosec
    if type(sec) is not int or type(ns) is not int or sec < 0 or not 0 <= ns < 1000000000:
        raise ValueError('invalid ROS timestamp')
    return sec + ns / 1e9


def _stamp(header, ref):
    return SensorStamp(header.frame_id, _time(header), ref)


@dataclass(frozen=True)
class ImageFrame:
    stamp: SensorStamp
    width: int
    height: int
    encoding: str
    step: int
    is_bigendian: bool
    data: bytes


@dataclass(frozen=True)
class CameraCalibration:
    stamp: SensorStamp
    width: int
    height: int
    k: tuple
    d: tuple
    r: tuple
    p: tuple
    distortion_model: str
    binning_x: int
    binning_y: int
    roi: tuple


@dataclass(frozen=True)
class Transform:
    stamp: SensorStamp
    source_frame: str
    translation_m: tuple
    quaternion_xyzw: tuple


@dataclass(frozen=True)
class RGBDFramePacket:
    rgb: ImageFrame
    depth: ImageFrame
    rgb_info: CameraCalibration
    depth_info: CameraCalibration
    scene_from_rgb: Transform
    rgb_from_depth: Transform
    depth_unit: str


def image_layout(msg, *, depth=False):
    allowed = {'16UC1': 2, '32FC1': 4} if depth else {'rgb8': 3, 'bgr8': 3}
    try:
        size = allowed[msg.encoding]
        w, h, step = msg.width, msg.height, msg.step
        if any(type(x) is not int or x <= 0 for x in (w, h, step)) or step < w * size or step * h > MAX_IMAGE_BYTES: raise ValueError('invalid image dimensions or stride')
        if type(msg.is_bigendian) not in (int, bool) or msg.is_bigendian not in (0, 1): raise ValueError('invalid byte order')
        if len(msg.data) != step * h: raise ValueError('invalid image data length')
        _time(msg.header)
        if not isinstance(msg.header.frame_id, str) or not 0 < len(msg.header.frame_id) <= 256: raise ValueError('invalid frame')
        return step * h
    except (AttributeError, TypeError, KeyError) as exc:
        raise ValueError('invalid image message') from exc


def image(msg, *, depth=False, depth_unit=None):
    allowed = {'16UC1': (2, 'mm'), '32FC1': (4, 'm')} if depth else {'rgb8': (3, None), 'bgr8': (3, None)}
    if msg.encoding not in allowed: raise ValueError('unsupported image encoding')
    size, unit = allowed[msg.encoding]
    if depth and depth_unit != unit: raise ValueError('explicit metric depth unit required')
    image_layout(msg, depth=depth)
    w, h, step = msg.width, msg.height, msg.step
    data = bytes(msg.data)
    if depth:
        fmt = ('>' if msg.is_bigendian else '<') + ('H' if size == 2 else 'f')
        usable = False
        for row in range(h):
            for (value,) in struct.iter_unpack(fmt, data[row * step:row * step + w * size]):
                if value > 0 and math.isfinite(value):
                    usable = True
                    break
            if usable: break
        if not usable: raise ValueError('no usable metric depth samples')
    return ImageFrame(_stamp(msg.header, _ref(data)), w, h, msg.encoding, step, bool(msg.is_bigendian), data)


def camera_info(msg, frame):
    if msg.header.frame_id != frame.stamp.frame_id or (msg.width, msg.height) != (frame.width, frame.height): raise ValueError('CameraInfo image mismatch')
    k, d, r, p = (tuple(float(x) for x in getattr(msg, name)) for name in ('k', 'd', 'r', 'p'))
    if len(k) != 9 or len(r) != 9 or len(p) != 12 or len(d) > 32 or any(not math.isfinite(x) for x in k+d+r+p): raise ValueError('invalid CameraInfo matrix')
    if k[0] <= 0 or k[4] <= 0 or k[8] != 1 or k[1] != 0 or k[3] != 0 or k[6] != 0 or k[7] != 0 or not (0 <= k[2] < msg.width and 0 <= k[5] < msg.height): raise ValueError('invalid camera intrinsics')
    roi = msg.roi
    region = (roi.x_offset, roi.y_offset, roi.height, roi.width, bool(roi.do_rectify))
    vals = (msg.width, msg.height, k, d, r, p, msg.distortion_model, msg.binning_x, msg.binning_y, region)
    if any(type(x) is not int or x < 0 for x in (msg.binning_x, msg.binning_y, *region[:4])): raise ValueError('invalid camera metadata')
    return CameraCalibration(_stamp(msg.header, _ref(_canonical(vals))), *vals)


def transform(msg, target, source):
    if msg is None: raise ValueError('missing TF')
    if msg.header.frame_id != target or msg.child_frame_id != source: raise ValueError('TF frame mismatch')
    t, q = msg.transform.translation, msg.transform.rotation
    xyz = tuple(float(v) for v in (t.x, t.y, t.z)); quat = tuple(float(v) for v in (q.x, q.y, q.z, q.w))
    if any(not math.isfinite(x) for x in xyz+quat) or abs(math.hypot(*quat)-1) > 1e-5: raise ValueError('invalid TF content')
    ref = _ref(_canonical((target, source, xyz, quat)))
    return Transform(_stamp(msg.header, ref), source, xyz, quat)


def normalize_rgbd(rgb, depth, rgb_info, depth_info, scene_tf, relative_tf, *, scene_frame, depth_unit, now, max_age, max_skew):
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (now, max_age, max_skew)) or max_age <= 0 or max_skew < 0: raise ValueError('invalid clock limits')
    a, b = image(rgb), image(depth, depth=True, depth_unit=depth_unit)
    c, d = camera_info(rgb_info, a), camera_info(depth_info, b)
    e = transform(scene_tf, scene_frame, a.stamp.frame_id)
    f = transform(relative_tf, a.stamp.frame_id, b.stamp.frame_id)
    stamps = [x.stamp.timestamp for x in (a,b,c,d,e,f)]
    if any(not 0 <= now - t <= max_age for t in stamps) or max(stamps)-min(stamps) > max_skew: raise ValueError('stale or unsynchronized data')
    return RGBDFramePacket(a,b,c,d,e,f,depth_unit)
