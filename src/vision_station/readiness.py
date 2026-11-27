"""Diagnostic readiness evidence, independent of trusted inspection receipts.

No actuator access, no ROS imports in the request path. Only bounded, fresh
observations from an explicitly configured local observer can change readiness.
"""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time

EVIDENCE_AGE = 2.0
SNAPSHOT_AGE = 5.0
MAX_BYTES = 8192
JOINTS = tuple(f"joint{i}" for i in range(1, 8))
SOURCES = ("nero", "oak", "oak800", "moveit")
SCHEMA = "vision.device-readiness.v1"
# Stable codes, no raw telemetry, error messages, coordinates or images.
REASONS = {
    "SERVICE_INACTIVE": "NOT_READY",
    "SERVICE_UNKNOWN": "UNKNOWN",
    "USB_MISSING": "NOT_READY",
    "OBSERVER_UNAVAILABLE": "UNKNOWN",
    "AMBIGUOUS_SCENE": "NOT_READY",
    "JOINT_FEEDBACK_UNVERIFIED": "UNKNOWN",
    "ARM_STATUS_UNVERIFIED": "UNKNOWN",
    "ARM_BRAKE_NOT_RELEASED": "NOT_READY",
    "ARM_FAULT": "NOT_READY",
    "MOTOR_STATUS_UNVERIFIED": "UNKNOWN",
    "MOTORS_NOT_ENABLED": "NOT_READY",
    "NERO_TELEMETRY_OK": "READY",
    "RGBD_UNVERIFIED": "UNKNOWN",
    "RGBD_STREAMS_OK": "READY",
    "SCENE_UNVERIFIED": "UNKNOWN",
    "ROBOT_TF_UNVERIFIED": "UNKNOWN",
    "PLANNING_DATA_OK": "READY",
    "SONY_UNVERIFIED": "UNKNOWN",
}


@dataclass(frozen=True)
class Observation:
    reason: str
    observed_at: float

    @property
    def state(self):
        return REASONS[self.reason]


def fresh(stamp, now, age=EVIDENCE_AGE):
    return (type(stamp) in (int, float) and math.isfinite(stamp)
            and 0 < stamp <= now and now - stamp <= age)


def header_stamp(message):
    try:
        stamp = message.header.stamp
        if type(stamp.sec) is not int or type(stamp.nanosec) is not int or not 0 <= stamp.nanosec < 10**9:
            return None
        return stamp.sec + stamp.nanosec / 10**9
    except AttributeError:
        return None


def joints(message, now):
    """Retain only current seven-axis metadata; no synthetic zero positions."""
    try:
        stamp = header_stamp(message)
        names = tuple(message.name)
        positions = tuple(message.position)
        if (not fresh(stamp, now) or len(names) != 7 or set(names) != set(JOINTS)
                or len(positions) != 7 or not all(math.isfinite(p) for p in positions)):
            return None
        return stamp, tuple(positions[names.index(name)] for name in JOINTS)
    except (AttributeError, TypeError, ValueError):
        return None


def level(status):
    value = status.level
    # ROS Jazzy exposes the uint8 level as a one-byte bytes object on ARM64.
    if isinstance(value, bytes) and len(value) == 1:
        value = value[0]
    return value if type(value) is int and value in (0, 1, 2, 3) else None


def values(status):
    pairs = [(v.key, v.value) for v in status.values]
    if len(pairs) > 64 or len(dict(pairs)) != len(pairs):
        raise ValueError("invalid diagnostic keys")
    return dict(pairs)


def arm(message, now):
    """Use the source timestamp and exact arm diagnostic, not DDS reception time."""
    try:
        stamp = header_stamp(message)
        if not fresh(stamp, now) or len(message.status) != 1:
            return None
        status = message.status[0]
        if status.name != "arm" or status.hardware_id != "can0:arm":
            return None
        fields = values(status)
        code = int(fields["arm_status"])
        errors = int(fields["err_status"])
        diagnostic = level(status)
        if diagnostic is None or diagnostic == 3 or code < 0 or errors < 0:
            return None
        if code == 6:
            return stamp, "ARM_BRAKE_NOT_RELEASED"
        if diagnostic in (1, 2) or code != 0 or errors != 0:
            return stamp, "ARM_FAULT"
        for field in ("joint_angle_limit", "communication_status_joint"):
            flags = json.loads(fields[field])
            if not isinstance(flags, list) or len(flags) != 7 or not all(type(v) is bool for v in flags):
                return None
            if any(flags):
                return stamp, "ARM_FAULT"
        return stamp, "NERO_TELEMETRY_OK"
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def motors(message, now):
    try:
        stamp = header_stamp(message)
        if not fresh(stamp, now) or len(message.status) != 7:
            return None
        rows = {s.name:s for s in message.status}
        if set(rows) != set(JOINTS):
            return None
        enabled = []
        for i, name in enumerate(JOINTS, 1):
            status = rows[name]
            if status.hardware_id != f"can0:{i}":
                return None
            diagnostic = level(status)
            if diagnostic in (1, 2):
                return stamp, "ARM_FAULT"
            if diagnostic != 0:
                return None
            flag = values(status).get("enabled")
            if flag not in ("true", "false"):
                return None
            enabled.append(flag == "true")
        return stamp, "NERO_TELEMETRY_OK" if all(enabled) else "MOTORS_NOT_ENABLED"
    except (AttributeError, TypeError, ValueError):
        return None


def nero_observation(joint, arm_status, motor_status, now):
    # A fresh explicit fault is meaningful even when other telemetry is missing.
    for evidence in (arm_status, motor_status):
        if evidence and fresh(evidence[0], now) and REASONS[evidence[1]] == "NOT_READY":
            return Observation(evidence[1], evidence[0])
    for evidence, missing in ((joint, "JOINT_FEEDBACK_UNVERIFIED"),
                              (arm_status, "ARM_STATUS_UNVERIFIED"),
                              (motor_status, "MOTOR_STATUS_UNVERIFIED")):
        if not evidence or not fresh(evidence[0], now):
            return Observation(missing, now)
    return Observation("NERO_TELEMETRY_OK", min(joint[0], arm_status[0], motor_status[0]))


def rgbd_observation(rgb, depth, now):
    if (not fresh(rgb, now) or not fresh(depth, now) or abs(rgb-depth) > 0.5):
        return Observation("RGBD_UNVERIFIED", now)
    return Observation("RGBD_STREAMS_OK", min(rgb, depth))


def planning_observation(joint, scene, tf_stamp, now):
    if not joint or not fresh(joint[0], now):
        return Observation("JOINT_FEEDBACK_UNVERIFIED", now)
    if (not scene or not fresh(scene[0], now)
            or any(abs(a-b)>0.05 for a,b in zip(joint[1],scene[1]))):
        return Observation("SCENE_UNVERIFIED", now)
    if not fresh(tf_stamp, now):
        return Observation("ROBOT_TF_UNVERIFIED", now)
    return Observation("PLANNING_DATA_OK", min(joint[0], scene[0], tf_stamp))


_SOURCE_REASONS = {
    "nero": {"JOINT_FEEDBACK_UNVERIFIED", "ARM_STATUS_UNVERIFIED", "ARM_BRAKE_NOT_RELEASED",
             "ARM_FAULT", "MOTOR_STATUS_UNVERIFIED", "MOTORS_NOT_ENABLED", "NERO_TELEMETRY_OK"},
    "oak": {"RGBD_UNVERIFIED", "RGBD_STREAMS_OK"},
    "oak800": {"RGBD_UNVERIFIED", "RGBD_STREAMS_OK"},
    "moveit": {"JOINT_FEEDBACK_UNVERIFIED", "SCENE_UNVERIFIED", "ROBOT_TF_UNVERIFIED", "PLANNING_DATA_OK"},
}


def write_snapshot(path, observations, now):
    """Atomic private metadata file. No raw ROS messages cross this boundary."""
    path = Path(path)
    body = json.dumps({"schema": SCHEMA, "capturedAt": now, "sources": {
        key: {"reason": value.reason, "observedAt": value.observed_at}
        for key,value in observations.items()}}, allow_nan=False, separators=(",", ":"))
    if len(body) > MAX_BYTES:
        raise ValueError("oversized readiness snapshot")
    fd, name = tempfile.mkstemp(prefix=".readiness-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(body)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_snapshot(path, now):
    if path is None:
        return {}
    try:
        # Reject symlinks, non-regular files, other owners and shared permissions.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_BYTES):
                return {}
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return {}
        body = json.loads(raw)
        if (type(body) is not dict or set(body) != {"schema","capturedAt","sources"}
                or body["schema"] != SCHEMA or not fresh(body["capturedAt"],now,SNAPSHOT_AGE)
                or type(body["sources"]) is not dict or set(body["sources"]) != set(SOURCES)):
            return {}
        result = {}
        for key, value in body["sources"].items():
            if (type(value) is not dict or set(value) != {"reason","observedAt"}
                    or value["reason"] not in _SOURCE_REASONS[key]
                    or not fresh(value["observedAt"],now,SNAPSHOT_AGE)
                    or value["observedAt"] > body["capturedAt"]):
                continue
            result[key] = Observation(value["reason"], value["observedAt"])
        return result
    except (OSError, ValueError, TypeError):
        return {}


def valid_reason(device, reason, readiness):
    if not isinstance(reason,str) or REASONS.get(reason) != readiness:
        return False
    common = {"SERVICE_INACTIVE","SERVICE_UNKNOWN","USB_MISSING","OBSERVER_UNAVAILABLE"}
    specific = {
        "nero": _SOURCE_REASONS["nero"],
        "luxonis": _SOURCE_REASONS["oak"] | {"AMBIGUOUS_SCENE"},
        "moveit": _SOURCE_REASONS["moveit"] | {"AMBIGUOUS_SCENE"},
        "sony": {"SONY_UNVERIFIED"},
    }
    return device in specific and reason in (common | specific[device])


def device_observation(device, availability, hardware, observations, active_scenes, now):
    """Combine service facts with observer evidence, never authorize operation."""
    if availability == "INACTIVE":
        return Observation("SERVICE_INACTIVE",now)
    if device == "sony":
        return Observation("SONY_UNVERIFIED",now)
    if availability != "ACTIVE":
        return Observation("SERVICE_UNKNOWN",now)
    if hardware in ("USB_NOT_DETECTED", "USB_CAN_NOT_DETECTED"):
        return Observation("USB_MISSING",now)
    if device in ("luxonis","moveit") and len(active_scenes) != 1:
        return Observation("AMBIGUOUS_SCENE",now)
    key = active_scenes[0] if device == "luxonis" else device
    evidence = observations.get(key)
    return evidence if evidence and fresh(evidence.observed_at,now,SNAPSHOT_AGE) else Observation("OBSERVER_UNAVAILABLE",now)
