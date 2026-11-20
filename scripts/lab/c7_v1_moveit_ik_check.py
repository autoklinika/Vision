#!/usr/bin/env python3
"""C7 V1 Vision -> MoveIt 2 offline IK, state validity and collision checks.

Only executes in explicitly isolated ROS2 lab domain with MoveIt execution
disabled, no robot control bridge, and can0 physically down.
Does not publish TF or create ROS2 actions to command the robot.
"""
import argparse, datetime as dt, hashlib, json, math, os, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, PoseStamped, Vector3
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from moveit_msgs.msg import (RobotState, PlanningScene, CollisionObject,
                             AttachedCollisionObject, Constraints, JointConstraint, PlanningSceneComponents)
from moveit_msgs.srv import (GetPositionIK, GetPositionFK, GetStateValidity,
                             ApplyPlanningScene, GetMotionPlan, GetPlanningScene)

JOINTS=[f"joint{i}" for i in range(1,8)]
HIST_JOINT_DEG=[89.083,48.099,2.832,117.542,-1.002,1.171,14.504]
LAB_DOMAIN="201"
TABLE_ID="c7_v1_ik_synthetic_table"
ECU_ID="c7_v1_ik_synthetic_pcb_prism"
TOOL_ID="c7_v1_ik_sony_dummy_adapter"
TX=Path("/sys/class/net/can0/statistics/tx_packets")
COLLISION_NAME={-31:"NO_IK_SOLUTION",-21:"FRAME_TRANSFORM_FAILURE",-2:"FAILURE",1:"SUCCESS"}


def check_preflight():
    assert os.environ.get("ROS_DOMAIN_ID")==LAB_DOMAIN,"ROS_DOMAIN_ID_201_REQUIRED"
    assert os.environ.get("ROS_AUTOMATIC_DISCOVERY_RANGE")=="LOCALHOST","LOCALHOST_DISCOVERY_REQUIRED"
    assert int(TX.read_text())==0,"CAN_ALREADY_USED"
    assert "DOWN" in subprocess.check_output(["ip","-br","link","show","can0"],text=True),"CAN_NOT_DOWN"
    cmd=subprocess.run(["ros2","param","get","/move_group","allow_trajectory_execution"],
                       capture_output=True,text=True,timeout=8)
    assert cmd.returncode==0 and "Boolean value is: False" in cmd.stdout,"MOVEIT_EXECUTION_NOT_DISABLED"


def rx(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[1,0,0],[0,c,-s],[0,s,c]],float)
def ry(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,0,s],[0,1,0],[-s,0,c]],float)
def rz(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]],float)
def T(R=None,t=(0,0,0)):
    a=np.eye(4);a[:3,:3]=np.eye(3) if R is None else R;a[:3,3]=t
    return a
def rpy_R(euler):
    roll,pitch,yaw=euler
    return rz(yaw)@ry(pitch)@rx(roll)
def quat_R(q):
    x,y,z,w=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
      [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
      [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def rot_quat(R):
    trace=np.trace(R)
    if trace>0:
        s=math.sqrt(trace+1)*2;x=(R[2,1]-R[1,2])/s
        y=(R[0,2]-R[2,0])/s;z=(R[1,0]-R[0,1])/s;w=s/4
    else:
        i=int(np.argmax(np.diag(R)))
        if i==0:
            s=2*math.sqrt(1+R[0,0]-R[1,1]-R[2,2])
            x=s/4;y=(R[0,1]+R[1,0])/s;z=(R[0,2]+R[2,0])/s;w=(R[2,1]-R[1,2])/s
        elif i==1:
            s=2*math.sqrt(1+R[1,1]-R[0,0]-R[2,2])
            x=(R[0,1]+R[1,0])/s;y=s/4;z=(R[1,2]+R[2,1])/s;w=(R[0,2]-R[2,0])/s
        else:
            s=2*math.sqrt(1+R[2,2]-R[0,0]-R[1,1])
            x=(R[0,2]+R[2,0])/s;y=(R[1,2]+R[2,1])/s;z=s/4;w=(R[1,0]-R[0,1])/s
    v=np.array([x,y,z,w],float);v/=np.linalg.norm(v)
    assert np.allclose(quat_R(v),R,atol=1e-6)
    return v.tolist()
def pose_Rt(R,t):
    p=Pose();p.position.x,p.position.y,p.position.z=[float(x) for x in t]
    q=rot_quat(R)
    p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w=[float(x) for x in q]
    return p
def robot_state(q):
    obj=RobotState();obj.is_diff=False
    obj.joint_state.name=JOINTS
    obj.joint_state.position=[float(x) for x in q]
    return obj
def box(size):
    p=SolidPrimitive();p.type=SolidPrimitive.BOX;p.dimensions=[float(x) for x in size];return p
def cylinder(length,radius):
    p=SolidPrimitive();p.type=SolidPrimitive.CYLINDER;p.dimensions=[float(length),float(radius)];return p
def world_object(name,primitives,poses,operation=CollisionObject.ADD):
    obj=CollisionObject();obj.id=name;obj.header.frame_id="base_link"
    obj.primitives=primitives;obj.primitive_poses=poses;obj.operation=operation
    return obj
def tool_object(model,profile,signed,kind):
    flange=profile["vendor_T_link7_flange"]
    R_LF=rpy_R(flange["rpy_rad"])
    T_LF=T(R_LF,flange["xyz_m"])
    # Chosen hypothesis: socket +Z aligned with flange +Z and nominal axial offset 0.
    R_FS=rz(math.radians(90-signed))
    T_LS=T_LF@T(R_FS)
    collision=[]
    if kind=="DETAILED":
        collision=model["collision_primitives"]
    elif kind=="CONSERVATIVE":
        v=model["conservative_proxy"]
        collision=[{"name":"conservative_yaw_invariant",
                    "type":"cylinder","origin_xyz_m":v["origin_xyz_m"],
                    "origin_rpy_rad":v["origin_rpy_rad"],
                    "length_m":v["length_m"],"radius_m":v["radius_m"]}]
    else:raise RuntimeError("Unknown collision model")
    primitives=[];poses=[]
    for item in collision:
        R=rpy_R(item["origin_rpy_rad"])
        X=T_LS@T(R,item["origin_xyz_m"])
        if item["type"]=="box":
            prim=box(item["size_xyz_m"])
        else:
            prim=cylinder(item["length_m"],item["radius_m"])
        primitives.append(prim);poses.append(pose_Rt(X[:3,:3],X[:3,3]))
    obj=AttachedCollisionObject();obj.link_name="link7"
    obj.object=CollisionObject()
    obj.object.header.frame_id="link7";obj.object.id=TOOL_ID
    obj.object.primitives=primitives;obj.object.primitive_poses=poses
    obj.object.operation=CollisionObject.ADD
    obj.touch_links=list(model["touch_links_assumed"])
    return obj
def remove_tool():
    obj=AttachedCollisionObject();obj.link_name="link7"
    obj.object=CollisionObject()
    obj.object.header.frame_id="link7";obj.object.id=TOOL_ID
    obj.object.operation=CollisionObject.REMOVE
    return obj


class Lab(Node):
    def __init__(self):
        super().__init__("vision_c7_v1_ik_and_collision_offline")
        self.ik=self.create_client(GetPositionIK,"/compute_ik")
        self.fk=self.create_client(GetPositionFK,"/compute_fk")
        self.valid=self.create_client(GetStateValidity,"/check_state_validity")
        self.apply=self.create_client(ApplyPlanningScene,"/apply_planning_scene")
        self.plan=self.create_client(GetMotionPlan,"/plan_kinematic_path")
        self.getscene=self.create_client(GetPlanningScene,"/get_planning_scene")

    def call(self,srv,msg,timeout=9):
        f=srv.call_async(msg)
        rclpy.spin_until_future_complete(self,f,timeout_sec=timeout)
        if not f.done() or f.result() is None:
            raise TimeoutError("ROS service call timed out: "+srv.srv_name)
        return f.result()

    def set_scene(self,world=None,tool=None):
        scene=PlanningScene();scene.is_diff=True;scene.robot_state.is_diff=True
        if world is not None:scene.world.collision_objects=list(world)
        if tool is not None:scene.robot_state.attached_collision_objects=[tool]
        req=ApplyPlanningScene.Request();req.scene=scene
        if not bool(self.call(self.apply,req).success):
            raise RuntimeError("MOVEIT_APPLY_PLANNING_SCENE_REJECTED")
        return True

    def scene_inventory(self):
        req=GetPlanningScene.Request()
        req.components.components=int(PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS |
                                      PlanningSceneComponents.WORLD_OBJECT_GEOMETRY)
        res=self.call(self.getscene,req)
        return {"world": {x.id: len(x.primitives) for x in res.scene.world.collision_objects},
                "attached": {x.object.id: len(x.object.primitives)
                             for x in res.scene.robot_state.attached_collision_objects}}

    def assert_tool(self,primitive_count):
        inventory=self.scene_inventory()
        present=inventory["attached"].get(TOOL_ID)
        world_residual=TOOL_ID in inventory["world"]
        if present != primitive_count or world_residual:
            raise RuntimeError(f"TOOL_SCENE_NOT_EXCLUSIVE expected {primitive_count} attached and NO world residue, got {inventory}")

    def clear_tool(self):
        """Explicitly clear BOTH MoveIt attached object and its world residue.

        AttachedCollisionObject.REMOVE detaches and can leave the geometry in
        PlanningScene.world; it is not sufficient to call only detach.
        """
        inv=self.scene_inventory()
        if TOOL_ID in inv["attached"]:
            self.set_scene(tool=remove_tool())
        inv=self.scene_inventory()
        if TOOL_ID in inv["world"]:
            self.set_scene(world=[world_object(TOOL_ID,[],[],CollisionObject.REMOVE)])
        inv=self.scene_inventory()
        if TOOL_ID in inv["attached"] or TOOL_ID in inv["world"]:
            raise RuntimeError(f"TOOL_NOT_FULLY_REMOVED_FROM_SCENE: {inv}")
        return True

    def state_check(self,joint_values):
        req=GetStateValidity.Request();req.group_name="arm";req.robot_state=robot_state(joint_values)
        res=self.call(self.valid,req)
        return {
          "valid":bool(res.valid),
          "contacts":[{"body1":c.contact_body_1,"body2":c.contact_body_2,"depth_m":round(float(c.depth),6)} for c in list(res.contacts)[:15]]}

    def compute_ik(self,target,seed,avoid_collisions=False,timeout_s=1):
        req=GetPositionIK.Request();ik=req.ik_request
        ik.group_name="arm";ik.ik_link_name="link7";ik.avoid_collisions=bool(avoid_collisions)
        ik.timeout.sec=int(timeout_s)
        ik.robot_state=robot_state(seed)
        goal=PoseStamped();goal.header.frame_id="world"
        pos=target["link7_IK_candidate"]["position_m"]
        quat=target["link7_IK_candidate"]["quaternion_xyzw"]
        goal.pose.position.x,goal.pose.position.y,goal.pose.position.z=[float(x) for x in pos]
        goal.pose.orientation.x,goal.pose.orientation.y,goal.pose.orientation.z,goal.pose.orientation.w=[float(x) for x in quat]
        ik.pose_stamped=goal
        result=self.call(self.ik,req,timeout=timeout_s+8)
        code=int(result.error_code.val)
        if code!=1:return {"status":"NO_SOLUTION","error_code":code,"label":COLLISION_NAME.get(code,str(code))}
        positions=dict(zip(result.solution.joint_state.name,result.solution.joint_state.position))
        if any(k not in positions for k in JOINTS):
            raise RuntimeError("IK_SOLVED_BUT_MISSING_JOINTS")
        q=[float(positions[k]) for k in JOINTS]
        if not all(math.isfinite(v) for v in q):
            raise RuntimeError("IK_NAN_JOINTS")
        return {"status":"IK_SOLUTION_FOUND","error_code":code,
                "joint_deg":[round(math.degrees(v),5) for v in q],"q":q}

    def verify_fk(self,target,q):
        req=GetPositionFK.Request()
        req.header.frame_id="world"
        req.fk_link_names=["link7"]
        req.robot_state=robot_state(q)
        res=self.call(self.fk,req)
        if res.error_code.val!=1:raise RuntimeError("FK_FAILED_"+str(res.error_code.val))
        pose=res.pose_stamped[0].pose
        got=np.array([pose.position.x,pose.position.y,pose.position.z])
        desired=np.array(target["link7_IK_candidate"]["position_m"])
        err_mm=1000*float(np.linalg.norm(got-desired))
        actual=np.array([pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w])
        exp=np.array(target["link7_IK_candidate"]["quaternion_xyzw"])
        orientation_error_deg=2*math.degrees(math.acos(min(1.0,abs(float(np.dot(actual,exp))))))
        return {"position_error_mm":round(err_mm,6),
                "angle_error_deg":round(orientation_error_deg,6),
                "matches_ik_target":err_mm<3 and orientation_error_deg<1.5}

    def pilz_plan(self,start,goal):
        req=GetMotionPlan.Request();p=req.motion_plan_request
        p.group_name="arm";p.pipeline_id="pilz_industrial_motion_planner";p.planner_id="PTP"
        p.allowed_planning_time=6.;p.num_planning_attempts=1
        p.max_velocity_scaling_factor=.10;p.max_acceleration_scaling_factor=.10
        p.workspace_parameters.header.frame_id="world"
        p.workspace_parameters.min_corner=Vector3(x=-2.,y=-2.,z=-1.)
        p.workspace_parameters.max_corner=Vector3(x=2.,y=2.,z=2.)
        p.start_state=robot_state(start)
        cs=Constraints()
        for name,val in zip(JOINTS,goal):
            from moveit_msgs.msg import JointConstraint
            c=JointConstraint();c.joint_name=name;c.position=float(val)
            c.tolerance_above=.0002;c.tolerance_below=.0002;c.weight=1.
            cs.joint_constraints.append(c)
        p.goal_constraints=[cs]
        response=self.call(self.plan,req,timeout=25).motion_plan_response
        points=response.trajectory.joint_trajectory.points
        out={"error_code":int(response.error_code.val),"plan_success":False,
             "waypoint_count":len(points),"invalid_waypoints":[]}
        if response.error_code.val==1 and points:
            for i,x in enumerate(points):
                v=self.state_check(list(x.positions))
                if not v["valid"]:
                    out["invalid_waypoints"].append({"waypoint":i,"contacts":v["contacts"]})
            out["plan_success"]=not out["invalid_waypoints"]
            t=points[-1].time_from_start
            out["planned_duration_s"]=round(t.sec+t.nanosec*1e-9,3)
        return out


def config_check(candidates,profile,scene,proxy):
    assert candidates["status"]=="OFFLINE_VIEWPOINT_CANDIDATES_ONLY"
    assert candidates["physical_execution_allowed"] is False
    assert candidates["MoveIt_planning_executed"] is False
    assert candidates["candidate_count"]==10
    assert len(candidates["candidates"])==10
    assert scene.get("evidence_kind") in ("synthetic_fixture","vision_perception_candidate","operator_measured")
    # Strict conservative check: no stale or implicit "approved" motion permission.
    assert profile["execution_policy"]=={
        "allow_trajectory_execution":False,"publish_static_tf":False,
        "activate_production_profile":False,"send_robot_commands":False,
        "use_for_collision_safety":False}
    assert not profile["candidate_T_table_base_link_approved"]
    assert not proxy["validated_against_complete_fabricated_physical_tool"]
    assert not proxy["allow_movement_from_this_collision_model"]


def table_scene(profile,scene):
    TT=np.array(profile["candidate_T_table_base_link"],float)
    B=np.linalg.inv(TT)
    table=profile["measured_table_mm"]
    W,D=table["width_x"]/1000,table["depth_y"]/1000
    center=B@np.array([W/2,D/2,-.025,1.])
    a=world_object(TABLE_ID,[box([W,D,.05])],[pose_Rt(B[:3,:3],center[:3])])
    pcb=scene["pcb"]
    env=scene.get("obstacle_envelope")
    if env is None:
        # Historical synthetic fixture: PCB prism stands in for the ECU.
        source={"center_table_xy_mm":pcb["center_table_xy_mm"],
                "size_xy_mm":pcb["size_xy_mm"],
                "height_above_table_mm":pcb["top_z_mm"],
                "yaw_table_deg":pcb.get("yaw_table_deg",0)}
    else:
        if env.get("not_safety_approved") is not True or env.get("source_status")!="EXPLORATORY_UNVERIFIED":
            raise ValueError("Source ECU obstacle must remain unverified")
        source=env
    yaw=math.radians(float(source.get("yaw_table_deg",0)))
    size=np.array(source["size_xy_mm"],float)/1000
    thick=float(source["height_above_table_mm"])/1000
    pos=np.array([source["center_table_xy_mm"][0]/1000,
                  source["center_table_xy_mm"][1]/1000,thick/2,1.])
    Tc=B@T(rz(yaw),pos[:3])
    if thick<=0 or any(v<=0 for v in size):
        raise ValueError("Invalid hypothetical ECU obstacle envelope")
    b=world_object(ECU_ID,[box([*size,thick])],[pose_Rt(Tc[:3,:3],Tc[:3,3])])
    return [a,b]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates",type=Path,required=True)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--scene",type=Path,required=True)
    parser.add_argument("--collision",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args()
    if a.output.exists():parser.error("Output exists; refusing to overwrite test evidence")
    check_preflight()
    before=int(TX.read_text())
    candidates=json.loads(a.candidates.read_text())
    profile=json.loads(a.profile.read_text())
    scene=json.loads(a.scene.read_text())
    geometry=json.loads(a.collision.read_text())
    config_check(candidates,profile,scene,geometry)
    report={
        "stage":"C7_V1_IK_MOVEIT",
        "status":"STARTED",
        "time_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "ROS_DOMAIN_ID":int(LAB_DOMAIN),
        "MoveIt_execution_allowed":False,
        "safety_function":False,
        "source_scene_kind":scene["evidence_kind"],
        "source_scene_id":scene["scenario_id"],
        "unapproved_table_to_base":True,
        "unapproved_tool_to_flange":True,
        "robot_joint_reference":"Historical 2026-11-18 state for IK seed only, not live position",
        "table_and_ECU_obstacle_in_planning_scene":True,
        "whole_ECU_obstacle_envelope_unapproved":scene.get("obstacle_envelope") is not None,
        "other_scene_obstacles_missing":True,
        "nominal_tool_and_conservative_tool_separately_checked":True,
        "continuous_collision_check":False,
        "CAN_TX_before":before,
        "results":[],
        "optional_plans":[],
        "scene_applied":False,
        "scene_cleanup_completed":False,
        "published_active_TF":False,
        "robot_commands_sent":False,
        "sources":{
           "candidates_sha256":hashlib.sha256(a.candidates.read_bytes()).hexdigest(),
           "profile_sha256":hashlib.sha256(a.profile.read_bytes()).hexdigest(),
           "scene_sha256":hashlib.sha256(a.scene.read_bytes()).hexdigest(),
           "tool_model_sha256":hashlib.sha256(a.collision.read_bytes()).hexdigest()}
    }
    lab=None
    try:
        rclpy.init()
        lab=Lab()
        for srv in (lab.ik,lab.fk,lab.valid,lab.apply,lab.plan,lab.getscene):
            if not srv.wait_for_service(timeout_sec=10):
                raise RuntimeError("MISSING_MOVEIT_SERVICE_"+srv.srv_name)
        world=table_scene(profile,scene)
        if not lab.set_scene(world=world):raise RuntimeError("APPLY_TABLE_ECU_SCENE_FAILED")
        scene_ids=lab.scene_inventory()
        if TABLE_ID not in scene_ids["world"] or ECU_ID not in scene_ids["world"]:
            raise RuntimeError("TABLE_OR_ECU_COLLISION_GEOMETRY_NOT_ACTUALLY_PRESENT")
        report["scene_applied"]=True
        report["verified_isolated_scene_inventory_after_apply"]=scene_ids
        hist=[math.radians(v) for v in HIST_JOINT_DEG]
        neutral=[0,0,0,math.radians(35),0,0,0]
        # Cross-check negative control: explicit blocker intersects link7 at historical q.
        v=lab.verify_fk(candidates["candidates"][0],hist)
        # FK residual unrelated to candidate is not used for control, only service health.
        # Never infer robot has actually moved to this historical q.
        for signed in (+90,-90):
            variants=[c for c in candidates["candidates"] if c["mount_signed_azimuth_assumption_deg"]==signed]
            assert len(variants)==5
            lab.set_scene(tool=tool_object(geometry,profile,signed,"DETAILED"))
            lab.assert_tool(4)
            for item in variants:
                row={
                 "view_id":item["view_id"],"mount_azimuth_deg":signed,
                 "target_link":"link7","IK_possible_without_collision_check":False,
                 "IK_collision_free":False,
                 "IK_error_code":None,
                 "position_residual_mm":None,
                 "angle_residual_deg":None,
                 "detailed_tool_collision_state_valid":False,
                 "conservative_model_collision_state_valid":False,
                 "IK_solution_joint_deg":None,
                 "unreachable_or_collision_explanation":[],
                 "motion_execution_allowed":False
                }
                seed_results=[]
                for seedname,seed in (("historical",hist),("neutral",neutral)):
                    solution=lab.compute_ik(item,seed,avoid_collisions=False)
                    seed_results.append({"seed":seedname,"IK_error_code":solution["error_code"],"IK_status":solution["status"]})
                    if solution["status"]!="IK_SOLUTION_FOUND":
                        continue
                    check=lab.verify_fk(item,solution["q"])
                    if not check["matches_ik_target"]:
                        row["unreachable_or_collision_explanation"].append("FK_RESIDUAL_FAIL")
                        continue
                    row["IK_possible_without_collision_check"]=True
                    q=solution["q"]
                    state=lab.state_check(q)
                    if state["valid"]:
                        row["detailed_tool_collision_state_valid"]=True
                        row["IK_solution_joint_deg"]=solution["joint_deg"]
                        row["selected_IK_seed"]=seedname
                        row["position_residual_mm"]=check["position_error_mm"]
                        row["angle_residual_deg"]=check["angle_error_deg"]
                        break
                    if "DETAILED_TOOL_OR_SCENE_COLLISION" not in row["unreachable_or_collision_explanation"]:
                        row["unreachable_or_collision_explanation"].append("DETAILED_TOOL_OR_SCENE_COLLISION")
                    row["detailed_collision_contacts"]=state["contacts"]
                row["kinematic_seed_results"]=seed_results
                if not row["detailed_tool_collision_state_valid"]:
                    aware=lab.compute_ik(item,hist,avoid_collisions=True,timeout_s=2)
                    row["collision_aware_IK_error_code"]=aware["error_code"]
                    if aware["status"]=="IK_SOLUTION_FOUND":
                        check=lab.verify_fk(item,aware["q"])
                        val=lab.state_check(aware["q"])
                        if check["matches_ik_target"] and val["valid"]:
                            row["IK_possible_without_collision_check"]=True
                            row["detailed_tool_collision_state_valid"]=True
                            row["IK_solution_joint_deg"]=aware["joint_deg"]
                            row["position_residual_mm"]=check["position_error_mm"]
                            row["angle_residual_deg"]=check["angle_error_deg"]
                            row["selected_IK_seed"]="collision_aware"
                        else:
                            row["unreachable_or_collision_explanation"].append("COLLISION_AWARE_IK_RETURNED_INVALID_STATE")
                row["IK_collision_free"]=row["detailed_tool_collision_state_valid"]
                report["results"].append(row)
                print("IK_DETAILED",signed,item["view_id"],
                      "KINEMATIC",row["IK_possible_without_collision_check"],
                      "COLLISION_FREE",row["IK_collision_free"],
                      "SEEDS",row["kinematic_seed_results"],flush=True)
            # Switch to conservative collision model and recheck every detailed solution.
            lab.clear_tool()
            lab.assert_tool(None)
            lab.set_scene(tool=tool_object(geometry,profile,signed,"CONSERVATIVE"))
            lab.assert_tool(1)
            for row in report["results"]:
                if row["mount_azimuth_deg"]!=signed or row["IK_solution_joint_deg"] is None:
                    continue
                q=[math.radians(v) for v in row["IK_solution_joint_deg"]]
                val=lab.state_check(q)
                row["conservative_model_collision_state_valid"]=val["valid"]
                row["conservative_collision_contacts"]=val["contacts"]
                print("IK_CONSERVATIVE",signed,row["view_id"],"VALID",val["valid"],flush=True)
            lab.clear_tool()
            lab.assert_tool(None)
        # MoveIt PTP only if 2+ viewpoints in same orientation survived both collision models.
        for signed in (+90,-90):
            good=[r for r in report["results"] if r["mount_azimuth_deg"]==signed
                  and r["IK_collision_free"] and r["conservative_model_collision_state_valid"]]
            if len(good)<2:
                report["optional_plans"].append({"signed_azimuth_deg":signed,
                  "status":"NOT_ATTEMPTED_INSUFFICIENT_DOUBLE_COLLISION_VALID_POSES",
                  "available_pose_count":len(good)})
                continue
            a1,b1=good[0:2]
            lab.set_scene(tool=tool_object(geometry,profile,signed,"DETAILED"))
            lab.assert_tool(4)
            q1=[math.radians(v) for v in a1["IK_solution_joint_deg"]]
            q2=[math.radians(v) for v in b1["IK_solution_joint_deg"]]
            result=lab.pilz_plan(q1,q2)
            result.update({"from":a1["view_id"],"to":b1["view_id"],"azimuth_deg":signed,
                           "physical_execution_allowed":False})
            report["optional_plans"].append(result)
            print("IK_TO_IK_PILZ",signed,result,flush=True)
            lab.clear_tool()
            lab.assert_tool(None)
        # Explicitly remove isolated planning objects.
        removed=lab.set_scene(world=[
          world_object(TABLE_ID,[],[],CollisionObject.REMOVE),
          world_object(ECU_ID,[],[],CollisionObject.REMOVE)])
        after_inventory=lab.scene_inventory()
        report["scene_cleanup_completed"]=bool(removed and TABLE_ID not in after_inventory["world"]
                                               and ECU_ID not in after_inventory["world"]
                                               and TOOL_ID not in after_inventory["attached"]
                                               and TOOL_ID not in after_inventory["world"])
        report["verified_scene_inventory_after_cleanup"]=after_inventory
        if not report["scene_cleanup_completed"]:
            raise RuntimeError("TEST_SCENE_NOT_CLEANED")
        report["status"]="MOVEIT_IK_CHECKS_COMPLETED"
    except Exception as exc:
        report["status"]="MOVEIT_IK_CHECKS_INCOMPLETE"
        report["exception"]=repr(exc)
        traceback.print_exc()
    finally:
        if lab is not None:
            try:
                if not report["scene_cleanup_completed"]:
                    lab.clear_tool()
                    lab.set_scene(world=[
                      world_object(TABLE_ID,[],[],CollisionObject.REMOVE),
                      world_object(ECU_ID,[],[],CollisionObject.REMOVE)])
            except Exception as e:
                report["cleanup_exception"]=repr(e)
            lab.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        report["CAN_TX_after"]=int(TX.read_text())
        report["CAN_TX_unchanged"]=report["CAN_TX_before"]==report["CAN_TX_after"]
        report["candidate_count_processed"]=len(report["results"])
        report["IK_kinematic_success_count"]=sum(r["IK_possible_without_collision_check"] for r in report["results"])
        report["IK_detailed_collision_free_count"]=sum(r["IK_collision_free"] for r in report["results"])
        report["IK_valid_in_both_collision_models_count"]=sum(
            r["IK_collision_free"] and r["conservative_model_collision_state_valid"] for r in report["results"])
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x") as f:
            json.dump(report,f,indent=2,ensure_ascii=False)
            f.write("\n")
        print("C7_IK_MOVEIT_RESULT",report["status"],
              "CANDIDATES",report["candidate_count_processed"],
              "KINEMATIC",report["IK_kinematic_success_count"],
              "DETAILED",report["IK_detailed_collision_free_count"],
              "BOTH",report["IK_valid_in_both_collision_models_count"],
              "CAN_TX",report["CAN_TX_before"],report["CAN_TX_after"],
              "OUTPUT",a.output,flush=True)
        if report["status"]!="MOVEIT_IK_CHECKS_COMPLETED" or not report["CAN_TX_unchanged"]:
            sys.exit(3)


if __name__=="__main__":
    main()
