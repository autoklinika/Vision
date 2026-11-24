"""Opt-in ROS subscriptions; caller owns node, executor and ROS lifecycle."""
from collections import deque
from dataclasses import dataclass
from threading import Lock
import math
import numbers
import heapq
from .ros2_messages import normalize_rgbd, image_layout, _time

MAX_RETAINED_BYTES = 128 * 1024 * 1024


MAX_CANDIDATES = 4096


@dataclass(frozen=True)
class _Stamp:
    sec: int
    nanosec: int


@dataclass(frozen=True)
class _Header:
    stamp: _Stamp
    frame_id: str


@dataclass(frozen=True)
class _Image:
    header: _Header
    encoding: str
    width: int
    height: int
    step: int
    is_bigendian: int
    data: bytes


@dataclass(frozen=True)
class _ROI:
    x_offset: int
    y_offset: int
    height: int
    width: int
    do_rectify: bool


@dataclass(frozen=True)
class _CameraInfo:
    header: _Header
    width: int
    height: int
    k: tuple
    d: tuple
    r: tuple
    p: tuple
    distortion_model: str
    binning_x: int
    binning_y: int
    roi: _ROI


def _header(header):
    return _Header(_Stamp(header.stamp.sec, header.stamp.nanosec), header.frame_id)


@dataclass(frozen=True)
class TopicBindings:
    rgb: str
    depth: str
    rgb_info: str
    depth_info: str
    ros_domain_id: int

    def __post_init__(self):
        topics = (self.rgb, self.depth, self.rgb_info, self.depth_info)
        if any(not isinstance(t, str) or not t.startswith('/') or len(t) < 2 or any(c.isspace() for c in t) for t in topics) or len(set(topics)) != 4: raise ValueError('four explicit absolute topics required')
        if type(self.ros_domain_id) is not int or not 0 <= self.ros_domain_id <= 232: raise ValueError('explicit ROS domain required')


class SnapshotCollector:
    def __init__(self, bindings, *, capacity=4):
        if not isinstance(bindings, TopicBindings) or type(capacity) is not int or not 1 <= capacity <= 32: raise ValueError('invalid collector configuration')
        self.bindings = bindings
        self._buffers = {name: deque(maxlen=capacity) for name in ('rgb', 'depth', 'rgb_info', 'depth_info')}
        self._capacity = capacity
        self._retained_bytes = 0
        self._sequence = 0
        self._lock = Lock()
        self._subscriptions = []

    def inject(self, stream, message):
        if stream not in self._buffers: raise ValueError('unknown stream')
        if stream in ('rgb', 'depth'):
            size = image_layout(message, depth=stream == 'depth')
        else:
            try:
                _time(message.header)
                if not isinstance(message.header.frame_id, str) or not 0 < len(message.header.frame_id) <= 256: raise ValueError('invalid frame')
                if any(type(x) is not int or x <= 0 or x > 65535 for x in (message.width, message.height)): raise ValueError('invalid CameraInfo dimensions')
                if any(len(getattr(message, k)) != n for k, n in (('k', 9), ('r', 9), ('p', 12))) or len(message.d) > 32: raise ValueError('invalid CameraInfo fields')
                if not isinstance(message.distortion_model, str) or len(message.distortion_model) > 256: raise ValueError('invalid distortion model')
                if any(type(x) is not int or not 0 <= x <= 2**32-1 for x in (message.binning_x, message.binning_y, message.roi.x_offset, message.roi.y_offset, message.roi.height, message.roi.width)): raise ValueError('invalid CameraInfo metadata')
                if any(isinstance(v, bool) or not isinstance(v, numbers.Real) or not math.isfinite(float(v)) for k in ('k','d','r','p') for v in getattr(message, k)): raise ValueError('invalid CameraInfo values')
                if type(message.roi.do_rectify) is not bool: raise ValueError('invalid CameraInfo ROI')
            except (AttributeError, TypeError) as exc:
                raise ValueError('invalid CameraInfo message') from exc
            size = 0
        with self._lock:
            buf = self._buffers[stream]
            oldest = min(buf, key=lambda item: item[2]) if len(buf) == self._capacity else None
            removed = oldest[1] if oldest else 0
            if self._retained_bytes - removed + size > MAX_RETAINED_BYTES: raise ValueError('retained image budget exceeded')
            # Copy only after both per-image and retained-budget validation.
            if stream in ('rgb', 'depth'):
                owned = _Image(_header(message.header), message.encoding, message.width,
                               message.height, message.step, message.is_bigendian, bytes(message.data))
                if image_layout(owned, depth=stream == 'depth') != size:
                    raise ValueError('image changed during ingress')
            else:
                roi = message.roi
                owned = _CameraInfo(_header(message.header), message.width, message.height,
                                    *(tuple(getattr(message, k)) for k in ('k', 'd', 'r', 'p')),
                                    message.distortion_model, message.binning_x, message.binning_y,
                                    _ROI(roi.x_offset, roi.y_offset, roi.height, roi.width, roi.do_rectify))
            if len(buf) == self._capacity:
                buf.remove(oldest)
                self._retained_bytes -= removed
            self._sequence += 1
            entry = (owned, size, self._sequence)
            timestamp = _time(owned.header)
            index = len(buf)
            while index and _time(buf[index - 1][0].header) > timestamp:
                index -= 1
            buf.insert(index, entry)
            self._retained_bytes += size

    def snapshot(self, *, scene_frame, depth_unit, now, max_age, max_skew, tf_lookup):
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (now, max_age, max_skew)) or max_age <= 0 or max_skew < 0: raise ValueError('invalid clock limits')
        with self._lock:
            streams = [[m for m, _, _ in reversed(self._buffers[k])] for k in ('rgb','depth','rgb_info','depth_info')]
        # Sort by original timestamp and arrival order; latest arrival wins ties.
        streams = [[m for m in s if 0 <= now - _time(m.header) <= max_age] for s in streams]
        if not all(streams):
            raise ValueError('no synchronized stream set')

        def priority(indices):
            # Maximize the oldest timestamp first, then the remaining timestamps.
            times = sorted(_time(streams[i][index].header) for i, index in enumerate(indices))
            return tuple(-t for t in times) + indices

        first = (0, 0, 0, 0)
        heap = [(priority(first), first)]
        visited = {first}
        for _ in range(MAX_CANDIDATES):
            if not heap:
                break
            _, indices = heapq.heappop(heap)
            rgb, depth, ri, di = (streams[i][index] for i, index in enumerate(indices))
            times = [_time(m.header) for m in (rgb, depth, ri, di)]
            if (max(times) - min(times) <= max_skew
                    and ri.header.frame_id == rgb.header.frame_id
                    and di.header.frame_id == depth.header.frame_id
                    and (ri.width, ri.height) == (rgb.width, rgb.height)
                    and (di.width, di.height) == (depth.width, depth.height)):
                try:
                    scene_tf = tf_lookup(scene_frame, rgb.header.frame_id, rgb.header.stamp)
                    relative_tf = tf_lookup(rgb.header.frame_id, depth.header.frame_id, depth.header.stamp)
                    return normalize_rgbd(rgb, depth, ri, di, scene_tf, relative_tf, scene_frame=scene_frame, depth_unit=depth_unit, now=now, max_age=max_age, max_skew=max_skew)
                except ValueError:
                    pass
            for i in range(4):
                neighbor = list(indices)
                neighbor[i] += 1
                neighbor = tuple(neighbor)
                if neighbor[i] < len(streams[i]) and neighbor not in visited:
                    visited.add(neighbor)
                    heapq.heappush(heap, (priority(neighbor), neighbor))
        raise ValueError('no synchronized stream set')

    @classmethod
    def from_node(cls, node, bindings, *, capacity=4, qos=None):
        # No init, spin, node creation, driver launch or domain mutation here.
        import rclpy
        from sensor_msgs.msg import Image, CameraInfo
        import tf2_ros
        del rclpy, tf2_ros
        import os
        if os.environ.get('ROS_DOMAIN_ID', '0') != str(bindings.ros_domain_id): raise ValueError('node ROS_DOMAIN_ID configuration mismatch')
        collector = cls(bindings, capacity=capacity)
        if qos is None:
            from rclpy.qos import qos_profile_sensor_data
            qos = qos_profile_sensor_data
        for name, typ in (('rgb',Image),('depth',Image),('rgb_info',CameraInfo),('depth_info',CameraInfo)):
            collector._subscriptions.append(node.create_subscription(typ, getattr(bindings, name), lambda msg, key=name: collector.inject(key, msg), qos))
        return collector
