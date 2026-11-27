"""Cartesian teleoperation intent and read-only station projection.

No actuator client. The vector conversion is used by the isolated MoveIt
Servo integration test. Actual commissioning must connect the existing
guarded owner, not introduce another CAN writer.
"""
import math

from .nero import fresh, validate_nero_report
from .nero_clear import valid_id
from .nero_joint_limits import project as joint_check, validate as validate_joint_check

SCHEMA = "vision.api.nero-tcp.v1"
FRAMES = {"BASE": "base_link", "TOOL": "tcp_link"}
AXES = ("X", "Y", "Z", "ROLL", "PITCH", "YAW")
SPEEDS = {"linearMin": 1, "linearMax": 100, "angularMin": 1, "angularMax": 30}
DEFAULTS = {"linearMmS": 10, "angularDegS": 5}


def validate_declaration(value):
    return (type(value) is dict and set(value) == {"frame", "linearMmS", "angularDegS"}
            and isinstance(value["frame"], str) and value["frame"] in FRAMES
            and type(value["linearMmS"]) is int
            and SPEEDS["linearMin"] <= value["linearMmS"] <= SPEEDS["linearMax"]
            and type(value["angularDegS"]) is int
            and SPEEDS["angularMin"] <= value["angularDegS"] <= SPEEDS["angularMax"])


def twist_intent(declaration, axis, direction):
    """Convert declared human units to SI units, no I/O or IK.

    This describes a single-axis velocity request, not a duration, position
    setpoint or guarantee of actual speed. The real owner must independently
    admit it, constrain it and enforce a local deadman/watchdog.
    """
    if (not validate_declaration(declaration) or axis not in AXES
            or type(direction) is not int or direction not in (-1, 1)):
        raise ValueError("invalid TCP intent")
    linear, angular = [0.] * 3, [0.] * 3
    i = AXES.index(axis)
    if i < 3:
        linear[i] = direction * declaration["linearMmS"] / 1000
    else:
        angular[i - 3] = direction * math.radians(declaration["angularDegS"])
    return {"frameId": FRAMES[declaration["frame"]], "linear": linear, "angular": angular}


def project(telemetry):
    now = telemetry["capturedAt"]
    drives = [None] * 7
    joints = None
    if validate_nero_report(telemetry) and telemetry["graph"] == "ACTIVE" and telemetry["observer"] == "ACTIVE":
        joints = telemetry["joints"]
        packet = telemetry["motors"]
        if packet and fresh(packet["stamp"], now):
            for i, motor in enumerate(packet["rows"]):
                raw=motor["rawStatus"]
                if motor["level"] != 3 and raw is not None and motor["enabled"] is bool(raw & 0x40):
                    drives[i] = motor["enabled"]
    return {"schema": SCHEMA, "source": "STATION", "instanceId": telemetry["instanceId"],
            "capturedAt": now, "driveEnabled": drives, "jointCheck": joint_check(joints, now),
            "mode": "LOCKED", "reason": "NOT_COMMISSIONED",
            "servoState": "NOT_CONNECTED",
            "capabilities": {"enable": False, "jog": False, "hold": False},
            "speedLimits": dict(SPEEDS), "defaults": dict(DEFAULTS),
            "frames": list(FRAMES),
            # Not derived from joint-speed magnitude; needs TCP TF/Jacobian
            # with the commissioned tool transform and fresh feedback.
            "actualTcp": None}


def validate_report(v):
    try:
        return (type(v) is dict and set(v) == {"schema","source","instanceId","capturedAt","driveEnabled","mode","reason","servoState","capabilities","speedLimits","defaults","frames","actualTcp","jointCheck"}
                and v["schema"] == SCHEMA and v["source"] == "STATION" and valid_id(v["instanceId"])
                and fresh(v["capturedAt"], v["capturedAt"])
                and type(v["driveEnabled"]) is list and len(v["driveEnabled"]) == 7
                and all(x is None or type(x) is bool for x in v["driveEnabled"])
                and validate_joint_check(v["jointCheck"],v["capturedAt"])
                and v["mode"] == "LOCKED" and v["reason"] == "NOT_COMMISSIONED"
                and v["servoState"] == "NOT_CONNECTED"
                and type(v["capabilities"]) is dict
                and set(v["capabilities"]) == {"enable", "jog", "hold"}
                and all(x is False for x in v["capabilities"].values())
                and v["speedLimits"] == SPEEDS and v["defaults"] == DEFAULTS
                and v["frames"] == list(FRAMES) and v["actualTcp"] is None)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
