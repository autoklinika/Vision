"""Canonical NERO diagnostic catalog (PyAgxArm 1.0.0 / NeroFW.V121).

Hex values belong to distinct code families, not a common DTC namespace.
Severity is Vision policy, not a manufacturer motion authorization.
"""
from .nero import FLAGS, JOINTS, fresh, integer, validate_nero_report

SCHEMA = "vision.api.nero-diagnostics.v1"
CATALOG = "nero-v121-vision-v1"
ARM = {
    0: ("Normal", "INFO"),
    1: ("Emergency stop", "FAULT"),
    2: ("No solution", "WARNING"),
    3: ("Singularity", "WARNING"),
    4: ("Target exceeds limit", "WARNING"),
    5: ("Joint communication error", "FAULT"),
    6: ("Joint brakes not released", "WARNING"),
    7: ("Collision detected", "FAULT"),
    8: ("Teaching overspeed", "FAULT"),
    9: ("Joint status error", "FAULT"),
    10: ("Other arm error", "FAULT"),
    11: ("Teaching recording", "INFO"),
    12: ("Teaching execution", "INFO"),
    13: ("Teaching paused", "INFO"),
    14: ("Main controller overtemperature", "FAULT"),
    15: ("Brake resistor overtemperature", "FAULT"),
}
DRIVE = {
    1: ("Undervoltage", "FAULT"),
    2: ("Motor overtemperature", "FAULT"),
    4: ("Driver overcurrent", "FAULT"),
    8: ("Driver overtemperature", "FAULT"),
    16: ("Collision protection", "FAULT"),
    32: ("Driver error", "FAULT"),
    128: ("Stall protection", "FAULT"),
}
DRIVE_FAULT_MASK = 0xBF
SOURCES = ("ARM", *(f"J{i}" for i in range(1, 8)))
SEVERITIES = ("INFO", "WARNING", "FAULT", "UNKNOWN")
FAMILIES = ("ARM_STATUS", "ARM_MASK", "DRIVE_STATUS")
SCOPES = (("ARM", "ARM_STATUS"), *((s, "ARM_MASK") for s in SOURCES),
          *((s, "DRIVE_STATUS") for s in SOURCES[1:]))


def describe(source, family, code):
    if family == "ARM_STATUS" and source == "ARM" and integer(code, 255):
        return ARM.get(code, ("Unknown arm status", "UNKNOWN"))
    if family == "DRIVE_STATUS" and source in SOURCES[1:] and code in DRIVE:
        return DRIVE[code]
    if family == "ARM_MASK" and source in SOURCES:
        if source == "ARM" and code in (0x80, 0x8000):
            return "Reserved arm error bit", "UNKNOWN"
        if source != "ARM":
            i = int(source[1:]) - 1
            if code == 1 << i:
                return "Joint communication error", "FAULT"
            if code == 1 << (8 + i):
                return "Joint angle limit", "WARNING"
    raise ValueError("invalid diagnostic code")


def entry(source, family, code, stamp):
    description, severity = describe(source, family, code)
    return {"source": source, "family": family, "code": code,
            "hex": f"0x{code:0{4 if family == 'ARM_MASK' else 2}X}",
            "description": description, "severity": severity, "stamp": stamp}


def decode(report):
    """Return observed conditions plus valid coverage, independently per source.

    Missing/stale or inconsistent redundant fields never imply cleared faults.
    The V1 drive array timestamp is publication time, not individual CAN
    feedback time; use only for passive observations, NEVER to verify clears.
    """
    current, coverage = [], {}
    if not validate_nero_report(report) or report["graph"] != "ACTIVE" or report["observer"] != "ACTIVE":
        return current, coverage
    arm, motors = report["arm"], report["motors"]
    if arm:
        stamp, raw = arm["stamp"], arm["errorCode"]
        coverage["ARM", "ARM_STATUS"] = stamp
        current.append(entry("ARM", "ARM_STATUS", arm["armStatus"], stamp))
        # Installed SDK decodes communication bits 0..6, angle bits 8..14.
        if (arm["communicationFault"] == [bool(raw & (1 << i)) for i in range(7)]
                and arm["angleLimit"] == [bool(raw & (1 << (8+i))) for i in range(7)]):
            for source in SOURCES:
                coverage[source, "ARM_MASK"] = stamp
            for i, source in enumerate(SOURCES[1:]):
                for bit in (i, i+8):
                    if raw & (1 << bit):
                        current.append(entry(source, "ARM_MASK", 1 << bit, stamp))
            for bit in (0x80, 0x8000):
                if raw & bit:
                    current.append(entry("ARM", "ARM_MASK", bit, stamp))
    if motors:
        stamp = motors["stamp"]
        for source, motor in zip(SOURCES[1:], motors["rows"]):
            raw = motor["rawStatus"]
            if motor["level"] == 3 or raw is None or motor["faults"] is None:
                continue
            if motor["enabled"] != bool(raw & 0x40) or any(
                    motor["faults"][name] != bool(raw & mask)
                    for name, mask in zip(FLAGS, DRIVE)):
                continue
            coverage[source, "DRIVE_STATUS"] = stamp
            for mask in DRIVE:
                if raw & mask:
                    current.append(entry(source, "DRIVE_STATUS", mask, stamp))
    return current, coverage


def validate_entry(value):
    try:
        return (type(value) is dict and set(value) == {"source","family","code","hex","description","severity","stamp"}
                and type(value["code"]) is int and fresh(value["stamp"], value["stamp"])
                and value == entry(value["source"], value["family"], value["code"], value["stamp"]))
    except (KeyError, TypeError, ValueError):
        return False


def validate_report(value):
    try:
        return (type(value) is dict and set(value) == {"schema","source","instanceId","catalog","capturedAt","current","coverage","historyAvailable","clearAvailable"}
                and value["schema"] == SCHEMA and value["source"] == "STATION" and value["catalog"] == CATALOG
                and isinstance(value["instanceId"],str) and len(value["instanceId"]) == 32
                and all(c in "0123456789abcdef" for c in value["instanceId"])
                and fresh(value["capturedAt"], value["capturedAt"])
                and type(value["historyAvailable"]) is bool and type(value["clearAvailable"]) is bool
                and type(value["current"]) is list and len(value["current"]) <= 66
                and all(validate_entry(e) and fresh(e["stamp"], value["capturedAt"]) for e in value["current"])
                and type(value["coverage"]) is list and len(value["coverage"]) <= len(SCOPES)
                and all(type(c) is dict and set(c) == {"source","family","stamp"}
                        and (c["source"],c["family"]) in SCOPES
                        and fresh(c["stamp"],value["capturedAt"]) for c in value["coverage"])
                and len({(c["source"],c["family"]) for c in value["coverage"]}) == len(value["coverage"])
                and all(any(e["source"]==c["source"] and e["family"]==c["family"] and e["stamp"]==c["stamp"]
                            for c in value["coverage"]) for e in value["current"]))
    except (KeyError, TypeError, ValueError):
        return False


def projection(report, *, history_available, clear_available=False):
    current, coverage = decode(report)
    return {"schema": SCHEMA, "source": "STATION", "instanceId": report["instanceId"],
            "catalog": CATALOG, "capturedAt": report["capturedAt"],
            "current": current, "coverage": [{"source": s,"family": f,"stamp": t}
                                               for (s,f),t in coverage.items()],
            "historyAvailable": history_available, "clearAvailable": clear_available}
