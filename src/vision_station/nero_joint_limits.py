"""Read-only, source-derived NERO software joint limits.

Never instantiate or connect an arm in the Core. The installed SDK factory
configuration is a software reference, not a query of the actual firmware.
The URDF is the configured manufacturer's installed description, not evidence
of the commissioned Servo planning scene. No PARK target or embedded joint
limits are used here.
"""
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .nero import fresh

JOINTS=tuple(f"joint{i}" for i in range(1,8))
STATES=("UNKNOWN","WITHIN_LIMITS","OUTSIDE_LIMITS")
MAX_MODEL_BYTES=1024*1024
TOKEN=re.compile(r"[A-Za-z0-9_.+-]{1,64}\Z")


def finite(v):
    return type(v) in (int,float) and math.isfinite(v)


def valid_pair(v):
    return (isinstance(v,(list,tuple)) and len(v)==2 and
            all(finite(x) and abs(x)<=100 for x in v) and v[0]<v[1])


def sdk_bounds(config):
    if config.get("robot")!="nero":raise ValueError("NERO SDK configuration required")
    limits=config["joint_limits"]
    if type(limits) is not dict or set(limits)!=set(JOINTS) or not all(valid_pair(x) for x in limits.values()):
        raise ValueError("invalid SDK joint limits")
    return tuple(tuple(limits[n]) for n in JOINTS)


def model_bounds(xml):
    """Read the actual expanded URDF, or the installed plain NERO URDF."""
    if isinstance(xml,str):xml=xml.encode("utf-8")
    if (not isinstance(xml,bytes) or not 0<len(xml)<=MAX_MODEL_BYTES
            or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper()):
        raise ValueError("invalid bounded URDF")
    root=ET.fromstring(xml)
    if root.tag!="robot":raise ValueError("expected URDF robot")
    joints={}
    for j in root.findall("joint"):
        name=j.get("name")
        if name not in JOINTS:continue
        if name in joints or j.get("type")!="revolute" or len(j.findall("limit"))!=1:
            raise ValueError("ambiguous NERO model joint")
        limit=j.find("limit")
        bounds=(float(limit.attrib["lower"]),float(limit.attrib["upper"]))
        if not valid_pair(bounds):raise ValueError("invalid URDF joint limits")
        joints[name]=bounds
    if set(joints)!=set(JOINTS):raise ValueError("incomplete URDF limits")
    return tuple(joints[n] for n in JOINTS)


def intersection(sdk,model):
    if len(sdk)!=7 or len(model)!=7 or not all(valid_pair(r) for r in (*sdk,*model)):
        raise ValueError("invalid reference limits")
    bounds=tuple((max(s[0],m[0]),min(s[1],m[1])) for s,m in zip(sdk,model))
    if not all(valid_pair(b) for b in bounds):raise ValueError("incompatible joint limits")
    return bounds


def valid_source(v):
    return (type(v) is dict and set(v)=={"sdkVersion","firmwareProfile","modelSha256"}
            and all(isinstance(v[k],str) and TOKEN.fullmatch(v[k]) for k in ("sdkVersion","firmwareProfile"))
            and isinstance(v["modelSha256"],str) and re.fullmatch(r"[a-f0-9]{64}",v["modelSha256"]) is not None)


@dataclass(frozen=True)
class Reference:
    sdk:tuple
    model:tuple
    sdk_version:str
    firmware_profile:str
    model_sha256:str

    def __post_init__(self):
        intersection(self.sdk,self.model)
        if not valid_source(self.source()):raise ValueError("invalid provenance")

    def source(self):
        return {"sdkVersion":self.sdk_version,"firmwareProfile":self.firmware_profile,"modelSha256":self.model_sha256}


class InstalledJointLimits:
    """Explicit installed model path and selected SDK firmware profile.

    Reload on each report, so a model update or loss is visible rather than
    silently using last-known hardcoded limits. No I/O to CAN or ROS here.
    """
    def __init__(self,urdf,profile):
        self.urdf=Path(urdf)
        if not self.urdf.is_absolute() or not isinstance(profile,str) or TOKEN.fullmatch(profile) is None:
            raise ValueError("explicit absolute URDF and SDK firmware profile required")
        self.profile=profile

    def __call__(self):
        from pyAgxArm import ArmModel,NeroFW,create_agx_arm_config
        allowed={v for k,v in vars(NeroFW).items() if not k.startswith("_") and isinstance(v,str)}
        if self.profile not in allowed:raise ValueError("unsupported NERO SDK profile")
        cfg=create_agx_arm_config(robot=ArmModel.NERO,firmeware_version=self.profile)
        # Factory configuration only; no AgxArmFactory.create_arm/connect.
        if str(cfg["firmeware_version"])!=self.profile:raise ValueError("SDK profile mismatch")
        path=self.urdf.resolve(strict=True)
        if not path.is_file():raise ValueError("URDF must be a regular file")
        with path.open("rb") as f:xml=f.read(MAX_MODEL_BYTES+1)
        return Reference(sdk_bounds(cfg),model_bounds(xml),version("pyAgxArm"),
                         self.profile,hashlib.sha256(xml).hexdigest())


def classify(q,sdk,model):
    if q is None or sdk is None or model is None:return "UNKNOWN"
    return "WITHIN_LIMITS" if max(sdk[0],model[0])<=q<=min(sdk[1],model[1]) else "OUTSIDE_LIMITS"


def overall(rows):
    states=[r["state"] for r in rows]
    return "OUTSIDE_LIMITS" if "OUTSIDE_LIMITS" in states else "UNKNOWN" if "UNKNOWN" in states else "WITHIN_LIMITS"


def project(packet,now,reference=None):
    stamp=None;positions=[None]*7
    if packet is not None and fresh(packet["stamp"],now) and len(packet["rows"])==7:
        stamp=packet["stamp"];positions=[r["positionRad"] for r in packet["rows"]]
    sdk=reference.sdk if reference is not None else (None,)*7
    model=reference.model if reference is not None else (None,)*7
    rows=[{"joint":name,"positionRad":q,"sdkRad":list(s) if s is not None else None,
           "modelRad":list(m) if m is not None else None,"state":classify(q,s,m)}
          for name,q,s,m in zip(JOINTS,positions,sdk,model)]
    return {"reference":reference.source() if reference is not None else None,
            "stamp":stamp,"state":overall(rows),"rows":rows}


def validate(v,now):
    try:
        if (type(v) is not dict or set(v)!={"reference","stamp","state","rows"}
                or v["state"] not in STATES or type(v["rows"]) is not list or len(v["rows"])!=7):return False
        source=v["reference"]
        if source is not None and not valid_source(source):return False
        stamp=v["stamp"]
        if stamp is not None and not fresh(stamp,now):return False
        for name,r in zip(JOINTS,v["rows"]):
            if (type(r) is not dict or set(r)!={"joint","positionRad","sdkRad","modelRad","state"}
                    or r["joint"]!=name):return False
            s,m=r["sdkRad"],r["modelRad"]
            if source is None:
                if s is not None or m is not None:return False
            elif not valid_pair(s) or not valid_pair(m) or max(s[0],m[0])>=min(s[1],m[1]):return False
            q=r["positionRad"]
            if stamp is None:
                if q is not None:return False
            elif not finite(q) or abs(q)>100:return False
            if r["state"]!=classify(q,s,m):return False
        return v["state"]==overall(v["rows"])
    except (KeyError,TypeError,ValueError,OverflowError):return False
