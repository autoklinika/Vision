"""VISION C7 limited NERO ROS 2 FollowJointTrajectory adapter.

Experimental single CAN owner on the official AgileX v121 pyAgxArm.
Default trajectory DISABLED. One authorized joint2-only <=2deg move per
process lifetime using move_j() (NEVER move_js()). External HOLD Trigger
retargets current q via existing tested stop path and latches STOP.

Not a full Pilz time-parameterized trajectory executor or a safety-rated system.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import threading
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.action.server import GoalResponse,CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor,ExternalShutdownException
from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger
from agx_arm_ctrl.vision_nero_guarded_node import VisionNeroGuardedNode
from agx_arm_ctrl.vision_nero_single_segment_policy import (
 JOINTS, RejectGoal, validate_step,check_feedback,converged)

class VisionNeroSingleSegmentNode(VisionNeroGuardedNode):
 def __init__(self):
    self._io_mutex=threading.RLock()
    self._goal_mutex=threading.RLock()
    self._stop_requested=threading.Event()
    self._hold_result=None
    self._active_motion=False
    self._goal_claimed=False
    super().__init__()
    self.declare_parameter("physical_single_segment_enabled",False)
    self._physical_enabled=bool(self.get_parameter("physical_single_segment_enabled").value)
    self.declare_parameter("one_shot_authorization_file","")
    fn=str(self.get_parameter("one_shot_authorization_file").value)
    self._auth_path=Path(fn) if fn else None
    self._used_marker=Path(fn+".used") if fn else None
    self._author=None
    if self._used_marker and self._used_marker.exists():
        self._goal_claimed=True
        self.get_logger().warn("ONE_SHOT_PREVIOUSLY_CONSUMED_FAIL_CLOSED")
    if self._physical_enabled:
        mock=(os.getenv("VISION_NERO_ISOLATED_FAKE")=="1" and
              os.getenv("VISION_NERO_ISOLATED_TEST")=="1" and
              os.getenv("ROS_DOMAIN_ID")=="178" and
              getattr(self.agx_arm,"_vision_offline_fake",False) is True)
        live=(os.getenv("ROS_DOMAIN_ID")=="181" and
              os.getenv("ROS_LOCALHOST_ONLY")=="1" and
              os.getenv("VISION_NERO_ISOLATED_FAKE") is None)
        if (not (mock or live) or
            not self.physical_hold_enabled or
            self._auth_path is None or not self._auth_path.is_file()):
            raise RuntimeError("FAIL_CLOSED_NO_AUTH_OR_WRONG_DOMAIN_OR_HOLD_DISABLED")
        self._author=json.loads(self._auth_path.read_text())
        if (self._author.get("phase")!="LIMITED_ONE_SEGMENT_FIRST_MOTION"
            or self._author.get("max_delta_deg")!=2.0
            or self._author.get("enabled_by_operator") is not True
            or self._author.get("expires_unix_time",0)<time.time()
            or self._author.get("joint")!="joint2"):
            raise RuntimeError("INVALID_EXPIRED_OR_WRONG_LIMITS_AUTHORIZATION")
    self._group=ReentrantCallbackGroup()
    self._action=ActionServer(self,FollowJointTrajectory,
        "/nero_guarded/follow_joint_trajectory_lab",
        execute_callback=self._execute_goal,
        goal_callback=self._on_goal,
        cancel_callback=self._on_cancel,
        callback_group=self._group)
    self.get_logger().warn(
       "VISION_LIMITED_FOLLOW_ACTION_AVAILABLE: physical_enabled=%s; "
       "one-shot joint2 max 2deg; full trajectories BLOCKED; "
       "HOLD service preserved; NOT_SAFETY_RATED" % self._physical_enabled)

 def _snapshot(self):
    with self._io_mutex:
        status=self.agx_arm.get_arm_status()
        joints=self.agx_arm.get_joint_angles()
        now=time.time()
        if status is None or joints is None:
            raise RejectGoal("MISSING_ARM_TELEMETRY")
        age=max(now-joints.timestamp,now-status.timestamp)
        if age<0 or age>.15:
            raise RejectGoal(f"STALE_ARM_FEEDBACK_{age:.4f}")
        q=list(map(float,joints.msg))
        if len(q)!=7:
            raise RejectGoal("BAD_JOINTS")
        motor=[]
        for idx in range(1,8):
            m=self.agx_arm.get_motor_states(idx)
            if m is None or time.time()-m.timestamp>.20:
                raise RejectGoal("STALE_MOTOR_FEEDBACK")
            motor.append(float(m.msg.velocity))
        enabled=list(map(bool,self.agx_arm.get_joints_enable_status_list()))
        arm=str(status.msg.arm_status).split("(")[0]
        ctrl=str(status.msg.ctrl_mode).split("(")[0]
        errors=int(status.msg.err_code or 0)
        check_feedback(q,motor,arm,errors,ctrl,enabled,timestamp_age_s=age)
        return q,motor

 def _points(self,trajectory):
    points=[]
    for point in trajectory.points:
        sec=point.time_from_start.sec+point.time_from_start.nanosec/1e9
        points.append((point.positions,sec))
    return points

 def _on_goal(self, request):
    with self._goal_mutex:
        if not self._physical_enabled or self._author is None:
            self.get_logger().warn("FOLLOW_REJECTED_NOT_ACTUATION_ARMED")
            return GoalResponse.REJECT
        if self._goal_claimed or self._active_motion or self._stop_requested.is_set():
            self.get_logger().warn("FOLLOW_REJECTED_BUSY_OR_STOP_LATCHED")
            return GoalResponse.REJECT
        if self.vision_arbiter.mode.value!="LOCKED":
            self.get_logger().warn("FOLLOW_REJECTED_OLD_STOP_LATCH")
            return GoalResponse.REJECT
        token=self._author.get("goal_token")
        if not token or request.trajectory.header.frame_id!=token:
            self.get_logger().warn("FOLLOW_REJECTED_NO_ONE_SHOT_TOKEN")
            return GoalResponse.REJECT
        if not request.trajectory.points or len(request.trajectory.points)>2:
            return GoalResponse.REJECT
        try:
            current,_=self._snapshot()
            policy=validate_step(request.trajectory.joint_names,
                 self._points(request.trajectory),current)
        except (RejectGoal,ValueError) as e:
            self.get_logger().warn("FOLLOW_REJECTED_POLICY: "+str(e))
            return GoalResponse.REJECT
        if request.trajectory.header.stamp.sec or request.trajectory.header.stamp.nanosec:
            self.get_logger().warn("FOLLOW_REJECTED_NONZERO_START_TIME")
            return GoalResponse.REJECT
        # Persist one-time acceptance before ROS acknowledges goal. Service
        # restarts cannot re-use the same authorization to command a second move.
        try:
            fd=os.open(str(self._used_marker),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,"w") as rec:
                rec.write("goal_consumed_at=%s\n" % time.time())
                rec.flush()
                os.fsync(rec.fileno())
        except OSError as exc:
            self.get_logger().error("ONE_SHOT_MARKER_WRITE_FAILED: %s" % exc)
            return GoalResponse.REJECT
        self._goal_claimed=True
        self.get_logger().warn(
            "FOLLOW_SINGLE_SEGMENT_ACCEPTED joint2_delta=%.4f deg start=live "
            "speed_percent=3 no planned MultiWayPoint" % policy.delta_deg)
        return GoalResponse.ACCEPT

 def _on_cancel(self,handle):
    self._stop_requested.set()
    self.get_logger().warn("FOLLOW_ACTION_CANCEL_RECEIVED__ISSUE_HOLD")
    return CancelResponse.ACCEPT

 def _controlled_stop_hold_callback(self,request,response):
    self._stop_requested.set()
    with self._io_mutex:
        self._hold_result=super()._controlled_stop_hold_callback(request,response)
    return self._hold_result

 def _try_hold(self,why):
    self._stop_requested.set()
    with self._io_mutex:
        if self._hold_result is None:
            response=super()._controlled_stop_hold_callback(
                Trigger.Request(),Trigger.Response())
            self._hold_result=response
        self.get_logger().warn(
          "TRAJECTORY_STOP_HOLD %s STATUS=%s %s" %
          (why,self._hold_result.success,self._hold_result.message))
        return bool(self._hold_result.success)

 def _result(self,code,reason):
    out=FollowJointTrajectory.Result()
    out.error_code=int(code);out.error_string=str(reason)
    return out

 def _feedback(self,goal_handle,q,vel,target):
    feed=FollowJointTrajectory.Feedback()
    feed.header.stamp=self.get_clock().now().to_msg()
    feed.joint_names=list(JOINTS)
    feed.desired.positions=list(target)
    feed.actual.positions=list(q)
    feed.actual.velocities=list(vel)
    feed.error.positions=[a-b for a,b in zip(target,q)]
    goal_handle.publish_feedback(feed)

 def _execute_goal(self,goal_handle):
    self._active_motion=True
    moved=False
    try:
        if self._stop_requested.is_set():
            goal_handle.abort()
            return self._result(-4,"STOP_LATCHED_BEFORE_MOVE")
        measured,vel=self._snapshot()
        step=validate_step(goal_handle.request.trajectory.joint_names,
                 self._points(goal_handle.request.trajectory),measured)
        with self._io_mutex:
            if self._stop_requested.is_set():
                goal_handle.abort()
                return self._result(-4,"STOP_LATCHED_DURING_PREFLIGHT")
            # Vendor move_j is speed-limited point-to-point, not MoveJS.
            self.agx_arm.set_speed_percent(step.permitted_speed_percent)
            self.agx_arm.move_j(list(step.target))
            moved=True
        self.get_logger().warn("ROS2_LIMITED_MOVE_J_SENT: joint=%s delta_deg=%.3f"
                               % (step.joint,step.delta_deg))
        deadline=time.monotonic()+min(max(step.planned_duration_s*2,12),35)
        consecutive=0
        while time.monotonic()<deadline:
            if goal_handle.is_cancel_requested or self._stop_requested.is_set():
                ok=self._try_hold("ACTION_CANCEL_OR_OPERATOR_HOLD")
                if ok and goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    return self._result(0,"CANCELED_WITH_OPERATOR_HOLD")
                goal_handle.abort()
                return self._result(-4,"STOP_LATCHED_HOLD_RESULT_%s" % ok)
            try:
                q,v=self._snapshot()
                check_feedback(q,v,"NORMAL",0,"CAN_CTRL",[True]*7,
                    timestamp_age_s=0,expected_start=step.start,accepted_delta_deg=2.0)
            except (RejectGoal,ValueError) as e:
                self._try_hold("FEEDBACK_FAULT_"+str(e))
                goal_handle.abort()
                return self._result(-4,"FEEDBACK_INVALID_"+str(e))
            self._feedback(goal_handle,q,v,step.target)
            if converged(q,v,step.target):
                consecutive+=1
                if consecutive>=5:
                    goal_handle.succeed()
                    return self._result(0,"ONE_SEGMENT_REACHED__V121_MOVE_J")
            else:
                consecutive=0
            time.sleep(.055)
        self._try_hold("GOAL_TIMEOUT")
        goal_handle.abort()
        return self._result(-5,"GOAL_TIMEOUT_HOLD_REQUESTED")
    except BaseException as e:
        self.get_logger().error("FOLLOW_SINGLE_SEGMENT_FAILED: %r" % e)
        if moved:self._try_hold("EXECUTOR_EXCEPTION")
        goal_handle.abort()
        return self._result(-4,"EXECUTOR_EXCEPTION_"+type(e).__name__)
    finally:
        self._active_motion=False

 def _vision_guard_status_callback(self,request,response):
    res=super()._vision_guard_status_callback(request,response)
    res.message+=("; LIMITED_J2_ACTION_ARMED=%s; SINGLE_SEGMENT_MAX_DEG=2; "
                  "MOVE_JS_DISABLED; OTHER_TRAJECTORIES=BLOCKED" %
                  (self._physical_enabled and not self._goal_claimed))
    return res

 def destroy_node(self):
    if self._active_motion:
        self._try_hold("NODE_SHUTDOWN")
    if getattr(self,"_action",None):
        self._action.destroy()
    return super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node=None
    ex=MultiThreadedExecutor(num_threads=4)
    try:
        node=VisionNeroSingleSegmentNode()
        ex.add_node(node)
        ex.spin()
    except (KeyboardInterrupt,ExternalShutdownException):
        pass
    finally:
        if node:
            ex.remove_node(node)
            node.destroy_node()
        ex.shutdown()
        rclpy.try_shutdown()

if __name__=="__main__":main()
