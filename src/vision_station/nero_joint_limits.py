"""Read-only comparison to the installed SDK and official MoveIt model.

Verified on VENTUNO 2026-11-27: pyAgxArm NeroFW.V121 (firmware 1.22),
AgileX agx_arm_ros revision 5051114, generated NERO URDF, group arm.
These are software model reference limits, not measured mechanical stops
or firmware configuration readback. Do not infer physical readiness from
an in-range result, or enlarge these limits to admit an out-of-range state.
"""
import math
from .nero import fresh

REFERENCE = "NERO_V121_5051114"
SDK = (
    (-2.705261, 2.705261), (-1.74533, 1.74533),
    (-2.757621, 2.757621), (-1.012291, 2.146755),
    (-2.757621, 2.757621), (-.733039, .872665),
    (-1.570797, 1.570797),
)
MODEL = (
    (-2.70526, 2.70526), (-1.74, 1.74),
    (-2.75, 2.75), (-1.01, 2.14),
    (-2.75, 2.75), (-.7330383, .8726646),
    (-1.5707963, 1.5707963),
)
STATES = ("UNKNOWN", "WITHIN_LIMITS", "OUTSIDE_LIMITS")

def finite(v):
    return type(v) in (int,float) and math.isfinite(v)

def classify(q, sdk, model):
    if q is None:return "UNKNOWN"
    return "WITHIN_LIMITS" if max(sdk[0],model[0])<=q<=min(sdk[1],model[1]) else "OUTSIDE_LIMITS"

def overall(rows):
    states=[r["state"] for r in rows]
    return "OUTSIDE_LIMITS" if "OUTSIDE_LIMITS" in states else "UNKNOWN" if "UNKNOWN" in states else "WITHIN_LIMITS"

def project(packet, now):
    stamp=None
    positions=[None]*7
    if packet is not None and fresh(packet["stamp"],now) and len(packet["rows"])==7:
        stamp=packet["stamp"]
        positions=[r["positionRad"] for r in packet["rows"]]
    rows=[{"joint":f"joint{i}","positionRad":q,"sdkRad":list(sdk),"modelRad":list(model),
           "state":classify(q,sdk,model)}
          for i,(q,sdk,model) in enumerate(zip(positions,SDK,MODEL),1)]
    return {"reference":REFERENCE,"stamp":stamp,"state":overall(rows),"rows":rows}

def validate(v, now):
    try:
        if (type(v) is not dict or set(v)!={"reference","stamp","state","rows"}
                or v["reference"]!=REFERENCE or v["state"] not in STATES
                or type(v["rows"]) is not list or len(v["rows"])!=7):
            return False
        stamp=v["stamp"]
        if stamp is not None and not fresh(stamp,now):return False
        for i,(r,sdk,model) in enumerate(zip(v["rows"],SDK,MODEL),1):
            if (type(r) is not dict or set(r)!={"joint","positionRad","sdkRad","modelRad","state"}
                    or r["joint"]!=f"joint{i}" or r["sdkRad"]!=list(sdk) or r["modelRad"]!=list(model)):
                return False
            q=r["positionRad"]
            if stamp is None:
                if q is not None:return False
            elif not finite(q) or abs(q)>100:return False
            if r["state"]!=classify(q,sdk,model):return False
        return v["state"]==overall(v["rows"])
    except (KeyError,TypeError,ValueError,OverflowError):return False
