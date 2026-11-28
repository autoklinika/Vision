"""Stationary start synchronization for the virtual JTC only.

No physical setpoint, home/park target, CAN operation, or runtime launch.
A fresh stationary measurement is the input, never a desired robot pose.
The owner must independently verify current SDK feedback and JTC readback
before admitting manual commands. Historical replays cannot authorize it.
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from .nero_manual import AGE, JOINTS, Feedback, Profile, finite, vector7
from .nero_manual_station import xml_root, only, check_interpolator

# Same stationary position/velocity envelope as the existing settled check.
POSITION_ERROR=.001
VELOCITY_ERROR=.01
CONTROLLER_AGE=.10


@dataclass(frozen=True)
class StationarySeed:
    first_stamp: float
    stamp: float
    q: tuple

    def valid(self, now, profile):
        return (isinstance(profile,Profile) and vector7(self.q)
                and finite(self.first_stamp) and finite(self.stamp)
                and 0<=now-self.stamp<=AGE
                and 0<self.stamp-self.first_stamp<=AGE
                and 0<=now-self.first_stamp<=AGE
                and profile.contains(self.q))


def live_seed(first, second, *, profile, now):
    """Two distinct, bounded, stationary SDK observations of the same arm.

    Does not command a motion or accept a previously saved seed file.
    """
    if not isinstance(profile,Profile) or not all(isinstance(f,Feedback) for f in (first,second)):
        raise ValueError("two actual SDK observations required")
    if not all(f.clean(now) and f.arm_status in (0,6)
               and (all(f.drives()) or not any(f.drives()))
               and profile.contains(f.q)
               and max(abs(x) for x in f.velocity)<=VELOCITY_ERROR
               for f in (first,second)):
        raise ValueError("fresh stationary observations required")
    if (first.drives()!=second.drives() or second.joint_stamp<=first.joint_stamp
            or second.stamp_min()<=first.stamp_min()
            or max(abs(a-b) for a,b in zip(first.q,second.q))>POSITION_ERROR):
        raise ValueError("stationary evidence changed or repeated")
    seed=StationarySeed(first.joint_stamp,second.joint_stamp,tuple(second.q))
    if not seed.valid(now,profile):
        raise ValueError("invalid initial-state evidence")
    return seed


def seed_virtual_model(urdf, q, profile):
    """Pure virtual model transform, also usable for explicit test replay.

    Preserve every factory moving joint and collision geometry. Only the
    initial value on the mock position state interfaces is replaced.
    """
    if not isinstance(profile,Profile) or not profile.contains(q):
        raise ValueError("invalid initial joint vector")
    check_interpolator(urdf.encode())
    root=xml_root(urdf.encode())
    ctrl=only(root,"ros2_control")
    for name,value in zip(JOINTS,q):
        joint=only(ctrl,f'joint[@name="{name}"]')
        state=only(joint,'state_interface[@name="position"]')
        initial=only(state,'param[@name="initial_value"]')
        initial.text=repr(float(value))
    return ET.tostring(root,encoding="unicode")


def initial_virtual_model(urdf, first, second, *, profile, now):
    """Build in memory from fresh SDK measurements, not historical poses."""
    seed=live_seed(first,second,profile=profile,now=now)
    return seed_virtual_model(urdf,seed.q,profile),seed


@dataclass(frozen=True)
class ControllerStart:
    stamp: float
    gid: bytes
    q: tuple
    reference: tuple
    velocity: tuple
    reference_velocity: tuple

    def matches(self, feedback, *, now, expected_gid):
        return (isinstance(feedback,Feedback) and feedback.clean(now)
                and finite(self.stamp) and 0<=now-self.stamp<=CONTROLLER_AGE
                and type(self.gid) is bytes and any(self.gid) and self.gid==expected_gid
                and all(vector7(x) for x in (self.q,self.reference,self.velocity,self.reference_velocity))
                and max(abs(x) for x in (*feedback.velocity,*self.velocity,*self.reference_velocity))<=VELOCITY_ERROR
                and all(abs(x-y)<=POSITION_ERROR
                        for q in (self.q,self.reference) for x,y in zip(q,feedback.q)))
