"""Hardware-independent RGB/depth synchronizer and lossless offline bundle replay.

The DepthAI device monotonic clock is ONLY compared with itself. Host monotonic
timestamps measure queue/transport age; they are not exposure timestamps.
No USB, motion, neural network or external services in this module.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import json
import time
import uuid


SCHEMA = "camera.frame_bundle.v1"
STREAMS = ("rgb", "depth")


@dataclass(frozen=True)
class FramePacket:
    stream: str
    sequence: int
    device_ns: int
    host_received_ns: int
    width: int
    height: int
    payload: Any


@dataclass(frozen=True)
class FramePair:
    session_id: str
    pair_sequence: int
    rgb: FramePacket
    depth: FramePacket
    assembled_ns: int

    @property
    def pairing_delta_ms(self) -> float:
        return round(abs(self.rgb.device_ns - self.depth.device_ns) / 1e6, 3)


class RgbdSynchronizer:
    """Bounded nearest-in-time, in-order matching of two device-clock streams.

    Sequences detect stream drops; exact sequence equality is NOT required:
    independent RGB/mono frame sequence counters need not share their origin.
    """
    def __init__(self, max_delta_ms: float = 20., capacity: int = 16,
                 max_pending_ms: float = 550., max_age_ms: float = 450.):
        if not (0 < max_delta_ms <= 100 and 1 <= capacity <= 16):
            raise ValueError("invalid synchronization limits")
        self.max_delta_ns = int(max_delta_ms * 1e6)
        self.max_pending_ns = int(max_pending_ms * 1e6)
        self.max_age_ns = int(max_age_ms * 1e6)
        self.capacity = capacity
        self.reset()

    def reset(self):
        self.session_id = uuid.uuid4().hex
        self.pending = {k: deque() for k in STREAMS}
        self.last_seq = {k: None for k in STREAMS}
        self.last_device_ns = {k: None for k in STREAMS}
        self.last_host_ns = {k: None for k in STREAMS}
        self.received = {k: 0 for k in STREAMS}
        self.lost_sequence = {k: 0 for k in STREAMS}
        self.dropped = {k: 0 for k in STREAMS}
        self.rejected = {k: 0 for k in STREAMS}
        self.matched = 0
        self.latest: FramePair | None = None
        self.last_pair_device_ns = -1

    def _drop_old(self, now_ns: int):
        for stream in STREAMS:
            q = self.pending[stream]
            while q and now_ns - q[0].host_received_ns > self.max_pending_ns:
                q.popleft()
                self.dropped[stream] += 1

    def ingest(self, pkt: FramePacket, now_ns: int | None = None) -> FramePair | None:
        if pkt.stream not in STREAMS:
            raise ValueError("unsupported stream")
        stream = pkt.stream
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        if (pkt.device_ns <= 0 or pkt.sequence < 0 or
                pkt.width <= 0 or pkt.height <= 0 or
                pkt.host_received_ns > now_ns or
                now_ns - pkt.host_received_ns > self.max_pending_ns):
            self.rejected[stream] += 1
            return None
        old_seq = self.last_seq[stream]
        old_ts = self.last_device_ns[stream]
        if ((old_seq is not None and pkt.sequence <= old_seq) or
                (old_ts is not None and pkt.device_ns <= old_ts)):
            self.rejected[stream] += 1
            return None
        if old_seq is not None and pkt.sequence > old_seq + 1:
            self.lost_sequence[stream] += pkt.sequence - old_seq - 1
        self.last_seq[stream] = pkt.sequence
        self.last_device_ns[stream] = pkt.device_ns
        self.last_host_ns[stream] = pkt.host_received_ns
        self.received[stream] += 1
        self._drop_old(now_ns)
        q = self.pending[stream]
        if len(q) >= self.capacity:
            q.popleft()
            self.dropped[stream] += 1
        q.append(pkt)
        rgbq, dq = self.pending["rgb"], self.pending["depth"]
        while rgbq and dq:
            rgb, dep = rgbq[0], dq[0]
            delta = rgb.device_ns - dep.device_ns
            if abs(delta) <= self.max_delta_ns:
                rgbq.popleft()
                dq.popleft()
                if max(rgb.device_ns, dep.device_ns) <= self.last_pair_device_ns:
                    self.rejected["rgb"] += 1
                    self.rejected["depth"] += 1
                    continue
                if abs(rgb.host_received_ns - dep.host_received_ns) > self.max_pending_ns:
                    self.dropped["rgb"] += 1
                    self.dropped["depth"] += 1
                    continue
                self.matched += 1
                self.last_pair_device_ns = max(rgb.device_ns, dep.device_ns)
                pair = FramePair(
                    session_id=self.session_id, pair_sequence=self.matched,
                    rgb=rgb, depth=dep, assembled_ns=now_ns,
                )
                self.latest = pair
                return pair
            # The older head cannot match a future packet in the other stream.
            older = "rgb" if delta < 0 else "depth"
            self.pending[older].popleft()
            self.dropped[older] += 1
        return None

    def current(self, now_ns: int | None = None) -> FramePair | None:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        if self.latest is None or now_ns - self.latest.assembled_ns > self.max_age_ns:
            return None
        return self.latest

    def diagnostics(self, now_ns: int | None = None) -> dict:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        pair = self.current(now_ns)
        return {
            "schema_version": SCHEMA,
            "state": "SYNCED" if pair else "NOT_READY",
            "session_id": self.session_id,
            "paired_count": self.matched,
            "pairing_delta_ms": pair.pairing_delta_ms if pair else None,
            "pair_age_ms": round((now_ns - pair.assembled_ns) / 1e6, 2)
                if pair else None,
            "received": dict(self.received),
            "lost_sequences": dict(self.lost_sequence),
            "dropped_unpaired": dict(self.dropped),
            "rejected": dict(self.rejected),
            "pending": {k: len(v) for k, v in self.pending.items()},
            "queue_capacity": self.capacity,
            "pairing_limit_ms": self.max_delta_ns / 1e6,
            "freshness_limit_ms": self.max_age_ns / 1e6,
            "latest_device_rgb_minus_depth_ms": (
                round((self.last_device_ns["rgb"] - self.last_device_ns["depth"]) / 1e6, 3)
                if all(x is not None for x in self.last_device_ns.values()) else None),
            "latest_host_rgb_minus_depth_ms": (
                round((self.last_host_ns["rgb"] - self.last_host_ns["depth"]) / 1e6, 3)
                if all(x is not None for x in self.last_host_ns.values()) else None),
        }


def bundle_metadata(pair: FramePair, calibration: dict | None = None,
                    quality: dict | None = None, now_ns: int | None = None) -> dict:
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    rgb, depth = pair.rgb, pair.depth
    return {
        "schema_version": SCHEMA,
        "camera_id": "oak_d_pro_af_overhead",
        "session_id": pair.session_id,
        "bundle_id": f"{pair.session_id}:{pair.pair_sequence}",
        "sequence": pair.pair_sequence,
        "sync_state": "SYNCED",
        "pairing_delta_ms": pair.pairing_delta_ms,
        "device_timestamp": {
            "clock_domain": "depthai_device_monotonic_unsynced_to_host",
            "rgb_ns": rgb.device_ns, "depth_ns": depth.device_ns,
        },
        "host_timestamp": {
            "clock_domain": "host_monotonic",
            "rgb_received_ns": rgb.host_received_ns,
            "depth_received_ns": depth.host_received_ns,
            "assembled_ns": pair.assembled_ns,
        },
        "capture_age_ms": round(max(0, now_ns - min(rgb.host_received_ns,
                                                depth.host_received_ns)) / 1e6, 2),
        "age_basis": "host_receive_proxy_not_sensor_exposure",
        "assembly_latency_ms": round(
            max(0, pair.assembled_ns - max(rgb.host_received_ns,
                                          depth.host_received_ns)) / 1e6, 3),
        "host_arrival_spread_ms": round(
            abs(rgb.host_received_ns - depth.host_received_ns) / 1e6, 3),
        "rgb": {
            "stream_id": "rgb_mjpeg", "frame_id": rgb.sequence,
            "sequence": rgb.sequence, "resolution": [rgb.width, rgb.height],
            "encoding": "jpeg", "coordinate_frame": "rgb_optical",
            "aligned_to": "rgb_optical",
        },
        "depth": {
            "stream_id": "stereo_depth", "frame_id": depth.sequence,
            "sequence": depth.sequence, "resolution": [depth.width, depth.height],
            "encoding": "uint16", "depth_unit": "mm",
            "invalid_depth_values": [0], "invalid_depth_mask": "depth_mm == 0",
            "aligned_to": "stereo_left_rectified",
            "coordinate_frame": "stereo_left_rectified_optical",
        },
        "calibration": calibration or {"state": "UNAVAILABLE"},
        "intrinsics_id": (calibration or {}).get("intrinsics_id"),
        "extrinsics_id": (calibration or {}).get("extrinsics_id"),
        "calibration_revision": (calibration or {}).get("revision"),
        "transform_status": {
            "table": "UNAVAILABLE", "robot_base": "UNAVAILABLE",
        },
        "quality": quality or {},
    }


def encode_replay_npz(pair: FramePair, metadata: dict) -> bytes:
    """On-demand memory archive; does not write files or open hardware."""
    import numpy as np
    depth = np.asarray(pair.depth.payload)
    if depth.shape != (pair.depth.height, pair.depth.width) or depth.dtype != np.uint16:
        raise ValueError("depth must be uint16 (height, width)")
    buf = BytesIO()
    np.savez(buf, metadata=np.asarray(json.dumps(metadata)),
             rgb_jpeg=np.frombuffer(pair.rgb.payload, dtype=np.uint8),
             depth_mm=depth.astype("<u2", copy=False))
    return buf.getvalue()


def decode_replay_npz(source: bytes | str | Path) -> tuple[dict, bytes, Any]:
    """Replay without device/DepthAI, with no pickle execution."""
    import numpy as np
    obj = BytesIO(source) if isinstance(source, bytes) else source
    with np.load(obj, allow_pickle=False) as bundle:
        meta = json.loads(str(bundle["metadata"].item()))
        rgb = bundle["rgb_jpeg"].tobytes()
        depth = bundle["depth_mm"].copy()
    if (meta.get("schema_version") != SCHEMA or
            depth.dtype != np.uint16 or depth.ndim != 2 or
            depth.shape != tuple(reversed(meta["depth"]["resolution"])) or
            not rgb.startswith(b"\xff\xd8")):
        raise ValueError("invalid camera.frame_bundle.v1 replay")
    return meta, rgb, depth


def read_optics_readonly(device, dai, rgb_size: tuple[int, int]) -> dict:
    """Read camera EEPROM calibration; never flash or infer table/robot pose.

    Factory camera intrinsics describe native optics. Rectified-left reprojection
    remains NOT_VERIFIED until the exact stereo output projection is established.
    """
    import hashlib
    try:
        cal = device.readCalibration()
        rgb_k = cal.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A,
                                         rgb_size[0], rgb_size[1])
        mono_k = cal.getCameraIntrinsics(dai.CameraBoardSocket.CAM_B, 1280, 800)
        left_rotation = cal.getStereoLeftRectificationRotation()
        optical = {
            "rgb_optical": {"resolution": list(rgb_size), "K": rgb_k},
            "stereo_left_raw_optical": {
                "resolution": [1280, 800], "K": mono_k,
            },
            "stereo_left_rectification_rotation": left_rotation,
        }
        revision = hashlib.sha256(json.dumps(optical, sort_keys=True).encode()).hexdigest()[:16]
        return {
            "state": "EEPROM_READ_ONLY",
            "revision": revision,
            "intrinsics_id": "oak_device_intrinsics_" + revision,
            "extrinsics_id": None,
            "intrinsics": optical,
            "depth_projection_status": "RECTIFIED_OUTPUT_UNVERIFIED",
            "rgb_to_depth_registration": "NOT_ALIGNED",
            "table_calibration": "UNAVAILABLE",
            "robot_base_calibration": "UNAVAILABLE",
        }
    except Exception as exc:
        return {"state": "UNAVAILABLE", "reason": type(exc).__name__,
                "intrinsics_id": None, "extrinsics_id": None,
                "depth_projection_status": "UNAVAILABLE"}
