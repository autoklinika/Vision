"""Native manual execution ports inside the versioned guarded CAN owner.

Only explicit commissioned composition can instantiate this runtime.
There is deliberately no CLI that enables this from a ROS parameter.
The external pipeline authority must verify the approved real model,
scene, controller and Servo TWIST mode; a graph match is not sufficient.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from .nero_manual import Feedback,ManualEngine,Profile,JOINTS
from .nero_local_approval import Approval
from .nero_manual_transport import ManualOwnerServer
from .nero_joint_limits import MODEL

def _copy(packet,convert):
    if packet is None:raise ValueError("missing feedback")
    stamp=float(packet.timestamp);msg=packet.msg;value=convert(msg)
    if stamp!=packet.timestamp or msg is not packet.msg:raise ValueError("changed feedback")
    return stamp,value

def sdk_feedback(owner):
    try:
        robot=owner.agx_arm
        if tuple(owner.arm_joint_names)!=JOINTS or not robot.is_ok():return None
        jt,q=_copy(robot.get_joint_angles(),lambda m:tuple(map(float,m)))
        at,(status,mask,mode)=_copy(robot.get_arm_status(),lambda m:(int(m.arm_status),int(m.err_code),int(m.ctrl_mode)))
        d=[_copy(robot.get_driver_states(i),lambda m:int(m.foc_status_code)) for i in range(1,8)]
        v=[_copy(robot.get_motor_states(i),lambda m:float(m.velocity)) for i in range(1,8)]
        f=Feedback(q,tuple(x[1] for x in v),jt,at,status,mask,mode,tuple(x[1] for x in d),
                   tuple(x[0] for x in d),tuple(x[0] for x in v))
        return f if f.valid(time.time()) else None
    except Exception:return None

class NativePorts:
    def __init__(self,owner,*,approval,relay,pipeline_authority,native_hold):
        self.owner=owner;self.approval=approval;self.relay=relay
        self.authority=pipeline_authority;self.native_hold=native_hold
        from geometry_msgs.msg import TwistStamped
        self.message_type=TwistStamped
        self.publisher=owner.create_publisher(TwistStamped,"/vision_manual/twist",1)
    def read_feedback(self):return sdk_feedback(self.owner)
    def pipeline_ready(self):
        o=self.owner
        # Legacy motion endpoints stay locked. This is a separate manual
        # admission inside the same owner and shares the existing HOLD latch.
        return (self.authority() is True and self.relay.alive()
                and o.vision_arbiter.mode.value=="LOCKED" and not o._stop_in_progress
                and o.physical_hold_enabled and not o.fast_mode and not o.auto_enable and not o.control_enabled
                and not o.get_parameter("auto_enable").value and not o.get_parameter("control_enabled").value)
    def approve(self,intent):return self.approval.consume(intent["operationId"],255)
    def enable(self):
        if not self.pipeline_ready():raise RuntimeError("manual interlock")
        f=self.read_feedback()
        if f is None or not f.clean(time.time()) or any(f.drives()) or f.arm_status not in (0,6):
            raise RuntimeError("enable readback rejected")
        # Existing firmware-specific vendor SDK. No retry, reset or disable.
        self.owner.agx_arm.enable(timeout=0.)
    def twist(self,v):
        m=self.message_type();m.header.stamp=self.owner.get_clock().now().to_msg();m.header.frame_id=v["frameId"]
        m.twist.linear.x,m.twist.linear.y,m.twist.linear.z=v["linear"]
        m.twist.angular.x,m.twist.angular.y,m.twist.angular.z=v["angular"]
        self.publisher.publish(m)
    def reference(self):return self.relay.latest()
    def position(self,q):
        f=self.read_feedback()
        if not self.pipeline_ready() or f is None or not f.normal(time.time()):
            raise RuntimeError("manual interlock")
        # Use the existing AgileX ROS driver position-command implementation,
        # not a second SDK instance, raw CAN, or custom IK.
        self.owner._control_arm_joints(dict(zip(JOINTS,q)))
    def hold(self):return self.native_hold() is True

class NativeRelay:
    """Only the spawned native relay possesses the inherited sample socket."""
    def __init__(self,executable):
        p=Path(executable)
        if (not p.is_absolute() or not p.is_relative_to("/srv/vision-data") or not p.is_file()
                or any(x.is_symlink() for x in (p,*p.parents)) or p.stat().st_uid!=os.getuid()
                or p.stat().st_mode&0o022):
            raise ValueError("explicit private native relay binary required")
        self.sock,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.sock.setblocking(False)
        try:
            self.child=subprocess.Popen([str(p),"--ros-args","-p","pipeline_namespace:=/vision_manual"],
                pass_fds=(peer.fileno(),),env=dict(os.environ,VISION_SERVO_RELAY_FD=str(peer.fileno())))
        except BaseException:
            self.sock.close();raise
        finally:peer.close()
    def alive(self):return self.child.poll() is None
    def latest(self):
        if not self.alive():raise RuntimeError("relay exited")
        last=None
        for _ in range(64):
            try:raw=self.sock.recv(2049)
            except BlockingIOError:break
            if not raw or len(raw)>2048:raise RuntimeError("relay frame unavailable")
            last=json.loads(raw)
        return last
    def close(self):
        self.sock.close()
        if self.alive():
            self.child.terminate()
            try:self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:self.child.kill();self.child.wait(timeout=2)

class ManualRuntime:
    """Instantiate only with a commissioning authority, inside one ROS owner."""
    def __init__(self,owner,*,profile,approval_directory,socket_path,relay_binary,pipeline_authority,native_hold):
        if (not isinstance(profile,Profile) or not callable(pipeline_authority)
                or pipeline_authority() is not True or not callable(native_hold)
                or owner._clear_commissioned or owner.fast_mode or not owner.physical_hold_enabled):
            raise ValueError("approved exclusive manual composition required")
        limits=owner.agx_arm.get_config()["joint_limits"]
        if set(limits)!=set(JOINTS) or any(lo<max(limits[n][0],model[0]) or hi>min(limits[n][1],model[1])
                for n,(lo,hi),model in zip(JOINTS,profile.joint_limits,MODEL)):
            raise ValueError("profile exceeds SDK or official MoveIt model limits")
        self.relay=NativeRelay(relay_binary)
        self.server=None;self.timer=None
        try:
            self.ports=NativePorts(owner,approval=Approval(approval_directory),relay=self.relay,
                                   pipeline_authority=pipeline_authority,native_hold=native_hold)
            self.engine=ManualEngine(profile,self.ports,lock=owner._tx_lock)
            self.server=ManualOwnerServer(socket_path,self.engine)
            self.timer=owner.create_timer(.02,self.engine.tick)
        except BaseException:
            if self.server:self.server.close()
            self.relay.close();raise
    def external_hold(self):self.engine.external_hold()
    def close(self):
        if self.timer:self.timer.cancel()
        if self.server:self.server.close()
        self.engine.shutdown()
        self.relay.close()
