#!/usr/bin/env python3
"""Actual ROS2 FollowJointTrajectory action integration HIL with FAKE AgileX SDK.

Domain 178 only; fake Arm never calls SocketCAN; host can0 TX must not change.
Exercises the very same guarded adapter ActionServer class used on real NERO.
"""
import argparse
import datetime as dt
import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

if os.environ.get("ROS_DOMAIN_ID")!="178" or os.environ.get("VISION_NERO_ISOLATED_TEST")!="1":
    raise SystemExit("WRONG_DOMAIN_OR_TEST_GUARD")
os.environ["ROS_LOCALHOST_ONLY"]="1"
os.environ["VISION_NERO_ISOLATED_FAKE"]="1"

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from action_msgs.msg import GoalStatus
from agx_arm_ctrl.vision_nero_single_segment_node import VisionNeroSingleSegmentNode
from agx_arm_ctrl.vision_nero_single_segment_policy import JOINTS,URDF_LIMITS_RAD

BASE=Path("/srv/vision-data/experiments/c7-nero-follow-action-20261120")
TX=Path("/sys/class/net/can0/statistics/tx_packets")
INITIAL=[math.radians(x) for x in [90.321,56.848,-.800,106.271,.237,-.880,23.330]]

class FakeAgileX:
    _vision_offline_fake=True
    def __init__(self):
        self.q=INITIAL[:]
        self.goal=INITIAL[:]
        self.last=time.monotonic()
        self.hold_events=0
        self.move_events=0
        self.speed=3
        self.lock=threading.RLock()
    def update(self):
        now=time.monotonic()
        with self.lock:
            dt_=min(0.10,max(0,now-self.last))
            self.last=now
            maxmove=math.radians(0.5)*dt_  # 0.5 deg/s
            for i in range(7):
                delta=self.goal[i]-self.q[i]
                self.q[i]+=max(-maxmove,min(maxmove,delta))
    def state(self):
        self.update()
        return list(self.q)
    def get_joint_angles(self):
        return SimpleNamespace(timestamp=time.time(),msg=self.state())
    def get_arm_status(self):
        return SimpleNamespace(timestamp=time.time(),
            msg=SimpleNamespace(arm_status="NORMAL",ctrl_mode="CAN_CTRL",err_code=0))
    def get_motor_states(self,i):
        self.update()
        with self.lock:
            delta=self.goal[i-1]-self.q[i-1]
        v=math.copysign(math.radians(.5),delta) if abs(delta)>math.radians(.02) else 0.
        return SimpleNamespace(timestamp=time.time(),msg=SimpleNamespace(velocity=v,current=.2))
    def get_joints_enable_status_list(self):
        return [True]*7
    def get_config(self):
        return {"joint_limits":dict(zip(JOINTS,URDF_LIMITS_RAD))}
    def set_speed_percent(self,value):
        if value!=3:raise AssertionError("WRONG_SPEED")
        self.speed=value
    def move_j(self,target):
        if len(target)!=7:raise AssertionError("BAD_TARGET")
        with self.lock:
            current=self.state()
            if max(abs(a-b) for a,b in zip(target,current))<math.radians(.025):
                self.hold_events+=1
            else:
                self.move_events+=1
            self.goal=list(target)
    def disconnect(self): pass
    def is_ok(self):return True

fake=FakeAgileX()
def fake_init(self):
    self.agx_arm=fake
    self.arm_joint_names=list(JOINTS)
    self.arm_joint_count=7
    self.firmware_version="1.22"
    self.firmware_profile="v121"

# Monkeypatch only in this isolated process. No real CAN owner exists here.
VisionNeroSingleSegmentNode._init_agx_arm=fake_init
VisionNeroSingleSegmentNode._publish_thread=lambda self:None
VisionNeroSingleSegmentNode._setup_publishers=lambda self:None

def run(mode):
    before=int(TX.read_text())
    with tempfile.TemporaryDirectory(prefix="c7-nero-fake-action-") as t:
        config=Path(t)/"one_shot_lab_authorization.json"
        token="VISION_NERO_OFFLINE_FAKE_ACTION"
        config.write_text(json.dumps({
            "phase":"LIMITED_ONE_SEGMENT_FIRST_MOTION",
            "max_delta_deg":2.0,"joint":"joint2",
            "enabled_by_operator":True,"expires_unix_time":time.time()+120,
            "goal_token":token}))
        rclpy.init(args=[
         "--ros-args","-p","arm_type:=nero","-p","effector_type:=none",
         "-p","auto_enable:=false","-p","control_enabled:=false",
         "-p","physical_hold_enabled:=true",
         "-p","physical_single_segment_enabled:=true",
         "-p","one_shot_authorization_file:="+str(config),
         "-r","__ns:=/nero_guarded"])
        node=VisionNeroSingleSegmentNode()
        exec=MultiThreadedExecutor(num_threads=4)
        exec.add_node(node)
        spin=threading.Thread(target=exec.spin,daemon=True)
        spin.start()
        client=rclpy.create_node("vision_nero_fake_action_client")
        ac=ActionClient(client,FollowJointTrajectory,"/nero_guarded/follow_joint_trajectory_lab")
        try:
            assert ac.wait_for_server(timeout_sec=4),"ACTION_SERVER_NOT_READY"
            msg=FollowJointTrajectory.Goal()
            msg.trajectory.header.frame_id=token
            msg.trajectory.joint_names=list(JOINTS)
            first=JointTrajectoryPoint()
            first.positions=INITIAL[:]
            first.time_from_start=Duration(sec=0)
            end=JointTrajectoryPoint()
            end.positions=INITIAL[:]
            end.positions[1]+=math.radians(1.25)
            end.time_from_start=Duration(sec=12)
            msg.trajectory.points=[first,end]
            sent=ac.send_goal_async(msg)
            rclpy.spin_until_future_complete(client,sent,timeout_sec=5)
            assert sent.done() and sent.result().accepted,"ACTION_NOT_ACCEPTED"
            handle=sent.result()
            if mode=="cancel":
                time.sleep(.6)
                cancel=handle.cancel_goal_async()
                rclpy.spin_until_future_complete(client,cancel,timeout_sec=5)
                assert cancel.done() and cancel.result().goals_canceling, "CANCEL_REJECTED"
            result=handle.get_result_async()
            rclpy.spin_until_future_complete(client,result,timeout_sec=22)
            assert result.done(), "ACTION_TIMEOUT"
            response=result.result()
            print("FAKE_FOLLOW_ACTION_RESULT",mode,
                "ROS_STATUS",response.status,
                "ACTION_ERROR_CODE",response.result.error_code,
                "ACTION_MSG",response.result.error_string,
                "MOVE_J_COMMANDS",fake.move_events,"HOLD_J_COMMANDS",fake.hold_events,
                "DELTA_J2_DEG",round(math.degrees(fake.q[1]-INITIAL[1]),4),flush=True)
            if mode=="success":
                assert response.status==GoalStatus.STATUS_SUCCEEDED
                assert response.result.error_code==0
                assert fake.move_events==1 and fake.hold_events==0
                assert abs(math.degrees(fake.q[1]-INITIAL[1])-1.25)<.15
            else:
                assert response.status==GoalStatus.STATUS_CANCELED
                assert fake.move_events==1 and fake.hold_events>=1
                assert abs(math.degrees(fake.q[1]-INITIAL[1]))<1.25
            # Second goal must be REJECTED regardless of success or cancel.
            again=ac.send_goal_async(msg)
            rclpy.spin_until_future_complete(client,again,timeout_sec=5)
            assert again.done() and not again.result().accepted, "ONE_SHOT_GATE_FAILED"
        finally:
            client.destroy_node()
            exec.remove_node(node)
            node.destroy_node()
            exec.shutdown(timeout_sec=2)
            spin.join(timeout=2)
            rclpy.try_shutdown()
    after=int(TX.read_text())
    print("FAKE_CAN_TX_BEFORE_AFTER",before,after,flush=True)
    assert before==after, "REAL_CAN_TX_IN_MOCK"

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--mode",choices=["success","cancel"],required=True)
    args=a.parse_args()
    run(args.mode)
