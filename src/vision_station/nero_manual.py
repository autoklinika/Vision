"""Manual-control admission and native JTC reference consumption.

No interpolation or second CAN owner. Only the commissioned owner may
supply the hardware callbacks. Never enables on initialization.
"""
from dataclasses import dataclass
import math
from threading import RLock
import time
from .nero_clear import valid_id
from .nero_tcp import AXES, validate_declaration, twist_intent

JOINTS=tuple(f"joint{i}" for i in range(1,8))
ACTIONS=("CONNECT_CAN","ENABLE","JOG","RELEASE","HOLD","CLOSE")
STATES=("IDLE","ENABLING","READY","JOGGING","STOPPING","HOLD","FAULT")
AGE=.15
LEASE=.30
SESSION_IDLE=30.
NANO=1_000_000_000

def finite(x):
    return type(x) in (int,float) and math.isfinite(x)

def vector7(v):
    return isinstance(v,(tuple,list)) and len(v)==7 and all(finite(x) for x in v)

def valid_intent(v):
    if (type(v) is not dict or set(v)!={"instanceId","operationId","action","sequence","sentAt","declaration","axis","direction"}
            or not valid_id(v["instanceId"]) or not valid_id(v["operationId"]) or v["action"] not in ACTIONS
            or type(v["sequence"]) is not int or not 0<=v["sequence"]<=2**31-1
            or not finite(v["sentAt"]) or v["sentAt"]<=0):return False
    if v["action"]=="JOG":
        return (v["sequence"]>0 and validate_declaration(v["declaration"])
                and v["axis"] in AXES and type(v["direction"]) is int and v["direction"] in (-1,1))
    return (v["declaration"] is None and v["axis"] is None and v["direction"] is None
            and (v["sequence"]==0 if v["action"] in ("ENABLE","CONNECT_CAN") else v["sequence"]>0))

@dataclass(frozen=True)
class Profile:
    # Explicit commissioning inputs; no real station defaults.
    linear_max:int
    angular_max:int
    joint_limits:tuple
    joint_velocity_max:tuple
    tracking_error_max:float

    def __post_init__(self):
        if (type(self.linear_max) is not int or not 1<=self.linear_max<=100
                or type(self.angular_max) is not int or not 1<=self.angular_max<=30
                or len(self.joint_limits)!=7 or not vector7(self.joint_velocity_max)
                or any(not 0<x<=.15 for x in self.joint_velocity_max)
                or not finite(self.tracking_error_max) or not 0<self.tracking_error_max<=.05
                or any(len(r)!=2 or not all(finite(x) for x in r) or r[0]>=r[1] for r in self.joint_limits)):
            raise ValueError("invalid commissioned limits")

    @classmethod
    def from_robot_model(cls, *, sdk_config, model_urdf, linear_max, angular_max,
                         joint_velocity_max, tracking_error_max):
        """Derive position bounds from the actual SDK and loaded robot_description.

        Speed/tracking caps still require approved station configuration.
        No stored initial joint position or default hardware envelope.
        """
        from .nero_joint_limits import sdk_bounds,model_bounds,intersection
        limits=intersection(sdk_bounds(sdk_config),model_bounds(model_urdf))
        return cls(linear_max,angular_max,limits,tuple(joint_velocity_max),tracking_error_max)

    def contains(self,q):
        return vector7(q) and all(lo<=x<=hi for x,(lo,hi) in zip(q,self.joint_limits))

    def accepts(self,d):
        return validate_declaration(d) and d["linearMmS"]<=self.linear_max and d["angularDegS"]<=self.angular_max

@dataclass(frozen=True)
class Feedback:
    q:tuple
    velocity:tuple
    joint_stamp:float
    arm_stamp:float
    arm_status:int
    arm_mask:int
    control_mode:int
    drive_status:tuple
    drive_stamps:tuple
    velocity_stamps:tuple

    def valid(self,now,*,require_can=True):
        return (vector7(self.q) and vector7(self.velocity)
                and len(self.drive_status)==len(self.drive_stamps)==len(self.velocity_stamps)==7
                and all(finite(t) and 0<=now-t<=AGE for t in (self.joint_stamp,self.arm_stamp,*self.drive_stamps,*self.velocity_stamps))
                and all(type(v) is int and 0<=v<=255 for v in self.drive_status)
                and type(self.arm_status) is int and 0<=self.arm_status<=255
                and type(self.arm_mask) is int and 0<=self.arm_mask<=65535 and type(self.control_mode) is int and (self.control_mode==1 if require_can else self.control_mode in (0,1,3)))

    def clean(self,now):
        return self.valid(now) and self.arm_mask==0 and not any(v&0xBF for v in self.drive_status)

    def drives(self):
        return tuple(bool(v&0x40) for v in self.drive_status)

    def normal(self,now):
        return self.clean(now) and self.arm_status==0 and all(self.drives())

    def stamp_min(self):
        return min(self.joint_stamp,self.arm_stamp,*self.drive_stamps,*self.velocity_stamps)

def validate_reference(v,now_ns):
    return (type(v) is dict and set(v)=={"stampNs","windowEndNs","status","positions","velocities"}
            and type(v["stampNs"]) is int and type(v["windowEndNs"]) is int
            and 0<=now_ns-v["stampNs"]<=100_000_000
            and now_ns<v["windowEndNs"]<=now_ns+500_000_000
            and type(v["status"]) is int and v["status"] in (0,1,3,4)
            and vector7(v["positions"]) and vector7(v["velocities"]))

class ManualEngine:
    """Single session. Native owner ports and HOLD share one RLock.

    A key release sends zero Twist. Lost input, invalid feedback, lost
    reference, or envelope violation requests latched HOLD, not disable.
    """
    def __init__(self,profile,ports,*,lock=None,wall=time.time,mono=time.monotonic):
        self.profile,self.ports=profile,ports
        self.lock=lock or RLock();self.wall,self.mono=wall,mono
        self.state="IDLE";self.reason="NO_SESSION";self.session=None;self.sequence=0
        self.declaration=self.intent=None;self.used=set()
        self.lease=self.idle_until=self.phase_start=0.
        self.sent_at=self.enable_sample=0.;self.enable_count=0
        self.last_stamp=0;self.last_reference_at=0.;self.last_q=None;self.last_send=0.
        self.stable_since=None
        self.start_pending=False

    def feedback(self):
        try:
            f=self.ports.read_feedback()
            return f if isinstance(f,Feedback) and f.valid(self.wall()) else None
        except Exception:return None

    def ready(self):
        try:return self.ports.pipeline_ready() is True
        except Exception:return False

    def start_aligned(self,f):
        if f is None or not self.profile.contains(f.q):
            return False
        try:return self.ports.start_aligned(f) is True
        except Exception:return False

    def zero(self):
        try:self.ports.twist({"frameId":"base_link","linear":[0.]*3,"angular":[0.]*3})
        except Exception:pass

    def latch(self,reason,*,invoke=True):
        self.state="HOLD";self.reason=reason;self.session=None
        self.intent=self.declaration=None
        self.start_pending=False
        self.zero()
        if invoke:
            try:
                if self.ports.hold() is not True:self.state="FAULT";self.reason="HOLD_UNVERIFIED"
            except Exception:self.state="FAULT";self.reason="HOLD_UNVERIFIED"

    def external_hold(self):
        with self.lock:self.latch("OPERATOR_HOLD",invoke=False)

    def shutdown(self):
        with self.lock:
            if self.state in ("ENABLING","READY","JOGGING","STOPPING"):self.latch("SHUTDOWN")

    def can_connect_available(self):
        if self.state!="IDLE" or self.session is not None:
            return False
        try:return self.ports.can_connect_available() is True
        except Exception:return False

    def report(self):
        with self.lock:
            f=self.feedback();drives=list(f.drives()) if f else [None]*7
            ready=self.ready()
            aligned=self.start_aligned(f) if ready and self.state in ("IDLE","READY") else False
            possible=(self.state=="IDLE" and ready and f is not None and f.clean(self.wall())
                      and f.arm_status in (0,6) and (all(drives) or not any(drives))
                      and aligned and max(abs(x) for x in f.velocity)<=.01)
            reason=("START_STATE_UNALIGNED" if self.state in ("IDLE","READY") and ready and f is not None and not aligned else self.reason)
            return {"state":self.state,"reason":reason,"driveEnabled":drives,"pipelineReady":ready,
                    "canConnectAvailable":self.can_connect_available(),"enableAvailable":possible,"jogAvailable":self.state in ("READY","JOGGING") and ready and f is not None and f.normal(self.wall()) and (self.state=="JOGGING" or aligned),
                    "holdAvailable":self.state in ("ENABLING","READY","JOGGING","STOPPING"),
                    "linearMax":self.profile.linear_max,"angularMax":self.profile.angular_max}

    def command(self,v):
        if not valid_intent(v):raise ValueError("invalid manual intent")
        with self.lock:
            op=v["operationId"];act=v["action"];now=self.wall();mono=self.mono()
            def out(ok,reason):
                return {"operationId":op,"action":act,"sequence":v["sequence"],"accepted":ok,"reason":reason,"state":self.state}
            if act=="CONNECT_CAN":
                # Standalone operator command. Never opens a motion session or enables drives.
                if not 0<=now-v["sentAt"]<=1.:return out(False,"STALE")
                if op in self.used or len(self.used)>=10000:return out(False,"REPLAY")
                if not self.can_connect_available():return out(False,"INTERLOCK")
                self.used.add(op)
                try:connected=self.ports.connect_can() is True
                except Exception:connected=False
                return out(connected,"CAN_CONNECTED" if connected else "CAN_CONNECT_UNVERIFIED")
            if act=="ENABLE":
                if not 0<=now-v["sentAt"]<=1.:return out(False,"STALE")
                if self.state!="IDLE" or op in self.used or len(self.used)>=10000:return out(False,"INTERLOCK")
                f=self.feedback()
                if not self.report()["enableAvailable"] or f is None or not self.start_aligned(f):return out(False,"INTERLOCK")
                if not self.ports.approve(v):return out(False,"NO_LOCAL_CONFIRMATION")
                self.used.add(op);self.session=(v["instanceId"],op);self.sequence=0
                self.phase_start=mono;self.idle_until=mono+SESSION_IDLE
                if all(f.drives()) and f.normal(now):
                    self.state="READY";self.reason="DRIVES_ALREADY_ENABLED"
                    return out(True,self.reason)
                if any(f.drives()):
                    self.session=None;return out(False,"INTERLOCK")
                self.state="ENABLING";self.reason="AWAITING_DRIVE_FEEDBACK"
                self.enable_count=0;self.enable_sample=0.;self.sent_at=now
                try:self.ports.enable()  # one explicit attempt; reply isn't readback
                except Exception:self.latch("ENABLE_UNVERIFIED");return out(False,self.reason)
                return out(True,self.reason)
            if self.session!=(v["instanceId"],op):return out(False,"NO_SESSION")
            if v["sequence"]<=self.sequence:return out(False,"REPLAY")
            if act=="HOLD":
                self.sequence=v["sequence"];self.latch("OPERATOR_HOLD");return out(True,self.reason)
            if not 0<=now-v["sentAt"]<=LEASE:return out(False,"STALE")
            self.sequence=v["sequence"]
            if act=="CLOSE":
                if self.state!="READY":self.latch("SESSION_CLOSED");return out(True,self.reason)
                self.state="IDLE";self.session=None;self.reason="SESSION_CLOSED";self.zero();return out(True,self.reason)
            if act=="RELEASE":
                if self.state=="JOGGING":
                    self.state="STOPPING";self.reason="DECELERATING";self.phase_start=mono;self.stable_since=None;self.zero()
                return out(self.state in ("READY","STOPPING"),self.reason)
            if act!="JOG" or self.state not in ("READY","JOGGING"):return out(False,"INTERLOCK")
            f=self.feedback();d=v["declaration"]
            if f is None or not f.normal(now) or not self.ready() or not self.profile.accepts(d):
                self.latch("ADMISSION_FAILED");return out(False,self.reason)
            key=(v["axis"],v["direction"])
            if self.state=="JOGGING" and (self.intent!=key or self.declaration!=d):
                self.latch("INPUT_CHANGED_WHILE_MOVING");return out(False,self.reason)
            if self.state=="READY":
                if not self.start_aligned(f):
                    return out(False,"START_STATE_UNALIGNED")
                self.state="JOGGING";self.reason="JOG_ACTIVE";self.phase_start=mono
                self.last_reference_at=mono;self.last_q=tuple(f.q);self.last_send=mono
                self.last_stamp=int(now*NANO);self.intent=key;self.declaration=dict(d)
                self.start_pending=True
                try:self.ports.reference()  # discard queued sample from previous input
                except Exception:self.latch("TRANSPORT_LOST");return out(False,self.reason)
            self.lease=mono+LEASE;self.idle_until=mono+SESSION_IDLE
            return out(True,self.reason)

    def tick(self):
        with self.lock:
            now=self.wall();mono=self.mono()
            if self.state=="ENABLING":
                f=self.feedback()
                if not self.ready() or mono-self.phase_start>2.5:self.latch("ENABLE_UNVERIFIED");return
                if f and f.normal(now) and self.start_aligned(f) and f.stamp_min()>max(self.sent_at,self.enable_sample):
                    self.enable_sample=f.stamp_min();self.enable_count+=1
                    if self.enable_count>=2:
                        self.state="READY";self.reason="DRIVES_ENABLED_OBSERVED";self.idle_until=mono+SESSION_IDLE
                return
            if self.state=="READY":
                f=self.feedback()
                if f is None or not f.normal(now) or not self.ready():self.latch("FEEDBACK_OR_PIPELINE_LOST")
                elif mono>=self.idle_until:self.session=None;self.state="IDLE";self.reason="SESSION_EXPIRED";self.zero()
                return
            if self.state not in ("JOGGING","STOPPING"):return
            f=self.feedback()
            if (f is None or not f.normal(now) or not self.ready() or not self.profile.contains(f.q)
                    or any(abs(v)>lim+.01 for v,lim in zip(f.velocity,self.profile.joint_velocity_max))):
                self.latch("FEEDBACK_OR_PIPELINE_LOST");return
            if self.state=="JOGGING" and mono>=self.lease:self.latch("INPUT_LEASE_EXPIRED");return
            if self.start_pending:
                self.start_pending=False
                if not self.start_aligned(f):
                    self.latch("START_STATE_UNALIGNED");return
            try:
                if self.state=="JOGGING":self.ports.twist(twist_intent(self.declaration,*self.intent))
                else:self.zero()
                r=self.ports.reference()
            except Exception:self.latch("TRANSPORT_LOST");return
            if r is not None:
                if not validate_reference(r,int(self.wall()*NANO)):self.latch("REFERENCE_INVALID");return
                if r["stampNs"]>self.last_stamp:
                    q=r["positions"];v=r["velocities"];dt=min(.1,max(0.,mono-self.last_send))
                    if (not self.profile.contains(q)
                            or any(abs(a-b)>self.profile.tracking_error_max for a,b in zip(q,f.q))
                            or any(abs(x)>lim for x,lim in zip(v,self.profile.joint_velocity_max))
                            or any(abs(a-b)>lim*dt+.0001 for a,b,lim in zip(q,self.last_q,self.profile.joint_velocity_max))):
                        self.latch("REFERENCE_ENVELOPE");return
                    try:self.ports.position(tuple(q))
                    except Exception:self.latch("POSITION_UNVERIFIED");return
                    self.last_q=tuple(q);self.last_send=mono;self.last_stamp=r["stampNs"];self.last_reference_at=mono
            if self.state=="STOPPING":
                settled=(max(abs(x) for x in f.velocity)<=.01 and self.last_q is not None
                         and max(abs(a-b) for a,b in zip(self.last_q,f.q))<=.001)
                if settled and mono-self.last_reference_at<AGE:
                    if self.stable_since is None:self.stable_since=mono
                    elif mono-self.stable_since>=.15:
                        self.state="READY";self.reason="STOP_OBSERVED";self.intent=None;self.idle_until=mono+SESSION_IDLE;return
                else:self.stable_since=None
                if mono-self.phase_start>.8:self.latch("STOP_UNVERIFIED");return
            if mono-self.last_reference_at>.35:self.latch("REFERENCE_TIMEOUT")
