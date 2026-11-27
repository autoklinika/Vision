"""Locked, time-aware adapter from MoveIt Servo to the NERO guarded arbiter.

No publisher to a hardware control topic, SDK call, enable, or execution path.
The conversion is a candidate for the existing owner's admission check.
It is not a trajectory controller: no interpolation or retiming of Servo
output is performed. A future execution transport must preserve timing.
"""
from dataclasses import dataclass
import math
from threading import RLock

JOINTS=tuple(f"joint{i}" for i in range(1,8))
MAX_POINTS=64
# Bounds for the offline / shadow protocol, not accepted motion limits.
MAX_HORIZON_NS=500_000_000
MAX_HEADER_AGE_NS=300_000_000
MAX_FUTURE_HEADER_NS=50_000_000
NANO=1_000_000_000
REASONS=("FORMAT","JOINT_NAMES","NONFINITE","TIME_ORDER","HORIZON",
         "STALE","FUTURE","EXPIRED","REPLAY","SOURCE_CHANGED",
         "GUARD_UNAVAILABLE","GUARD_LOCKED")


class CandidateRejected(ValueError):
    pass


def _ns(value, *, duration=False):
    sec=value.sec;nano=value.nanosec
    if type(sec) is not int or type(nano) is not int or not 0<=nano<NANO or sec<0:
        raise CandidateRejected("FORMAT")
    ns=sec*NANO+nano
    if not duration and ns<=0:raise CandidateRejected("STALE")
    return ns


def _vector(values, order, *, optional=False):
    if optional and not values:return ()
    if len(values)!=7:raise CandidateRejected("FORMAT")
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise CandidateRejected("NONFINITE")
    return tuple(float(values[i]) for i in order)


@dataclass(frozen=True)
class TimedPoint:
    at_ns:int
    positions:tuple
    velocities:tuple
    accelerations:tuple


@dataclass(frozen=True)
class Candidate:
    stamp_ns:int
    points:tuple

    @property
    def end_ns(self):return self.points[-1].at_ns

    def first_future(self,now_ns):
        return next((p for p in self.points if p.at_ns>now_ns),None)


def decode_candidate(message,now_ns):
    """Validate actual Servo JointTrajectory, retaining every absolute time."""
    if type(now_ns) is not int or now_ns<=0:raise CandidateRejected("FORMAT")
    try:
        names=tuple(message.joint_names)
        if len(names)!=7 or set(names)!=set(JOINTS):raise CandidateRejected("JOINT_NAMES")
        order=tuple(names.index(j) for j in JOINTS)
        # Servo joint-space output has an empty frame; accept the explicitly
        # documented model frame as well, not arbitrary spatial transforms.
        if message.header.frame_id not in ("","base_link"):raise CandidateRejected("FORMAT")
        stamp=_ns(message.header.stamp)
        if stamp-now_ns>MAX_FUTURE_HEADER_NS:raise CandidateRejected("FUTURE")
        if now_ns-stamp>MAX_HEADER_AGE_NS:raise CandidateRejected("STALE")
        if not 1<=len(message.points)<=MAX_POINTS:raise CandidateRejected("FORMAT")
        points=[];previous=-1
        for p in message.points:
            dt=_ns(p.time_from_start,duration=True)
            if dt<=previous:raise CandidateRejected("TIME_ORDER")
            if dt>MAX_HORIZON_NS:raise CandidateRejected("HORIZON")
            if p.effort:raise CandidateRejected("FORMAT")
            points.append(TimedPoint(stamp+dt,_vector(p.positions,order),
                        _vector(p.velocities,order,optional=True),
                        _vector(p.accelerations,order,optional=True)))
            previous=dt
        candidate=Candidate(stamp,tuple(points))
        if candidate.first_future(now_ns) is None:raise CandidateRejected("EXPIRED")
        return candidate
    except CandidateRejected:raise
    except (TypeError,AttributeError,KeyError,ValueError,OverflowError):
        raise CandidateRejected("FORMAT") from None


@dataclass(frozen=True)
class BridgeVerdict:
    # accepted_format means valid time window, NEVER permission to actuate.
    accepted_format:bool
    reason:str
    guard_reason:str|None=None
    candidate:Candidate|None=None
    can_execute:bool=False


class LockedBridge:
    """Source-pinned admission adapter. Always read-only, including success.

    Existing arbiter is injected by the sole guarded owner. Guard state
    changes (including HOLD) are not implemented here or overridden.
    """
    def __init__(self,arbiter,feedback):
        self.arbiter,self.feedback=arbiter,feedback
        self._lock=RLock()
        self._source=None
        self._last_end=0

    def assess(self,message,now_ns,source):
        with self._lock:
            if source is None:return BridgeVerdict(False,"SOURCE_CHANGED")
            if self._source is None:self._source=source
            if source!=self._source:return BridgeVerdict(False,"SOURCE_CHANGED")
            try:c=decode_candidate(message,now_ns)
            except CandidateRejected as e:return BridgeVerdict(False,str(e))
            if c.end_ns<=self._last_end:return BridgeVerdict(False,"REPLAY")
            p=c.first_future(now_ns)
            try:
                f=self.feedback()
                # Use exactly the existing guarded arbiter's contract.
                # Even a permissive/future arbiter cannot make this bridge
                # actuate; the returned can_execute is unconditionally False.
                answer=self.arbiter.classify_setpoint(JOINTS,p.positions,
                    arm_status=f["arm_status"],firmware_error_mask=f["firmware_error_mask"],
                    feedback_stamp=f["feedback_stamp"],now=now_ns/NANO)
                reason=answer.reason
            except Exception:return BridgeVerdict(True,"GUARD_UNAVAILABLE",candidate=c)
            self._last_end=c.end_ns
            return BridgeVerdict(True,"GUARD_LOCKED",guard_reason=reason,candidate=c)
