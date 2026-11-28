"""Official Servo -> ros2_control JTC streaming test, GenericSystem only.

Isolated local domain 224. No actual NERO driver, SDK or physical output.
This tests JTC interpolation of the full rolling trajectory window.
"""
import argparse
import math
import json
import socket
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

from vision_station.nero_tcp import twist_intent

DOMAIN=224
NS="/vision_manual_fixture"
NAMES=[f"joint{i}" for i in range(1,8)]
POSE=[.15,-.4,.3,.9,.25,.25,.1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--servo-prefix",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--relay",type=Path)
    p.add_argument("--station-candidate",type=Path,
                   help="offline review bundle; recorded pose is replayed only")
    p.add_argument("--mesh-source-root",type=Path)
    group=p.add_mutually_exclusive_group()
    group.add_argument("--observe-pipeline",action="store_true")
    group.add_argument("--observe-stationary",action="store_true",
                       help="verify observation and fault latching without even synthetic motion")
    a=p.parse_args()
    a.observe_pipeline=a.observe_pipeline or a.observe_stationary
    if a.station_candidate is not None and not a.observe_pipeline:
        p.error("candidate requires an explicit observation fixture")
    if a.station_candidate is not None and (
            not a.station_candidate.is_absolute() or
            not a.station_candidate.resolve().is_relative_to("/srv/vision-data")):
        p.error("private NVMe candidate only")
    if a.observe_pipeline and a.relay is None:
        p.error("the software relay is required for observation tests")
    if os.environ.get("ROS_DOMAIN_ID")!=str(DOMAIN) or os.environ.get("ROS_LOCALHOST_ONLY")!="1":
        p.error("test-only local domain 224 required")
    if not all(x.is_absolute() and x.is_relative_to("/srv/vision-data") for x in (a.servo_prefix,a.output)):
        p.error("isolated NVMe paths required")
    import yaml,rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile,DurabilityPolicy
    from std_msgs.msg import String
    from sensor_msgs.msg import JointState
    from geometry_msgs.msg import TwistStamped
    from trajectory_msgs.msg import JointTrajectory
    from control_msgs.msg import JointTrajectoryControllerState
    from moveit_msgs.srv import ServoCommandType
    from moveit_msgs.msg import ServoStatus
    from moveit_configs_utils import MoveItConfigsBuilder
    from pipeline_observer_fixture import ObservationFixture

    cfg=(MoveItConfigsBuilder("agx_arm",package_name="agx_arm_moveit")
         .robot_description(file_path="config/agx_arm.urdf.xacro",mappings={
             "arm_type":"nero","effector_type":"none","revo2_type":"left",
             "tcp_offset_xyz":"0 0 0","tcp_offset_rpy":"0 0 0"})
         .robot_description_semantic(file_path="config/agx_arm.srdf.xacro",mappings={
             "arm_type":"nero","effector_type":"none","revo2_type":"left"})
         .robot_description_kinematics(file_path="config/kinematics.yaml")
         .joint_limits(file_path="config/joint_limits.yaml").to_moveit_configs())
    params={}
    for section in (cfg.robot_description,cfg.robot_description_semantic,cfg.robot_description_kinematics,cfg.joint_limits):
        params.update(section)
    candidate=None
    pose=POSE
    if a.station_candidate is not None:
        from ament_index_python.packages import get_package_share_directory
        from vision_station.nero_manual_station import load
        candidate=load(a.station_candidate,
                       mesh_root=get_package_share_directory("agx_arm_description"),
                       mesh_source_root=a.mesh_source_root)
        params["robot_description"]=candidate.urdf
        params["robot_description_semantic"]=candidate.srdf
        pose=list(candidate.historical_q)
        print("OFFLINE_STATION_CANDIDATE_LOADED",flush=True)
    model=ET.fromstring(params["robot_description"])
    control=model.find("ros2_control")
    if control is None or control.findtext("hardware/plugin")!="mock_components/GenericSystem":
        raise RuntimeError("not GenericSystem")
    if {j.get("name") for j in control.findall("joint")}!=set(NAMES):
        raise RuntimeError("unexpected controller joints")
    for joint in control.findall("joint"):
        for interface in joint.findall("state_interface"):
            if interface.get("name")=="position":
                interface.find("param").text=str(pose[NAMES.index(joint.get("name"))])
    params["robot_description"]=ET.tostring(model,encoding="unicode")
    params["moveit_servo"]={
        "move_group_name":"arm","command_in_type":"speed_units",
        "scale":{"linear":.1,"rotational":math.radians(30),"joint":.2},
        "publish_period":.02,"incoming_command_timeout":.15,
        "use_smoothing":False,"check_collisions":True,"check_octomap_collisions":False,
        "is_primary_planning_scene_monitor":True,
        "cartesian_command_in_topic":NS+"/twist",
        "joint_topic":NS+"/joint_states",
        "command_out_topic":NS+("/servo_trajectory" if a.relay else "/arm_controller/joint_trajectory"),
        "status_topic":NS+"/servo_status",
        "publish_joint_positions":True,"publish_joint_velocities":True,
        "publish_joint_accelerations":False,"command_out_type":"trajectory_msgs/JointTrajectory",
        "apply_twist_commands_about_ee_frame":True,
    }
    if a.observe_pipeline:
        from vision_station.nero_manual_pipeline import Routes
        params["moveit_servo"].update({
            "joint_topic":Routes.fixture().feedback_topic,
            "collision_check_rate":10.,
            "self_collision_proximity_threshold":.01,
            "scene_collision_proximity_threshold":.02,
        })
        params["use_sim_time"]=False
    profile=None
    if candidate is not None:
        from vision_station.nero_manual_composition import review_profile,servo_parameters,planning_parameters
        profile=review_profile(candidate)
        params["moveit_servo"]=servo_parameters(Routes.fixture(),profile)
        params.update(planning_parameters({"robot_description_planning":params["robot_description_planning"]},
                                         params["robot_description"],profile))
    a.output.mkdir(parents=True,exist_ok=True)
    servo_file=a.output/"servo.yaml";servo_file.write_text(yaml.safe_dump({NS+"/servo_node":{"ros__parameters":params}}))
    ctrl_file=a.output/"controllers.yaml"
    ctrl_file.write_text(yaml.safe_dump({
        NS+"/controller_manager":{"ros__parameters":{"update_rate":100,
             "arm_controller":{"type":"joint_trajectory_controller/JointTrajectoryController"},
             "joint_state_broadcaster":{"type":"joint_state_broadcaster/JointStateBroadcaster"}}},
        NS+"/arm_controller":{"ros__parameters":{"joints":NAMES,"command_interfaces":["position"],
            "state_interfaces":["position","velocity"],"allow_nonzero_velocity_at_trajectory_end":True,
            "allow_partial_joints_goal":False}}
    }))
    env=dict(os.environ,ROS_DOMAIN_ID=str(DOMAIN),ROS_LOCALHOST_ONLY="1")
    env.pop("ROS_STATIC_PEERS",None)
    env["AMENT_PREFIX_PATH"]=str(a.servo_prefix)+":"+env.get("AMENT_PREFIX_PATH","")
    env["LD_LIBRARY_PATH"]=str(a.servo_prefix/"lib")+":"+env.get("LD_LIBRARY_PATH","")
    ctx=Context();rclpy.init(args=[],context=ctx,domain_id=DOMAIN)
    node=rclpy.create_node("fixture",namespace=NS,context=ctx,start_parameter_services=False)
    executor=SingleThreadedExecutor(context=ctx);executor.add_node(node)
    children=[];logs=[];relay_socket=None;relay_samples=[]
    observer=ObservationFixture(node,params,station_candidate=candidate,profile=profile) if a.observe_pipeline else None
    def spawn(name,cmd):
        log=(a.output/(name+".log")).open("w");logs.append(log)
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env);children.append(child)
        return child
    def spin(seconds,callback=lambda:None):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            callback()
            if observer is not None:observer.tick()
            executor.spin_once(timeout_sec=.005)
            if relay_socket is not None:
                for _ in range(32):
                    try: data=relay_socket.recv(2048)
                    except BlockingIOError:break
                    if not data:break
                    relay_samples.append(json.loads(data))
    try:
        # Never share the isolated fixture domain with another runtime.
        spin(.9)
        assert all(name=="fixture" and ns==NS for name,ns in node.get_node_names_and_namespaces())
        manager=spawn("controller_manager",["/opt/ros/jazzy/lib/controller_manager/ros2_control_node",
            "--ros-args","-r","__ns:="+NS,"--params-file",str(ctrl_file),
            "-r","~/robot_description:="+NS+"/robot_description"])
        desc=node.create_publisher(String,NS+"/robot_description",QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        desc.publish(String(data=params["robot_description"]))
        spawner="/opt/ros/jazzy/lib/controller_manager/spawner"
        for controller in ("joint_state_broadcaster","arm_controller"):
            proc=spawn(controller,[spawner,controller,"-c",NS+"/controller_manager",
                                   "--controller-manager-timeout","12","--param-file",str(ctrl_file)])
            end=time.monotonic()+15
            while proc.poll() is None and time.monotonic()<end:spin(.1)
            if proc.poll()!=0:raise RuntimeError("controller spawn failed: "+controller)
        print("OFFICIAL_JTC_ACTIVE",flush=True)
        if a.relay:
            if not a.relay.is_absolute() or not a.relay.is_relative_to("/srv/vision-data"):
                raise RuntimeError("relay must be an isolated NVMe binary")
            relay_socket,peer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            relay_socket.setblocking(False)
            log=(a.output/"relay.log").open("w");logs.append(log)
            child=subprocess.Popen([str(a.relay),"--ros-args","-p","pipeline_namespace:="+NS],
                pass_fds=(peer.fileno(),),stdout=log,stderr=subprocess.STDOUT,
                env=dict(env,VISION_SERVO_RELAY_FD=str(peer.fileno())))
            children.append(child);peer.close()
        servo=spawn("servo",[str(a.servo_prefix/"lib/moveit_servo/servo_node"),
             "--ros-args","-r","__ns:="+NS,"-r","__node:=servo_node","--params-file",str(servo_file)])
        joint_states=[];samples=[];windows=[];statuses=[]
        def receive_state(state):
            joint_states.append(state)
            if observer is not None:observer.receive_mock_state(state)
        sub=node.create_subscription(JointState,NS+"/joint_states",receive_state,1)
        st=node.create_subscription(JointTrajectoryControllerState,NS+"/arm_controller/controller_state",samples.append,1)
        traj=node.create_subscription(JointTrajectory,NS+"/arm_controller/joint_trajectory",windows.append,1)
        status=node.create_subscription(ServoStatus,NS+"/servo_status",statuses.append,1)
        twist=node.create_publisher(TwistStamped,NS+"/twist",1)
        cli=node.create_client(ServoCommandType,NS+"/servo_node/switch_command_type")
        end=time.monotonic()+18
        while not cli.service_is_ready() and time.monotonic()<end:
            if servo.poll() is not None:raise RuntimeError("Servo exited")
            spin(.1)
        if not cli.service_is_ready():raise RuntimeError("Servo service unavailable")
        future=cli.call_async(ServoCommandType.Request(command_type=ServoCommandType.Request.TWIST))
        end=time.monotonic()+5
        while not future.done() and time.monotonic()<end:spin(.1)
        if not future.done() or not future.result().success:raise RuntimeError("TWIST mode not selected")
        spin(.75)
        if not samples:raise RuntimeError("no controller state")
        if observer is not None:
            observer.confirmed_twist=True
            observer.prepare(spin,pose)
            if a.observe_stationary:
                observer.test_loss(spin)
                (a.output/"stationary_observation_result.json").write_text(json.dumps({
                    "status":"PASS","independentObservedState":True,
                    "monitorVerified":True,"feedbackLossLatched":True,
                    "sceneChangeLatched":True,"syntheticOnly":True,
                    "dynamicMotionTested":False,"realStationAcceptance":False,
                    "fullStationCandidate":candidate is not None},indent=2)+"\n")
                print("STATIONARY_OBSERVATION_ONLY_PASS",flush=True)
                return
        next_cmd=0.
        def drive(axis=None):
            nonlocal next_cmd
            if observer is not None:observer.check()
            if time.monotonic()<next_cmd:return
            next_cmd=time.monotonic()+.02
            msg=TwistStamped();msg.header.stamp=node.get_clock().now().to_msg();msg.header.frame_id="base_link"
            if axis:
                v=twist_intent({"frame":"BASE","linearMmS":5 if candidate is not None else 10,"angularDegS":5},axis,1)
                msg.twist.linear.x,msg.twist.linear.y,msg.twist.linear.z=v["linear"]
                msg.twist.angular.x,msg.twist.angular.y,msg.twist.angular.z=v["angular"]
            twist.publish(msg)
        before=len(samples);start=dict(zip(samples[-1].joint_names,samples[-1].reference.positions))
        spin(2.,lambda:drive("Z" if candidate is not None else "X"))
        spin(.6,lambda:drive())
        spin(.4)
        if not windows or not statuses:raise RuntimeError("no Servo output")
        valid=[s for s in samples[before:] if set(s.joint_names)==set(NAMES)
               and len(s.reference.positions)==7 and all(math.isfinite(x) for x in s.reference.positions)]
        if not valid:raise RuntimeError("no JTC reference")
        if profile is not None:
            # Check every JTC reference against the same candidate envelope
            # that the guarded owner would enforce; no motion is executed.
            for sample in valid:
                positions=dict(zip(sample.joint_names,sample.reference.positions))
                velocities=dict(zip(sample.joint_names,sample.reference.velocities))
                assert profile.contains(tuple(positions[n] for n in NAMES))
                assert len(velocities)==7 and all(math.isfinite(velocities[n]) and
                           abs(velocities[n])<=limit+1e-8 for n,limit in zip(NAMES,profile.joint_velocity_max))
            print("REVIEW_PROFILE_JTC_ENVELOPE_PASS",len(valid),flush=True)
        displacement=max(abs(q-start[n]) for s in valid for n,q in zip(s.joint_names,s.reference.positions))
        if displacement<=1e-5:raise RuntimeError("Servo trajectory not executed by JTC")
        print("SERVO_TO_JTC_PASS","windows",len(windows),"sampled_references",len(valid),
              "max_synthetic_displacement_rad",round(displacement,7),
              "status_codes",sorted(set(s.code for s in statuses)),flush=True)
        if a.relay:
            if not relay_samples or not any(max(abs(q-p) for q,p in zip(s["positions"],pose))>1e-5 for s in relay_samples):
                raise RuntimeError("native source-checked relay delivered no valid references")
            if profile is not None:
                for reference in relay_samples:
                    assert profile.contains(reference["positions"])
                    assert len(reference["velocities"])==7 and all(
                        math.isfinite(x) and abs(x)<=limit+1e-8 for x,limit in zip(reference["velocities"],profile.joint_velocity_max))
                print("REVIEW_PROFILE_RELAY_ENVELOPE_PASS",len(relay_samples),flush=True)
            print("NATIVE_GID_RELAY_PASS","samples",len(relay_samples),flush=True)
        if observer is not None:
            observer.check()
            matched=observer.monitor.authority.matched_scene_updates
            assert matched>0, "no timestamp-aligned scene updates during motion"
            print("TIMESTAMP_ALIGNED_SCENE_PASS",matched,observer.monitor.last_timestamped_update,flush=True)
            observer.test_loss(spin)
            (a.output/"observation_result.json").write_text(json.dumps({
                "status":"PASS","independentObservedState":True,
                "monitorVerified":True,"feedbackLossLatched":True,
                "sceneChangeLatched":True,"syntheticOnly":True,
                "realStationAcceptance":False,
                "matchedSceneUpdates":matched,"fullStationCandidate":candidate is not None,
                "reviewProfileEnvelopeVerified":profile is not None,
                "relaySamples":len(relay_samples)},indent=2)+"\n")
        print("OFFLINE_ONLY_NO_HARDWARE_OUTPUT",flush=True)
    finally:
        if observer is not None:observer.close()
        for child in reversed(children):
            if child.poll() is None:child.terminate()
        for child in reversed(children):
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        if relay_socket is not None:relay_socket.close()
        executor.shutdown();node.destroy_node();rclpy.shutdown(context=ctx)
        for log in logs:log.close()


if __name__=="__main__":main()
