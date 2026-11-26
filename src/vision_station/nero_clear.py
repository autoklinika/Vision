"""Bounded clear state machine. No direct CAN opens; injected owner only.

The SDK has no clear acknowledgement. CLEARED denotes observed disappearance,
not proof of causal acknowledgement or permission to move.
"""
from dataclasses import dataclass
import math
import re
import threading
import time

from .nero_diagnostics import DRIVE_FAULT_MASK
from .nero import fresh, integer

SCOPES = (*range(1,8),255)
RESULTS = ("CLEARED","PARTIAL","STILL_ACTIVE","NO_ACTIVE_FAULTS","UNVERIFIED","REJECTED","FAILED")
AXIS_RESULTS = (*RESULTS,"NOT_SELECTED")
REASONS = ("OBSERVED","NO_ACTIVE_FAULTS","INVALID_REQUEST","NOT_COMMISSIONED",
           "BUSY","DUPLICATE","NO_LOCAL_CONFIRMATION","INTERLOCK","STALE_FEEDBACK",
           "TIMEOUT","SDK_EXCEPTION","SOURCE_CHANGED","TRANSPORT_UNAVAILABLE",
           "HISTORY_UNAVAILABLE","INTERRUPTED")
SERVICE = "/nero_guarded/diagnostics/clear_joint_errors"
CLEARABLE_ARM_STATES = (0,2,3,4,5,6,7,8,9,10,14,15)
AGE = .5
VERIFY_TIMEOUT = 2.5


def valid_id(v):
    return isinstance(v,str) and re.fullmatch(r"[0-9a-f]{32}",v) is not None


def valid_scope(v):
    return type(v) is int and v in SCOPES


def targets(scope):
    return tuple(range(7)) if scope==255 else (scope-1,)


@dataclass(frozen=True)
class Evidence:
    arm_stamp: float
    arm_status: int
    arm_mask: int
    drive_status: tuple
    drive_stamps: tuple

    def valid(self, now):
        return (fresh(self.arm_stamp,now,AGE) and integer(self.arm_status,255)
                and integer(self.arm_mask,65535) and len(self.drive_status)==len(self.drive_stamps)==7
                and all(integer(v,255) for v in self.drive_status)
                and all(fresh(t,now,AGE) for t in self.drive_stamps))

    def axis_faults(self, i):
        return (self.drive_status[i]&DRIVE_FAULT_MASK, self.arm_mask & ((1<<i)|(1<<(8+i))))

    def disabled(self):
        return all(not v&0x40 for v in self.drive_status)

    def payload(self):
        return {"armStamp":self.arm_stamp,"armStatus":self.arm_status,"armMask":self.arm_mask,
                "driveStatus":list(self.drive_status),"driveStamps":list(self.drive_stamps)}


def evidence_from_payload(value):
    if (type(value) is not dict or set(value)!={"armStamp","armStatus","armMask","driveStatus","driveStamps"}
            or type(value["driveStatus"]) is not list or type(value["driveStamps"]) is not list):
        raise ValueError("invalid evidence")
    e=Evidence(value["armStamp"],value["armStatus"],value["armMask"],tuple(value["driveStatus"]),tuple(value["driveStamps"]))
    if not e.valid(max(e.arm_stamp,*e.drive_stamps)):
        raise ValueError("incoherent evidence")
    return e


def read_sdk_evidence(robot, *, clock=time.time):
    """Copy feedback only from the existing SDK object, including actual timestamps."""
    def copy_packet(packet, get):
        if packet is None:return None
        stamp=packet.timestamp; message=packet.msg
        value=get(message)
        if stamp!=packet.timestamp or message is not packet.msg:return None
        return stamp,value
    try:
        if not robot.is_ok():return None
        arm=copy_packet(robot.get_arm_status(),lambda m:(int(m.arm_status),int(m.err_code)))
        motors=[copy_packet(robot.get_driver_states(i),lambda m:int(m.foc_status_code)) for i in range(1,8)]
        if arm is None or any(m is None for m in motors):return None
        e=Evidence(arm[0],*arm[1],tuple(m[1] for m in motors),tuple(m[0] for m in motors))
        return e if e.valid(clock()) else None
    except (AttributeError,TypeError,ValueError,RuntimeError):
        return None


def result(operation,scope,status,reason,*,before=None,after=None,invoked=False,axes=None,sent_after=None):
    if axes is None:
        axes=[status if i in targets(scope) else "NOT_SELECTED" for i in range(7)] if valid_scope(scope) else ["NOT_SELECTED"]*7
    return {"operationId":operation,"scope":scope,"result":status,"reason":reason,
            "commandInvoked":invoked,"axisResults":list(axes),"sentAfter":sent_after,
            "before":before.payload() if before else None,"after":after.payload() if after else None}


def observed_axes(before,after,scope):
    axes=[]
    for i in range(7):
        if i not in targets(scope):
            axes.append("NOT_SELECTED");continue
        old,new=before.axis_faults(i),after.axis_faults(i)
        if not any(old) and not any(new):axes.append("NO_ACTIVE_FAULTS")
        elif not any(new):axes.append("CLEARED")
        elif any(o & ~n for o,n in zip(old,new)):axes.append("PARTIAL")
        else:axes.append("STILL_ACTIVE")
    return axes


def aggregate(axes):
    relevant=set(axes)-{"NOT_SELECTED","NO_ACTIVE_FAULTS"}
    if not relevant:return "NO_ACTIVE_FAULTS"
    if relevant=={"CLEARED"}:return "CLEARED"
    if relevant=={"STILL_ACTIVE"}:return "STILL_ACTIVE"
    return "PARTIAL"


def validate_result(v):
    try:
        if (type(v) is not dict or set(v)!={"operationId","scope","result","reason","commandInvoked","axisResults","before","after","sentAfter"}
                or not valid_id(v["operationId"]) or not valid_scope(v["scope"])
                or v["result"] not in RESULTS or v["reason"] not in REASONS
                or (type(v["commandInvoked"]) is not bool and not (v["commandInvoked"] is None and v["result"]=="UNVERIFIED")) or type(v["axisResults"]) is not list
                or len(v["axisResults"])!=7 or any(a not in AXIS_RESULTS for a in v["axisResults"])
                or any((a=="NOT_SELECTED")!=(i not in targets(v["scope"])) for i,a in enumerate(v["axisResults"]))):
            return False
        b=evidence_from_payload(v["before"]) if v["before"] is not None else None
        a=evidence_from_payload(v["after"]) if v["after"] is not None else None
        if v["result"] in ("CLEARED","PARTIAL","STILL_ACTIVE"):
            return (v["commandInvoked"] and v["reason"]=="OBSERVED" and b is not None and a is not None
                    and b.disabled() and a.disabled() and b.arm_status in CLEARABLE_ARM_STATES and a.arm_status in CLEARABLE_ARM_STATES
                    and fresh(v["sentAfter"],v["sentAfter"])
                    and max(b.arm_stamp,*b.drive_stamps)<=v["sentAfter"]<min(a.arm_stamp,*a.drive_stamps)
                    and v["axisResults"]==observed_axes(b,a,v["scope"])
                    and v["result"]==aggregate(v["axisResults"]))
        if v["result"]=="NO_ACTIVE_FAULTS":
            return (v["commandInvoked"] is False and v["reason"]=="NO_ACTIVE_FAULTS" and b is not None and a is None
                    and b.disabled() and b.arm_status in CLEARABLE_ARM_STATES and v["sentAfter"] is None
                    and all(not any(b.axis_faults(i)) for i in targets(v["scope"]))
                    and all(x=="NO_ACTIVE_FAULTS" for x in v["axisResults"] if x!="NOT_SELECTED"))
        return (a is None and (v["sentAfter"] is None or fresh(v["sentAfter"],v["sentAfter"]))
                and (v["result"]!="REJECTED" or not v["commandInvoked"]) and all(
                    x==v["result"] for x in v["axisResults"] if x!="NOT_SELECTED"))
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


class ClearEngine:
    """Single-owner operation, no enable/reset/trajectory or auto-retry.

    The guard must keep motion locked and local approval independent of ROS.
    STOP may invalidate the in-flight operation without waiting on verification.
    """
    def __init__(self, *, read, clear, interlock, consume_approval, commissioned=False,
                 clock=time.time, mono=time.monotonic, sleep=time.sleep, tx_lock=None):
        self.read,self.clear,self.interlock,self.consume_approval=read,clear,interlock,consume_approval
        self.commissioned=commissioned
        self.clock,self.mono,self.sleep=clock,mono,sleep
        self.tx_lock=tx_lock or threading.RLock()
        self.lock=threading.Lock()
        self.seen=set()

    def execute(self, operation, scope, not_after):
        def out(status,reason,**kwargs):return result(operation,scope,status,reason,**kwargs)
        if (not valid_id(operation) or not valid_scope(scope) or
                type(not_after) not in (int,float) or not math.isfinite(not_after)
                or not self.clock()<not_after<=self.clock()+15):
            return out("REJECTED","INVALID_REQUEST")
        if not self.commissioned:return out("REJECTED","NOT_COMMISSIONED")
        if not self.lock.acquire(blocking=False):return out("REJECTED","BUSY")
        try:
            if operation in self.seen:return out("REJECTED","DUPLICATE")
            # Bound memory without permitting replay; refuse new operations
            # rather than evict previously consumed identifiers.
            if len(self.seen)>=10000:return out("REJECTED","NOT_COMMISSIONED")
            self.seen.add(operation)
            if not self.interlock():return out("REJECTED","INTERLOCK")
            if not self.consume_approval(operation,scope):return out("REJECTED","NO_LOCAL_CONFIRMATION")
            with self.tx_lock:
                if not self.interlock() or self.clock()>=not_after:return out("REJECTED","INTERLOCK")
                before=self.read()
                if before is None or not before.valid(self.clock()):
                    return out("REJECTED","STALE_FEEDBACK")
                if not before.disabled() or before.arm_status not in CLEARABLE_ARM_STATES:
                    return out("REJECTED","INTERLOCK",before=before)
                if all(not any(before.axis_faults(i)) for i in targets(scope)):
                    return out("NO_ACTIVE_FAULTS","NO_ACTIVE_FAULTS",before=before)
                if not self.interlock() or self.clock()>=not_after:
                    return out("REJECTED","INTERLOCK",before=before)
                try:
                    self.clear(scope)
                except Exception:
                    return out("FAILED","SDK_EXCEPTION",before=before,invoked=True)
                sent_after=self.clock()
            deadline=self.mono()+VERIFY_TIMEOUT
            previous=None
            last_verified=None
            while self.mono()<deadline:
                if not self.interlock():
                    return out("UNVERIFIED","INTERRUPTED",before=before,invoked=True,sent_after=sent_after)
                after=self.read()
                if after is not None and after.valid(self.clock()):
                    if not after.disabled() or after.arm_status not in CLEARABLE_ARM_STATES:
                        return out("UNVERIFIED","INTERLOCK",before=before,invoked=True,sent_after=sent_after)
                    if after.arm_stamp>sent_after and all(t>sent_after for t in after.drive_stamps):
                        if (previous is not None and after.arm_stamp>previous.arm_stamp
                                and all(n>o for n,o in zip(after.drive_stamps,previous.drive_stamps))):
                            axes=observed_axes(before,after,scope)
                            if all(after.axis_faults(i)==previous.axis_faults(i) for i in targets(scope)):
                                last_verified=(after,axes)
                                if aggregate(axes)=="CLEARED":
                                    return out("CLEARED","OBSERVED",before=before,after=after,invoked=True,axes=axes,sent_after=sent_after)
                            else:
                                last_verified=None
                        if previous is None or (after.arm_stamp>previous.arm_stamp and all(n>o for n,o in zip(after.drive_stamps,previous.drive_stamps))):
                            previous=after
                else:
                    # A feedback gap invalidates the consecutive evidence;
                    # never return a previously verified state through a gap.
                    previous=None
                    last_verified=None
                self.sleep(.05)
            if last_verified is not None:
                after,axes=last_verified
                if after.valid(self.clock()):
                    return out(aggregate(axes),"OBSERVED",before=before,after=after,invoked=True,axes=axes,sent_after=sent_after)
            return out("UNVERIFIED","TIMEOUT",before=before,invoked=True,sent_after=sent_after)
        finally:
            self.lock.release()
