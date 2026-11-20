"""Pure policy for ONE bounded NERO FollowJointTrajectory laboratory step.

The first physical integration only admits joint2 <= 2 degrees, with all
six other joints fixed. Full MoveIt trajectories (and MoveJS) are prohibited.
This module does not open ROS, CAN or motor control. It is not safety-rated.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

JOINTS=tuple(f"joint{i}" for i in range(1,8))
# Reference manufacturer URDF: nero_description.urdf, NOT approximate SDK limits.
URDF_LIMITS_RAD=(
 (-2.70526,2.70526),(-1.74533,1.74533),
 (-2.75762,2.75762),(-1.01,2.147),
 (-2.75762,2.75762),(-0.733038,0.872665),
 (-1.5707963,1.5707963)
)

class RejectGoal(ValueError):
    pass

@dataclass(frozen=True)
class Step:
    start:tuple[float,...]
    target:tuple[float,...]
    joint:str
    delta_deg:float
    planned_duration_s:float
    permitted_speed_percent:int=3

def validate_step(
    joint_names,points,current_q, *,
    allowed_joint="joint2", max_deg=2.0, speed_percent=3
)->Step:
    if tuple(joint_names)!=JOINTS:
        raise RejectGoal("JOINT_NAMES_MISSING_OR_REORDERED")
    if len(points)!=2:
        raise RejectGoal("EXACTLY_TWO_WAYPOINTS_REQUIRED")
    if len(current_q)!=7 or not all(math.isfinite(v) for v in current_q):
        raise RejectGoal("NO_FINITE_CURRENT_JOINTS")
    start=tuple(float(x) for x in points[0][0])
    end=tuple(float(x) for x in points[1][0])
    if len(start)!=7 or len(end)!=7 or not all(math.isfinite(v) for v in start+end):
        raise RejectGoal("POSITION_LENGTH_OR_NONFINITE")
    t0,t1=float(points[0][1]),float(points[1][1])
    if abs(t0)>0.001 or not (4.0<=t1<=30.0) or not math.isfinite(t1):
        raise RejectGoal("INVALID_TIMING")
    if not (1<=int(speed_percent)<=3):
        raise RejectGoal("SPEED_GREATER_THAN_3_PERCENT")
    if any(abs(math.degrees(a-b))>0.15 for a,b in zip(start,current_q)):
        raise RejectGoal("START_NOT_LIVE_JOINT_POSITION")
    # Joint position must remain a full one degree inside vendor URDF limits.
    clearance=math.radians(1.0)
    for q,(lo,hi) in zip(end,URDF_LIMITS_RAD):
        if not (lo+clearance<q<hi-clearance):
            raise RejectGoal("TARGET_TOO_CLOSE_TO_VENDOR_JOINT_LIMIT")
    for q,(lo,hi) in zip(start,URDF_LIMITS_RAD):
        if not (lo<q<hi):
            raise RejectGoal("START_OUTSIDE_VENDOR_JOINT_LIMIT")
    moved=[(j,math.degrees(b-a)) for j,a,b in zip(JOINTS,start,end)
            if abs(math.degrees(b-a))>0.025]
    if len(moved)!=1 or moved[0][0]!=allowed_joint:
        raise RejectGoal("ONE_APPROVED_JOINT_ONLY")
    joint,delta=moved[0]
    if not (0.20<=abs(delta)<=max_deg):
        raise RejectGoal("DISPLACEMENT_OUTSIDE_0.2_TO_2.0_DEGREES")
    if any(abs(math.degrees(b-a))>0.025 for j,a,b in zip(JOINTS,start,end)
           if j!=allowed_joint):
        raise RejectGoal("NON_TARGET_JOINT_CHANGED")
    return Step(start,end,joint,delta,t1,int(speed_percent))

def check_feedback(q,velocity,status,error_mask,ctrl_mode,motors_enabled,
                   *,timestamp_age_s,expected_start=None,accepted_delta_deg=2.0):
    if status!="NORMAL" or error_mask or ctrl_mode!="CAN_CTRL":
        raise RejectGoal("FIRMWARE_NOT_NORMAL_CAN_CONTROL")
    if len(motors_enabled)!=7 or not all(motors_enabled):
        raise RejectGoal("ALL_SEVEN_DRIVES_REQUIRED_ENABLED")
    if timestamp_age_s<0 or timestamp_age_s>.15:
        raise RejectGoal("STALE_JOINT_FEEDBACK")
    if len(q)!=7 or len(velocity)!=7 or not all(math.isfinite(v) for v in list(q)+list(velocity)):
        raise RejectGoal("INVALID_SENSOR_FEEDBACK")
    if any(abs(v)>.5 for v in velocity):
        raise RejectGoal("ROBOT_VELOCITY_EXCEEDED_FAIL_CLOSED")
    if expected_start is not None:
        # All joints except joint2 must remain within 0.4 deg of starting pose.
        if any(abs(math.degrees(a-b))>.4 for i,(a,b) in enumerate(zip(q,expected_start))
               if i!=1):
            raise RejectGoal("UNCOMMANDED_NON_J2_MOVEMENT")
        if abs(math.degrees(q[1]-expected_start[1]))>accepted_delta_deg+.4:
            raise RejectGoal("JOINT2_EXCEEDS_ONE_SEGMENT_TRAVEL")
    return True

def converged(q,velocity,target):
    return len(q)==7 and len(velocity)==7 and (
        max(abs(math.degrees(a-b)) for a,b in zip(q,target))<.15
        and max(abs(v) for v in velocity)<.045)
