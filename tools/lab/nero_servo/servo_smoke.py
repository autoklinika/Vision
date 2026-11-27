"""Offline upstream MoveIt Servo integration check; no CAN, no controller.

Only synthetic JointState messages feed the model. Servo outputs are captured
as test data. The process never uses domain 181, a hardware driver or an
actual robot controller. Run against the explicit isolated NVMe overlay.
"""
import argparse
import math
import os
from pathlib import Path
import subprocess
import time

from vision_station.nero_tcp import twist_intent
from vision_station.ros_nero_servo_bridge import CandidateReceiver

DOMAIN = 223
NS = "/vision_servo_fixture"
NAMES = [f"joint{i}" for i in range(1, 8)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--servo-prefix", required=True, type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--guarded-bridge",action="store_true",
                        help="Use the actual installed arbiter with a fake SDK; no actuator.")
    parser.add_argument("--live-observer",action="store_true",
                        help="Copy only existing read-only joint feedback to isolated Servo; no Twist publication.")
    args=parser.parse_args()
    if args.live_observer and args.guarded_bridge:
        parser.error("choose live feedback or synthetic guarded test")
    if os.environ.get("ROS_DOMAIN_ID")!=str(DOMAIN) or os.environ.get("ROS_LOCALHOST_ONLY")!="1":
        parser.error("isolated localhost domain 223 required")
    if not args.servo_prefix.is_relative_to("/srv/vision-data") or not args.output.is_relative_to("/srv/vision-data"):
        parser.error("explicit NVMe paths required")
    import yaml
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import JointState
    from geometry_msgs.msg import TwistStamped
    from trajectory_msgs.msg import JointTrajectory
    from moveit_msgs.msg import ServoStatus
    from moveit_msgs.srv import ServoCommandType
    from moveit_configs_utils import MoveItConfigsBuilder

    cfg=(MoveItConfigsBuilder("agx_arm",package_name="agx_arm_moveit")
         .robot_description(file_path="config/agx_arm.urdf.xacro",mappings={
             "arm_type":"nero","effector_type":"none","revo2_type":"left",
             "tcp_offset_xyz":"0 0 0","tcp_offset_rpy":"0 0 0"})
         .robot_description_semantic(file_path="config/agx_arm.srdf.xacro",mappings={
             "arm_type":"nero","effector_type":"none","revo2_type":"left"})
         .robot_description_kinematics(file_path="config/kinematics.yaml")
         .joint_limits(file_path="config/joint_limits.yaml").to_moveit_configs())
    params={}
    for section in (cfg.robot_description,cfg.robot_description_semantic,
                    cfg.robot_description_kinematics,cfg.joint_limits):
        params.update(section)
    params["moveit_servo"]={
        "move_group_name":"arm","command_in_type":"speed_units",
        "scale":{"linear":.1,"rotational":math.radians(30),"joint":.2},
        "publish_period":.02,"incoming_command_timeout":.15,
        "use_smoothing":False,"check_collisions":True,
        "is_primary_planning_scene_monitor":True,"check_octomap_collisions":False,
        "cartesian_command_in_topic":NS+"/twist",
        "joint_topic":NS+"/joint_states","command_out_topic":NS+"/captured_trajectory",
        "status_topic":NS+"/status","publish_joint_positions":True,"publish_joint_velocities":True,
        "publish_joint_accelerations":False,"command_out_type":"trajectory_msgs/JointTrajectory",
        "apply_twist_commands_about_ee_frame":True,
    }
    args.output.mkdir(parents=True,exist_ok=True)
    file=args.output/"servo_fixture.yaml"
    file.write_text(yaml.safe_dump({NS+"/servo_node":{"ros__parameters":params}}))
    exe=args.servo_prefix/"lib/moveit_servo/servo_node"
    env=dict(os.environ)
    env["AMENT_PREFIX_PATH"]=str(args.servo_prefix)+":"+env.get("AMENT_PREFIX_PATH","")
    env["LD_LIBRARY_PATH"]=str(args.servo_prefix/"lib")+":"+env.get("LD_LIBRARY_PATH","")
    env["ROS_DOMAIN_ID"]=str(DOMAIN)
    env["ROS_LOCALHOST_ONLY"]="1"
    env.pop("ROS_STATIC_PEERS",None)
    context=Context()
    rclpy.init(args=[],context=context,domain_id=DOMAIN)
    node=rclpy.create_node("capture",namespace=NS,context=context,start_parameter_services=False)
    executor=SingleThreadedExecutor(context=context)
    executor.add_node(node)
    log=(args.output/"servo_fixture.log").open("w")
    child=None
    try:
        # Test fixture starts only the upstream algorithm, never ros2_control.
        child=subprocess.Popen([str(exe),"--ros-args","-r","__ns:="+NS,
                                "-r","__node:=servo_node","--params-file",str(file)],
                                stdout=log,stderr=subprocess.STDOUT,env=env)
        joints=node.create_publisher(JointState,NS+"/joint_states",1)
        # Live-shadow mode has NO command publisher, even in the test domain.
        twists=None if args.live_observer else node.create_publisher(TwistStamped,NS+"/twist",10)
        if args.live_observer:
            from moveit_msgs.msg import PlanningSceneComponents
            from moveit_msgs.srv import GetPlanningScene
            from vision_station.nero import MAX_BYTES, valid_observation, fresh
            from vision_station.luxonis import private_directory, read_json
            directory=private_directory(Path("/run/user/1000/vision-fluent2-nero"))
            used_stamps=set()
            last=None
            def relay():
                nonlocal last
                v=read_json(directory/"observation.json",MAX_BYTES)
                now=time.time()
                if (v is not None and valid_observation(v) and v["graph"]=="ACTIVE"
                        and fresh(v["capturedAt"],now,.8) and v["joints"] is not None
                        and fresh(v["joints"]["stamp"],now,.8)):
                    packet=v["joints"]
                    if packet["stamp"] not in used_stamps:
                        j=JointState()
                        ns=round(packet["stamp"]*1e9)
                        j.header.stamp.sec,j.header.stamp.nanosec=divmod(ns,1_000_000_000)
                        j.name=[r["joint"] for r in packet["rows"]]
                        j.position=[r["positionRad"] for r in packet["rows"]]
                        if all(r["velocityRadS"] is not None for r in packet["rows"]):
                            j.velocity=[r["velocityRadS"] for r in packet["rows"]]
                        joints.publish(j)
                        used_stamps.add(packet["stamp"]);last=j
                executor.spin_once(timeout_sec=.02)
            service=None
            end=time.monotonic()+15
            while time.monotonic()<end and service is None:
                if child.poll() is not None:raise RuntimeError("Servo process exited")
                relay()
                matches=[n for n,types in node.get_service_names_and_types()
                         if n.endswith("/get_planning_scene") and "moveit_msgs/srv/GetPlanningScene" in types]
                if len(matches)==1:service=node.create_client(GetPlanningScene,matches[0])
            if service is None:raise RuntimeError("planning scene service not discovered")
            end=time.monotonic()+5
            while time.monotonic()<end:relay()
            if last is None or not service.service_is_ready():raise RuntimeError("no live feedback / service")
            req=GetPlanningScene.Request()
            req.components.components=PlanningSceneComponents.ROBOT_STATE
            future=service.call_async(req)
            end=time.monotonic()+5
            while not future.done() and time.monotonic()<end:relay()
            if not future.done():raise RuntimeError("planning scene readback timed out")
            state=future.result().scene.robot_state.joint_state
            by_name=dict(zip(state.name,state.position))
            if not all(n in by_name for n in NAMES):raise RuntimeError("incomplete Servo model readback")
            expected=dict(zip(last.name,last.position))
            err=max(abs(by_name[n]-expected[n]) for n in NAMES)
            if err>1e-4:raise RuntimeError("Servo model does not match real observer feedback")
            print("LIVE_FEEDBACK_TO_SERVO_PASS","axes",len(NAMES),"distinct_samples",len(used_stamps),
                  "max_error_rad",round(err,8),"twist_publishers",0,flush=True)
            return
        received=[];statuses=[];arrival=[]
        def record(m):
            received.append(m)
            if m.points:
                stamp=m.header.stamp.sec+m.header.stamp.nanosec/1e9
                p=m.points[-1].time_from_start
                now=node.get_clock().now().nanoseconds/1e9
                arrival.append((now-stamp,stamp+p.sec+p.nanosec/1e9-now))
        sub=node.create_subscription(JointTrajectory,NS+"/captured_trajectory",record,1)
        status_sub=node.create_subscription(ServoStatus,NS+"/status",statuses.append,1)
        # Synthetic bent pose, NOT physical calibration or a motion target.
        pose=[.15,-.4,.3,.9,.25,.25,.1]
        verdicts=[]
        bridge=None
        if args.guarded_bridge:
            from types import SimpleNamespace
            from agx_arm_ctrl.vision_nero_arbiter import NeroCommandArbiter
            # Use the exact arbiter code from the installed guarded workspace.
            # The SDK object only provides simulated readback, no command methods.
            node.vision_arbiter=NeroCommandArbiter()
            node._get_status_string=lambda:("NORMAL",0)
            node.agx_arm=SimpleNamespace(get_joint_angles=lambda:SimpleNamespace(timestamp=time.time()-.01))
            bridge=CandidateReceiver(node,topic=NS+"/captured_trajectory",source=NS+"/servo_node",
                                     on_verdict=verdicts.append)
        # MoveIt's current-state monitor can suppress callbacks when all
        # positions are identical. Alternate a negligible synthetic change
        # in joint1 to exercise state-update notifications.
        sequence=0
        def sample(axis=None,frame="BASE"):
            nonlocal sequence
            sequence+=1
            j=JointState();j.header.stamp=node.get_clock().now().to_msg()
            q=list(pose);q[0]+=(sequence%2)*1e-5
            j.name=NAMES;j.position=q;j.velocity=[0.]*7;joints.publish(j)
            if axis:
                v=twist_intent({"frame":frame,"linearMmS":10,"angularDegS":5},axis,1)
                msg=TwistStamped();msg.header.stamp=node.get_clock().now().to_msg()
                msg.header.frame_id=v["frameId"]
                msg.twist.linear.x,msg.twist.linear.y,msg.twist.linear.z=v["linear"]
                msg.twist.angular.x,msg.twist.angular.y,msg.twist.angular.z=v["angular"]
                twists.publish(msg)
            # Drain callbacks independently of the sample rate. One spin per
            # sample builds an artificial backlog at 50 Hz Servo output.
            until=time.monotonic()+.02
            while time.monotonic()<until:
                executor.spin_once(timeout_sec=min(.002,max(0.,until-time.monotonic())))
        service=node.create_client(ServoCommandType,NS+"/servo_node/switch_command_type")
        end=time.monotonic()+15
        while time.monotonic()<end and not service.service_is_ready():
            if child.poll() is not None:raise RuntimeError("Servo process exited")
            sample()
        if not service.service_is_ready():raise RuntimeError("Servo service not discovered")
        future=service.call_async(ServoCommandType.Request(command_type=ServoCommandType.Request.TWIST))
        end=time.monotonic()+5
        while not future.done() and time.monotonic()<end:sample()
        if not future.done() or not future.result().success:raise RuntimeError("TWIST not selected")
        print("UPSTREAM_SERVO_TWIST_MODE_PASS",flush=True)
        end=time.monotonic()+1.5
        while time.monotonic()<end:sample()
        print("STATE_SUBSCRIBERS",joints.get_subscription_count(),"TWIST_SUBSCRIBERS",twists.get_subscription_count(),flush=True)
        print("SERVO_GRAPH",node.get_node_names_and_namespaces(),flush=True)
        print("SERVO_PUBLISHERS",[(x.node_name,x.node_namespace,x.topic_type) for x in node.get_publishers_info_by_topic(NS+"/captured_trajectory")],flush=True)
        for frame,axis in (("BASE","X"),("TOOL","YAW")):
            received.clear();statuses.clear();arrival.clear();verdicts.clear()
            end=time.monotonic()+2
            while time.monotonic()<end:
                if child.poll() is not None:raise RuntimeError("Servo process exited")
                sample(axis,frame)
            valid=[m for m in received if set(m.joint_names)==set(NAMES) and m.points and
                   all(len(p.positions)==7 and all(math.isfinite(q) for q in p.positions) for p in m.points)]
            moving=[m for m in valid if any(abs(q-pose[NAMES.index(n)])>2e-5
                    for n,q in zip(m.joint_names,m.points[-1].positions))]
            print(frame,axis,"valid_trajectories",len(valid),"nonzero_targets",len(moving),
                  "statuses",sorted(set(s.code for s in statuses)),flush=True)
            if not moving:raise RuntimeError("no nonzero simulated trajectory for "+frame)
            print("ARRIVAL_SECONDS","header_age",tuple(round(f(x[0] for x in arrival),4) for f in (min,max)),
                  "remaining_horizon",tuple(round(f(x[1] for x in arrival),4) for f in (min,max)),flush=True)
            if bridge is not None:
                valid_guard=[v for v in verdicts if v.accepted_format and v.guard_reason=="CAN_TX_DISABLED_PENDING_HARDWARE_ACCEPTANCE"]
                print("GUARDED_BRIDGE",frame,"valid",len(valid_guard),"rejections",
                      sorted(set(v.reason for v in verdicts if not v.accepted_format)),
                      "guard_reasons",sorted(set(v.guard_reason or v.reason for v in verdicts)),
                      "provenance",bridge.last_provenance,flush=True)
                if not valid_guard or any(v.can_execute for v in verdicts):
                    raise RuntimeError("guarded bridge did not validate locked candidates")
            m=moving[-1]
            now=node.get_clock().now().nanoseconds/1e9
            stamp=m.header.stamp.sec+m.header.stamp.nanosec/1e9
            print("TRAJECTORY_SCHEMA",m.header.frame_id,"age",round(now-stamp,4),
                  "joint_count",len(m.joint_names),"points",len(m.points),
                  "durations",[round(p.time_from_start.sec+p.time_from_start.nanosec/1e9,5) for p in m.points],
                  "velocity_lengths",[len(p.velocities) for p in m.points],flush=True)
        if bridge is not None:
            # This is ONLY the in-memory test arbiter, not the physical HOLD.
            node.vision_arbiter.request_stop("NORMAL")
            verdicts.clear()
            end=time.monotonic()+1
            while time.monotonic()<end:sample("X")
            if not any(v.accepted_format and v.guard_reason=="STOP_ALREADY_LATCHED" for v in verdicts):
                raise RuntimeError("HOLD latch was not preserved")
            if any(v.can_execute for v in verdicts):raise RuntimeError("unexpected execution permission")
            print("EXISTING_ARBITER_HOLD_LATCH_PASS",flush=True)
        print("OFFLINE_NERO_SERVO_PASS",flush=True)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill();child.wait(timeout=5)
        executor.shutdown();node.destroy_node();rclpy.shutdown(context=context);log.close()


if __name__=="__main__":
    main()
