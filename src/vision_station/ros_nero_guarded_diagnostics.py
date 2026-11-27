"""Optional versioned extension of the sole existing guarded driver.

Never start alongside the existing CAN owner. The clear service is opt-in and
must remain disabled until separate supervised commissioning. No enable,
controller reset, new motion subscription or automatic motion is introduced.
"""
import os
import threading
import time

from .nero_clear import ClearEngine, Evidence, read_sdk_evidence
from .nero import NODE
from .ros_nero import sample_can
from .nero_local_approval import Approval
from .ros_nero_servo_bridge import CandidateReceiver


def to_message(value, msg):
    if value is not None:
        msg.valid=True
        msg.arm_stamp=value["armStamp"];msg.arm_status=value["armStatus"];msg.arm_mask=value["armMask"]
        msg.drive_status=value["driveStatus"];msg.drive_stamps=value["driveStamps"]
    return msg


def from_message(msg):
    if not msg.valid:return None
    return Evidence(msg.arm_stamp,msg.arm_status,msg.arm_mask,tuple(map(int,msg.drive_status)),tuple(map(float,msg.drive_stamps))).payload()


def node_class():
    # Import only in the isolated, deliberately launched ROS owner process.
    from agx_arm_ctrl.vision_nero_guarded_node import VisionNeroGuardedNode
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
    from vision_nero_diagnostics_interfaces.msg import NeroEvidence
    from vision_nero_diagnostics_interfaces.srv import ClearJointErrors

    class GuardedDiagnosticsNode(VisionNeroGuardedNode):
        def _load_parameters(self):
            super()._load_parameters()
            self.declare_parameter("diagnostics_clear_enabled",False)
            self.declare_parameter("diagnostics_approval_directory","")
            self._clear_commissioned=self.get_parameter("diagnostics_clear_enabled").value is True
            self._approval=None
            if self._clear_commissioned:
                self._approval=Approval(self.get_parameter("diagnostics_approval_directory").value)
            self.declare_parameter("servo_candidate_monitor_enabled",False)
            self._servo_candidate_receiver=None
            self._diagnostics_group=MutuallyExclusiveCallbackGroup()
            self._tx_lock=threading.RLock()
            self._stop_epoch=0
            self._stop_in_progress=False
            self._clear_epoch=None

        def _setup_publishers(self):
            super()._setup_publishers()
            self._evidence_pub=self.create_publisher(NeroEvidence,"feedback/diagnostic_evidence",1)
            self._evidence_timer=self.create_timer(.2,self._publish_evidence)

        def _publish_evidence(self):
            e=read_sdk_evidence(self.agx_arm)
            self._evidence_pub.publish(to_message(e.payload() if e else None,NeroEvidence()))

        def _setup_subscribers(self):
            super()._setup_subscribers()
            if self.get_parameter("servo_candidate_monitor_enabled").value is True:
                self._servo_candidate_receiver=CandidateReceiver(self)

        def _setup_services(self):
            super()._setup_services()
            self._clear_engine=ClearEngine(read=lambda:read_sdk_evidence(self.agx_arm),
                clear=self.agx_arm.clear_joint_error, interlock=self._clear_interlock,
                consume_approval=lambda op,scope: self._approval is not None and self._approval.consume(op,scope),
                commissioned=self._clear_commissioned,tx_lock=self._tx_lock)
            if self._clear_commissioned:
                self.create_service(ClearJointErrors,"diagnostics/clear_joint_errors",self._clear_callback,
                                    callback_group=self._diagnostics_group)

        def _clear_interlock(self):
            can=sample_can()
            return (can is not None and can["up"] is True and can["state"]=="ERROR-ACTIVE"
                    and self._clear_commissioned and self.get_parameter("diagnostics_clear_enabled").value is True
                    and self._clear_epoch==self._stop_epoch
                    and not self._stop_in_progress and not self.control_enabled and not self.auto_enable
                    and not self.get_parameter("control_enabled").value and not self.get_parameter("auto_enable").value
                    and not self.vision_arbiter.motion_allowed()
                    and self.vision_arbiter.mode.value in ("LOCKED","STOP_LATCHED"))

        def _controlled_stop_hold_callback(self,request,response):
            # Invalidate any diagnostic verification immediately. Preserve
            # the existing HOLD behavior; serialize only the SDK TX section.
            self._stop_epoch+=1
            self._stop_in_progress=True
            try:
                with self._tx_lock:
                    return super()._controlled_stop_hold_callback(request,response)
            finally:
                self._stop_in_progress=False

        def _clear_callback(self,request,response):
            self._clear_epoch=self._stop_epoch
            v=self._clear_engine.execute(request.operation_id,request.scope,request.not_after)
            response.operation_id=v["operationId"];response.scope=v["scope"]
            response.result=v["result"];response.reason=v["reason"]
            response.command_invoked=v["commandInvoked"];response.sent_after=v["sentAfter"] or 0.
            response.axis_results=v["axisResults"]
            response.before=to_message(v["before"],response.before)
            response.after=to_message(v["after"],response.after)
            return response

    return GuardedDiagnosticsNode


def main():
    if (os.environ.get("ROS_DOMAIN_ID")!="181" or os.environ.get("ROS_LOCALHOST_ONLY")!="1"
            or os.environ.get("VISION_NERO_REPLACEMENT_OWNER")!="1"):
        raise SystemExit("fixed local domain and explicit replacement-owner commissioning required")
    # This executable is intentionally not wired into a unit or deployment.
    # It is a replacement owner, never a second owner.
    import rclpy
    from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
    rclpy.init()
    node=None;executor=MultiThreadedExecutor(num_threads=3)
    try:
        # ROS graph preflight is an additional check, not a replacement for
        # stopping the old unit and verifying exclusive CAN ownership.
        probe=rclpy.create_node("vision_nero_replacement_preflight",enable_rosout=False,start_parameter_services=False,use_global_arguments=False)
        try:
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                rclpy.spin_once(probe,timeout_sec=.1)
                if any(ns.rstrip("/")+"/"+name==NODE for name,ns in probe.get_node_names_and_namespaces()):
                    raise RuntimeError("existing guarded CAN owner detected")
        finally:
            probe.destroy_node()
        node=node_class()();executor.add_node(node);executor.spin()
    except (KeyboardInterrupt,ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        if node is not None:node.destroy_node()
        rclpy.try_shutdown()


if __name__=="__main__":main()
