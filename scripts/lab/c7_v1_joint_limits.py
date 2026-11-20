"""Bound-corrected MoveIt LAB joint targets, without changing robot URDF or controllers.

Use exact vendor URDF bounds. Small numerical nudges at limits are allowed
only for OFFLINE planning, within strict maximum pose adjustment. Never
apply this normalization to physical encoder feedback or robot commands.
"""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET


class JointLimitError(ValueError):
    pass


def load_urdf_joint_limits(urdf: str | Path, names: list[str]) -> dict[str, tuple[float,float]]:
    root=ET.parse(urdf).getroot()
    joints={x.attrib.get("name"):x for x in root.findall("joint")}
    result={}
    for name in names:
        entry=joints.get(name)
        if entry is None or entry.attrib.get("type") != "revolute":
            raise JointLimitError(f"Expected revolute joint {name}")
        limit=entry.find("limit")
        if limit is None:
            raise JointLimitError(f"Missing joint limit {name}")
        low=float(limit.attrib["lower"]);high=float(limit.attrib["upper"])
        if not math.isfinite(low) or not math.isfinite(high) or low>=high:
            raise JointLimitError(f"Invalid bounds {name}")
        result[name]=(low,high)
    return result


def inset_at_limit(
    q: list[float],
    names: list[str],
    joint_limits: dict[str, tuple[float,float]],
    *,
    inset_rad: float=0.0001,
    max_adjustment_rad: float=math.radians(0.02)
) -> dict:
    """Return new joint angles strictly within bounds; refuse meaningful pose changes.

    For any q closer than inset to a URDF joint bound, nudge toward the
    interior by at most max_adjustment_rad. A pose clearly outside its
    limits is rejected, not clipped.
    """
    if not (0<inset_rad<max_adjustment_rad<.01):
        raise JointLimitError("Invalid inset/maximum adjustment")
    if len(q)!=len(names) or len(set(names))!=len(names):
        raise JointLimitError("Joint/angle mismatch")
    corrected=[];adjustments=[]
    for name,raw in zip(names,q):
        if name not in joint_limits or not math.isfinite(raw):
            raise JointLimitError(f"Unknown or nonfinite joint: {name}")
        lo,hi=joint_limits[name]
        if lo+inset_rad >= hi-inset_rad:
            raise JointLimitError(f"Joint range too narrow: {name}")
        lo_safe=lo+inset_rad
        hi_safe=hi-inset_rad
        val=min(max(float(raw),lo_safe),hi_safe)
        diff=val-float(raw)
        if abs(diff)>max_adjustment_rad:
            raise JointLimitError(f"Joint {name} outside safe adjustment: delta_deg={math.degrees(diff):.6f}")
        if not (lo<val<hi):
            raise JointLimitError(f"Joint {name} not strictly inside limits")
        corrected.append(val)
        if abs(diff)>1e-13:
            adjustments.append({"joint":name,
               "before_rad":float(raw),"after_rad":val,
               "delta_deg":math.degrees(diff),
               "vendor_lower_rad":lo,"vendor_upper_rad":hi})
    return {"corrected_q":corrected,"adjustments":adjustments,
            "max_abs_delta_deg":max((abs(a["delta_deg"]) for a in adjustments),default=0.0),
            "changed":bool(adjustments),
            "offline_only":True,"preserves_vendor_joint_limits":True}
