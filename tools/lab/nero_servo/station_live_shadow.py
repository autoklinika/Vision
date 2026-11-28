"""One-way live-state model review, no physical motion or controller.

ROS 181 is subscription-only, apart from a read-only parameter query.
ROS 232 has a separate official Servo PSM; optional virtual GenericSystem
JTC start verification uses live joint measurements only. No relay, motion
publisher, command-type selection, physical hardware plugin or CAN access.
The review cannot grant motion permission, even on a passing run.
"""
import argparse
from copy import deepcopy
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

from vision_station.nero import NODE, DOMAIN, PARAMS, parse_arm, parse_motors, parse_joints
from vision_station.nero_manual import AGE
from vision_station.nero_manual_station import load
from vision_station.ros_nero_manual_pipeline import joint_vector, scene_fingerprint
from pipeline_observer_fixture import ObservationFixture

SHADOW=232
NS="/vision_station_shadow"
SOURCE_JOINT="/nero_guarded/feedback/joint_states"
OBSERVED=NS+"/observed_joint_states"
SCENE=NS+"/scene_input"

def stamp(message):
    t=message.header.stamp
    return t.sec+t.nanosec/1e9

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("candidate","mesh-source-root","servo-prefix","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--verify-live-jtc",action="store_true",
                   help="initialize only an isolated virtual JTC from two fresh measurements")
    a=p.parse_args()
    if os.environ.get("ROS_DOMAIN_ID")!=str(SHADOW) or os.environ.get("ROS_LOCALHOST_ONLY")!="1":
        p.error("fixed isolated local shadow domain required")
    if not all(x.is_absolute() and x.resolve().is_relative_to("/srv/vision-data")
               for x in (a.candidate,a.mesh_source_root,a.servo_prefix,a.output)):
        p.error("private NVMe paths required")
    if a.output.exists():
        p.error("never overwrite a shadow review")
    os.umask(0o077)
    a.output.mkdir(mode=0o700)
    import rclpy
    import yaml
    from ament_index_python.packages import get_package_share_directory
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.serialization import deserialize_message
    from rcl_interfaces.srv import GetParameters
    from rclpy.parameter import parameter_value_to_python
    from sensor_msgs.msg import JointState
    from std_msgs.msg import String
    from control_msgs.msg import JointTrajectoryControllerState
    from controller_manager_msgs.srv import ListControllers, ListHardwareComponents
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from vision_station.nero_manual_composition import review_profile, planning_parameters
    from vision_station.nero_manual_start import seed_virtual_model, POSITION_ERROR, CONTROLLER_AGE
    from vision_station.ros_nero_manual_pipeline import controller_evidence, endpoint_node
    from vision_station.nero_manual import JOINTS, vector7

    from diagnostic_msgs.msg import DiagnosticArray
    from moveit_msgs.msg import PlanningScene
    from moveit_msgs.srv import GetPlanningScene
    from moveit_configs_utils import MoveItConfigsBuilder

    c=load(a.candidate,mesh_root=get_package_share_directory("agx_arm_description"),
           mesh_source_root=a.mesh_source_root)
    scene=deserialize_message(c.scene,PlanningScene)
    assert scene.is_diff and scene.robot_state.is_diff and not scene.robot_state.joint_state.name
    assert len(scene.world.collision_objects)==len(scene.robot_state.attached_collision_objects)==1
    assert not scene.world.octomap.octomap.data
    cfg=(MoveItConfigsBuilder("agx_arm",package_name="agx_arm_moveit")
         .robot_description(file_path="config/agx_arm.urdf.xacro",mappings={
            "arm_type":"nero","effector_type":"none","revo2_type":"left",
            "tcp_offset_xyz":"0 0 0","tcp_offset_rpy":"0 0 0"})
         .robot_description_semantic(file_path="config/agx_arm.srdf.xacro",mappings={
            "arm_type":"nero","effector_type":"none","revo2_type":"left"})
         .robot_description_kinematics(file_path="config/kinematics.yaml")
         .joint_limits(file_path="config/joint_limits.yaml").to_moveit_configs())
    cfg_params={**cfg.robot_description_kinematics,**cfg.joint_limits,
                "robot_description":c.urdf,"robot_description_semantic":c.srdf,"use_sim_time":False}
    # Output is an unconsumed topic in the shadow domain; no input
    # publisher or controller process is started.
    cfg_params["moveit_servo"]={
        "move_group_name":"arm","command_in_type":"speed_units",
        "scale":{"linear":.1,"rotational":math.radians(30),"joint":.2},
        "publish_period":.02,"incoming_command_timeout":.15,
        "use_smoothing":False,"check_collisions":True,"check_octomap_collisions":False,
        "is_primary_planning_scene_monitor":True,"monitored_planning_scene_topic":SCENE,
        "cartesian_command_in_topic":NS+"/unused_twist","joint_topic":OBSERVED,
        "command_out_topic":NS+"/unused_trajectory","status_topic":NS+"/status",
        "publish_joint_positions":True,"publish_joint_velocities":True,
        "publish_joint_accelerations":False,"command_out_type":"trajectory_msgs/JointTrajectory",
        "apply_twist_commands_about_ee_frame":True,
    }
    cfg_file=a.output/"servo.yaml"
    cfg_file.write_text(yaml.safe_dump({NS+"/servo_node":{"ros__parameters":cfg_params}}))
    env=dict(os.environ,ROS_DOMAIN_ID=str(SHADOW),ROS_LOCALHOST_ONLY="1")
    env.pop("ROS_STATIC_PEERS",None)
    env["AMENT_PREFIX_PATH"]=str(a.servo_prefix)+":"+env.get("AMENT_PREFIX_PATH","")
    env["LD_LIBRARY_PATH"]=str(a.servo_prefix/"lib")+":"+env.get("LD_LIBRARY_PATH","")
    source=Context();target=Context()
    rclpy.init(args=[],context=source,domain_id=DOMAIN)
    rclpy.init(args=[],context=target,domain_id=SHADOW)
    reader=rclpy.create_node("vision_station_shadow_reader",context=source,
                             enable_rosout=False,start_parameter_services=False)
    view=rclpy.create_node("review",namespace=NS,context=target,
                           enable_rosout=False,start_parameter_services=False)
    rs=SingleThreadedExecutor(context=source);rs.add_node(reader)
    ts=SingleThreadedExecutor(context=target);ts.add_node(view)
    specs={
        "joints":(SOURCE_JOINT,"sensor_msgs/msg/JointState",JointState,parse_joints),
        "arm":("/nero_guarded/feedback/arm_status","diagnostic_msgs/msg/DiagnosticArray",DiagnosticArray,parse_arm),
        "motors":("/nero_guarded/feedback/motor_status","diagnostic_msgs/msg/DiagnosticArray",DiagnosticArray,parse_motors),
    }
    pins={};latest={};counts=dict.fromkeys(specs,0);last_stamp={}
    ages=[];gaps=[];last_joint_receipt=None;failures=[];first_q=None
    sent=0;child=None;log=None
    forwarded=False
    live_samples=deque(maxlen=32)
    virtual_children=[];virtual_logs=[]
    controller_sample=None
    bootstrap=None
    profile=review_profile(c)

    joint_pub=view.create_publisher(JointState,OBSERVED,1)
    scene_pub=view.create_publisher(PlanningScene,SCENE,10)
    read_scene=view.create_client(GetPlanningScene,NS+"/get_planning_scene")
    request=GetPlanningScene.Request();request.components.components=1023

    def endpoint(key):
        topic,kind,_,_=specs[key]
        rows=reader.get_publishers_info_by_topic(topic)
        if len(rows)!=1:return None
        e=rows[0]
        if e.node_namespace.rstrip("/")+"/"+e.node_name!=NODE or e.topic_type!=kind:return None
        gid=bytes(e.endpoint_gid)
        return gid if gid and any(gid) else None

    def receive(key,msg,info):
        nonlocal first_q,sent,last_joint_receipt
        try:
            now=time.time();t=stamp(msg)
            if endpoint(key)!=pins[key]:
                raise ValueError("source changed")
            gid=info.get("publisher_gid")
            if gid is not None and bytes(gid)!=pins[key]:
                raise ValueError("sample source changed")
            parsed=specs[key][3](msg,now)
            if parsed is None:raise ValueError("invalid message")
            if t<=last_stamp.get(key,0):return
            last_stamp[key]=t
            latest[key]=parsed
            counts[key]+=1
            if key!="joints":return
            q=joint_vector(msg)
            age=now-t
            ages.append(age)
            receipt=time.monotonic()
            if last_joint_receipt is not None:gaps.append(receipt-last_joint_receipt)
            last_joint_receipt=receipt
            if not 0<=age<=AGE:raise ValueError("joint source stale")
            if first_q is None:first_q=q
            if max(abs(x-y) for x,y in zip(first_q,q))>.001:
                raise ValueError("physical pose changed during stationary review")
            if not all(lo<=x<=hi for x,(lo,hi) in zip(q,c.manifest["limits"]["jointPositionRad"])):
                raise ValueError("joint outside archived intersection")
            if len(msg.velocity)!=7 or any(not math.isfinite(x) or abs(x)>.001 for x in msg.velocity):
                raise ValueError("stationary evidence lost")
            live_samples.append((t,q))
            # Send only the real measurement and its original stamp into the
            # isolated visualization/PSM domain. No return command path.
            if forwarded:
                joint_pub.publish(deepcopy(msg));sent+=1
        except Exception as exc:
            failures.append(key+":"+str(exc))

    def spin(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rs.spin_once(timeout_sec=.003);ts.spin_once(timeout_sec=.002)
            if failures:raise RuntimeError(failures[0])
            if child is not None and child.poll() is not None:raise RuntimeError("shadow Servo exited")
            if any(proc.poll() is not None for proc in virtual_children):
                raise RuntimeError("virtual controller manager exited")

    def await_future(f,seconds=4.):
        end=time.monotonic()+seconds
        while not f.done() and time.monotonic()<end:spin(.01)
        if not f.done():raise RuntimeError("read-only service timed out")
        return f.result()
    def readback():
        return await_future(read_scene.call_async(request)).scene
    def can_stats():
        p=Path("/sys/class/net/can0/statistics")
        return {k:int((p/k).read_text()) for k in ("rx_packets","rx_dropped","rx_errors","tx_packets","tx_errors")}
    before=can_stats()
    try:
        # Discovery before any shadow process is created.
        spin(1.)
        assert set(view.get_node_names_and_namespaces())=={("review",NS)}
        # DDS discovery can complete after the initial one-second sample.
        # Wait only for the expected unique owner; never accept duplicates.
        discovery_end=time.monotonic()+3.
        while True:
            n=[ns.rstrip("/")+"/"+n for n,ns in reader.get_node_names_and_namespaces()].count(NODE)
            if n>1:raise RuntimeError("ambiguous guarded source")
            if n==1 and all(endpoint(k) is not None for k in specs):break
            if time.monotonic()>=discovery_end:raise RuntimeError("guarded source discovery incomplete")
            spin(.05)
        for key,(topic,kind,msgtype,_) in specs.items():
            pins[key]=endpoint(key)
            if pins[key] is None:raise RuntimeError("unverified feedback source "+key)
            def bind(k):
                def cb(msg,info):
                    receive(k,msg,info)
                return cb
            reader.create_subscription(msgtype,topic,bind(key),qos_profile_sensor_data)
        pc=reader.create_client(GetParameters,NODE+"/get_parameters")
        end=time.monotonic()+4.
        while not pc.service_is_ready() and time.monotonic()<end:spin(.03)
        if not pc.service_is_ready():raise RuntimeError("guard parameter readback unavailable")
        params=dict(zip(PARAMS,map(parameter_value_to_python,
                    await_future(pc.call_async(GetParameters.Request(names=list(PARAMS)))).values)))
        if params!={"control_enabled":False,"auto_enable":False,"physical_hold_enabled":True}:
            raise RuntimeError("unexpected existing guarded-owner configuration")
        spin(1.)
        if not all(counts.values()):raise RuntimeError("incomplete feedback")
        def stationary_status():
            arm,motors=latest["arm"],latest["motors"]
            if arm["errorCode"] or any(arm["angleLimit"]+arm["communicationFault"]):
                raise RuntimeError("arm reports faults")
            if any(r["enabled"] is not False or r["rawStatus"] is None or any((r["faults"] or {}).values())
                   for r in motors["rows"]):
                raise RuntimeError("review requires disabled, fault-free drives")
            if time.time()-arm["stamp"]>1. or time.time()-motors["stamp"]>1.:
                raise RuntimeError("diagnostic packet unavailable")
        stationary_status()
        print("LIVE_SOURCE_PINNED",counts,flush=True)
        if a.verify_live_jtc:
            # No persisted position is read here. Both samples have arrived
            # from the pinned live source during this invocation.
            now=time.time()
            rows=[row for row in live_samples if 0<=now-row[0]<=AGE]
            if len(rows)<2 or rows[-1][0]<=rows[-2][0]:
                raise RuntimeError("two fresh distinct joint observations required")
            first,second=rows[-2:]
            if max(abs(x-y) for x,y in zip(first[1],second[1]))>POSITION_ERROR:
                raise RuntimeError("stationary seed changed")
            q0=second[1]
            # This is ROS joint-state evidence, not the independent fresh
            # per-axis SDK evidence required for physical commissioning.
            seeded=seed_virtual_model(c.urdf,q0,profile)
            cfg_params["robot_description"]=seeded
            cfg_params.update(planning_parameters({"robot_description_planning":
                cfg_params["robot_description_planning"]},seeded,profile))
            cfg_file.write_text(yaml.safe_dump({NS+"/servo_node":{"ros__parameters":cfg_params}}))
            ctrl_file=a.output/"virtual-controllers.yaml"
            ctrl_file.write_text(yaml.safe_dump({
                NS+"/controller_manager":{"ros__parameters":{"update_rate":100,
                    "arm_controller":{"type":"joint_trajectory_controller/JointTrajectoryController"}}},
                NS+"/arm_controller":{"ros__parameters":{"joints":list(JOINTS),
                    "command_interfaces":["position"],"state_interfaces":["position","velocity"],
                    "allow_partial_joints_goal":False}}
            }))
            def controller_state(msg,info):
                nonlocal controller_sample
                try:
                    topic=NS+"/arm_controller/controller_state"
                    eps=view.get_publishers_info_by_topic(topic)
                    if len(eps)!=1 or endpoint_node(eps[0])!=NS+"/arm_controller" or eps[0].topic_type!="control_msgs/msg/JointTrajectoryControllerState":
                        controller_sample=None;return
                    gid=bytes(eps[0].endpoint_gid)
                    actual_gid=info.get("publisher_gid")
                    if not any(gid) or (actual_gid is not None and bytes(actual_gid)!=gid):
                        controller_sample=None;return
                    if set(msg.joint_names)!=set(JOINTS) or len(msg.joint_names)!=7 or msg.multi_dof_joint_names:
                        controller_sample=None;return
                    def order(v):
                        v=tuple(v)
                        if not vector7(v):raise ValueError("invalid virtual state")
                        return tuple(v[msg.joint_names.index(n)] for n in JOINTS)
                    t=stamp(msg)
                    if controller_sample is not None and t<=controller_sample[0]:return
                    controller_sample=(t,gid,order(msg.feedback.positions),
                                       order(msg.reference.positions),order(msg.feedback.velocities),
                                       order(msg.reference.velocities))
                except Exception:
                    controller_sample=None
            view.create_subscription(JointTrajectoryControllerState,
                NS+"/arm_controller/controller_state",controller_state,1)
            desc=view.create_publisher(String,NS+"/robot_description",
                QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
            manager_log=(a.output/"virtual-manager.log").open("w")
            virtual_logs.append(manager_log)
            virtual_children.append(subprocess.Popen(
                ["/opt/ros/jazzy/lib/controller_manager/ros2_control_node",
                 "--ros-args","-r","__ns:="+NS,"--params-file",str(ctrl_file),
                 "-r","~/robot_description:="+NS+"/robot_description"],
                stdout=manager_log,stderr=subprocess.STDOUT,env=env))
            desc.publish(String(data=seeded))
            spawn_log=(a.output/"virtual-spawner.log").open("w")
            virtual_logs.append(spawn_log)
            spawner=subprocess.Popen(
                ["/opt/ros/jazzy/lib/controller_manager/spawner","arm_controller",
                 "-c",NS+"/controller_manager","--controller-manager-timeout","10",
                 "--param-file",str(ctrl_file)],stdout=spawn_log,stderr=subprocess.STDOUT,env=env)
            try:
                end=time.monotonic()+15.
                while spawner.poll() is None and time.monotonic()<end:spin(.03)
                if spawner.poll()!=0:raise RuntimeError("virtual JTC did not activate")
            finally:
                if spawner.poll() is None:
                    spawner.terminate();spawner.wait(timeout=3)
            lc=view.create_client(ListControllers,NS+"/controller_manager/list_controllers")
            lh=view.create_client(ListHardwareComponents,NS+"/controller_manager/list_hardware_components")
            end=time.monotonic()+3.
            while not(lc.service_is_ready() and lh.service_is_ready()) and time.monotonic()<end:spin(.03)
            assert lc.service_is_ready() and lh.service_is_ready()
            ctrl=await_future(lc.call_async(ListControllers.Request()))
            hw=await_future(lh.call_async(ListHardwareComponents.Request()))
            assert controller_evidence(ctrl,hw)==(True,True)
            def verify_virtual_start():
                if controller_sample is None:raise RuntimeError("virtual JTC readback missing")
                t,gid,q,r,v,rv=controller_sample
                now=time.time()
                latest_stamp=latest["joints"]["stamp"]
                actual=tuple(x["positionRad"] for x in latest["joints"]["rows"])
                if not 0<=now-t<=CONTROLLER_AGE or not 0<=now-latest_stamp<=AGE:
                    raise RuntimeError("virtual or measured position stale")
                if max(abs(x) for x in (*v,*rv))>.001:
                    raise RuntimeError("unexpected virtual movement")
                error=max(abs(x-y) for row in (q,r) for x,y in zip(row,actual))
                if error>POSITION_ERROR:raise RuntimeError("live JTC seed mismatch")
                # There is no publisher for trajectory or action goals.
                if view.count_publishers(NS+"/arm_controller/joint_trajectory")!=0:
                    raise RuntimeError("unexpected virtual JTC command source")
                return error
            spin(.3)
            bootstrap={"status":"LIVE_VIRTUAL_JTC_START_VERIFIED","source":"LIVE_ROS_JOINT_STATE",
                       "sourceStamps":[first[0],second[0]],"jointRad":q0,
                       "initialStateMaxErrorRad":verify_virtual_start(),
                       "virtualControllerOnly":True,"physicalExecutionAllowed":False}
            print("LIVE_VIRTUAL_JTC_INITIALIZED",bootstrap["initialStateMaxErrorRad"],flush=True)
        log=(a.output/"servo.log").open("w")
        child=subprocess.Popen([str(a.servo_prefix/"lib/moveit_servo/servo_node"),
                 "--ros-args","-r","__ns:="+NS,"-r","__node:=servo_node","--params-file",str(cfg_file)],
                 stdout=log,stderr=subprocess.STDOUT,env=env)
        forwarded=True
        end=time.monotonic()+15.
        while (not read_scene.service_is_ready() or scene_pub.get_subscription_count()!=1) and time.monotonic()<end:
            spin(.03)
        assert read_scene.service_is_ready() and scene_pub.get_subscription_count()==1
        spin(.5)
        old=readback()
        assert not old.world.collision_objects and not old.robot_state.attached_collision_objects
        scene_pub.publish(scene)
        spin(.5)
        digests=[];residuals=[]
        for _ in range(5):
            actual=readback()
            ObservationFixture.verify_station_geometry(scene,actual)
            assert actual.allowed_collision_matrix==old.allowed_collision_matrix
            q=joint_vector(actual.robot_state.joint_state)
            ref=tuple(r["positionRad"] for r in latest["joints"]["rows"])
            residuals.append(max(abs(x-y) for x,y in zip(q,ref)))
            assert residuals[-1]<=1e-6
            digests.append(scene_fingerprint(actual))
            stationary_status()
            assert view.count_publishers(NS+"/unused_twist")==0
            assert view.count_subscribers(NS+"/unused_trajectory")==0
            if a.verify_live_jtc:
                bootstrap["lastStateMaxErrorRad"]=verify_virtual_start()
            else:
                assert not any("controller_manager" in n for n,_ in view.get_node_names_and_namespaces())
            spin(.15)
        assert len(set(digests))==1
        assert sent>20 and all(endpoint(k)==v for k,v in pins.items())
        after=can_stats()
        deltas={k:after[k]-before[k] for k in before}
        if deltas["tx_packets"] or deltas["tx_errors"] or deltas["rx_errors"]:
            raise RuntimeError("CAN counter changes incompatible with read-only review")
        if not gaps or max(gaps)>AGE:raise RuntimeError("joint receipt gap exceeded")
        receipt={
            "status":"LIVE_STATION_SHADOW_READBACK_PASS",
            "physicalExecutionAllowed":False,"stationAcceptance":False,
            "sourceDomain":DOMAIN,"shadowDomain":SHADOW,
            "sourceTopic":SOURCE_JOINT,"observedTopic":OBSERVED,"sourceGids":{k:v.hex() for k,v in pins.items()},
            "sourceStamp":latest["joints"]["stamp"],"jointRad":ref,
            "sourceSamples":counts,"forwardedSamples":sent,
            "maxJointAgeMs":1000*max(ages),"maxReceiptGapMs":1000*max(gaps),
            "maxPsmPositionDifferenceRad":max(residuals),"sceneDigest":digests[0],
            "candidateManifestSha256":hashlib.sha256((a.candidate/"manifest.json").read_bytes()).hexdigest(),
            "guardParameters":params,"arm":latest["arm"],"motors":latest["motors"],
            "canCounterDelta":deltas,"noMotionPath":True,
            "timestampEvidence":"live joint source only; PSM service response has no source timestamp",
            "limits":"historical intersection; not fresh firmware query",
        }
        if bootstrap is not None:
            receipt["virtualJtcBootstrap"]=bootstrap
        (a.output/"result.json").write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n")
        print(json.dumps({k:v for k,v in receipt.items() if k not in ("arm","motors","sourceGids")},indent=2),flush=True)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
        if log is not None:log.close()
        for proc in reversed(virtual_children):
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        for out in virtual_logs:out.close()
        rs.remove_node(reader);ts.remove_node(view)
        rs.shutdown();ts.shutdown();reader.destroy_node();view.destroy_node()
        rclpy.try_shutdown(context=source);rclpy.try_shutdown(context=target)

if __name__=="__main__":
    main()
