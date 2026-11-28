"""One configuration for the Servo interpolator and the guarded owner.

The laboratory review builder never approves a station, contacts hardware,
starts a runtime or grants an enable token. A physical owner factory needs
separately accepted commissioning inputs; the fixture is not such evidence.
"""
from copy import deepcopy
from dataclasses import dataclass, replace
import math
import xml.etree.ElementTree as ET

from .nero_manual import JOINTS, Profile, finite
from .nero_manual_station import Candidate, STATUS, xml_root, only
from .nero_joint_limits import model_bounds
from .nero_manual_pipeline import Contract, Routes


def review_profile(candidate):
    """Provisional Precision envelope for the offline station fixture."""
    if (not isinstance(candidate, Candidate)
            or candidate.manifest.get("status") != STATUS
            or candidate.manifest.get("physicalExecutionAllowed") is not False):
        raise ValueError("review-only candidate required")
    limits = candidate.manifest["limits"]
    position = tuple(tuple(row) for row in limits["jointPositionRad"])
    speed = limits["controllerMaxVelocityRadS"]
    if len(speed)!=7 or any(not finite(v) or v<.02 for v in speed):
        raise ValueError("recorded firmware limits do not support review cap")
    return Profile(5,2,position,(.02,)*7,.005)


def verify_tcp(model_urdf, model_srdf):
    root,semantic = xml_root(model_urdf.encode()),xml_root(model_srdf.encode())
    tcp=only(root,'joint[@name="tcp_joint"]')
    if (tcp.get("type")!="fixed" or only(tcp,"parent").get("link")!="flange_link"
            or only(tcp,"child").get("link")!="tcp_link"
            or list(only(root,'link[@name="tcp_link"]'))):
        raise ValueError("mechanical mount-face TCP required")
    origin=only(tcp,"origin")
    xyz=tuple(map(float,origin.get("xyz","").split()))
    rpy=tuple(map(float,origin.get("rpy","").split()))
    if (len(xyz)!=3 or xyz[:2]!=(0.,0.) or not 0<xyz[2]<=.1
            or rpy!=(0.,0.,0.)):
        raise ValueError("explicit mechanical TCP transform required")
    if only(semantic,'group[@name="arm"]/chain').attrib!={"base_link":"base_link","tip_link":"tcp_link"}:
        raise ValueError("MoveIt arm group must end at selected TCP")
    return xyz


def servo_parameters(routes, profile):
    """One explicit inventory; collision thresholds unchanged from V1."""
    if not isinstance(routes,Routes) or not isinstance(profile,Profile):
        raise ValueError("typed routes and profile required")
    return {
        "move_group_name":"arm","command_in_type":"speed_units",
        "scale":{"linear":profile.linear_max/1000.,
                 "rotational":math.radians(profile.angular_max),"joint":.2},
        "publish_period":.02,"incoming_command_timeout":.15,
        "use_smoothing":False,"check_collisions":True,"check_octomap_collisions":False,
        "is_primary_planning_scene_monitor":True,
        "monitored_planning_scene_topic":routes.namespace+"/scene_input",
        "cartesian_command_in_topic":routes.twist,
        "pose_command_in_topic":routes.namespace+"/unused_pose_target",
        "joint_command_in_topic":routes.namespace+"/unused_joint_jog",
        "joint_topic":routes.feedback_topic,"command_out_topic":routes.trajectory,
        "status_topic":routes.status,
        "publish_joint_positions":True,"publish_joint_velocities":True,
        "publish_joint_accelerations":False,"command_out_type":"trajectory_msgs/JointTrajectory",
        "apply_twist_commands_about_ee_frame":True,
        "collision_check_rate":10.,
        "self_collision_proximity_threshold":.01,
        "scene_collision_proximity_threshold":.02,
        "lower_singularity_threshold":17.,"hard_stop_singularity_threshold":30.,
        "leaving_singularity_threshold_multiplier":2.,
        "override_velocity_scaling_factor":0.,
        "halt_all_joints_in_joint_mode":True,"halt_all_joints_in_cartesian_mode":True,
    }


def planning_parameters(base, model_urdf, profile):
    """Keep manufacturer acceleration settings; narrow velocity bounds."""
    result=deepcopy(base)
    section=result["robot_description_planning"]
    rows=section["joint_limits"]
    root=xml_root(model_urdf.encode())
    model=model_bounds(model_urdf)
    for i,name in enumerate(JOINTS):
        row=rows[name]
        limit=only(root,f'joint[@name="{name}"]/limit')
        velocity=float(limit.get("velocity"))
        configured=row.get("max_velocity")
        lo,hi=profile.joint_limits[i]
        if (row.get("has_velocity_limits") is not True
                or not finite(configured) or not finite(velocity)
                or profile.joint_velocity_max[i]>min(velocity,configured)
                or lo<model[i][0] or hi>model[i][1]
                or row.get("has_acceleration_limits") is not True
                or not finite(row.get("max_acceleration")) or row["max_acceleration"]<=0):
            raise ValueError("profile exceeds model/MoveIt reference")
        row["max_velocity"]=profile.joint_velocity_max[i]
    # Do not publish a gripper limit for an absent effector.
    section["joint_limits"]={name:rows[name] for name in JOINTS}
    # These are MoveGroup planning-request defaults, not Servo node
    # parameters. Servo declares the actual joint limit entries instead.
    # Do not request undeclared planning-request defaults from Servo.
    section.pop("default_velocity_scaling_factor",None)
    section.pop("default_acceleration_scaling_factor",None)
    return result


def scalar_parameters(tree, prefix=""):
    """Readback inventory without accepting arrays or mutable free-form values."""
    result={}
    for key,value in tree.items():
        name=prefix+key
        if isinstance(value,dict):
            result.update(scalar_parameters(value,name+"."))
        elif type(value) in (str,bool,int,float):
            result[name]=value
        else:
            raise ValueError("unexpected non-scalar configuration "+name)
    return result


def contract_for_loaded_model(routes, profile, params, scene_digest):
    """Construct expected observation settings from an independently checked scene.

    A digest alone is not acceptance. The caller must not use a fixture or
    shadow receipt as physical commissioning approval.
    """
    verify_tcp(params["robot_description"],params["robot_description_semantic"])
    expected=servo_parameters(routes,profile)
    if params["moveit_servo"]!=expected or params.get("use_sim_time") is not False:
        raise ValueError("Servo configuration differs from composition")
    rows=params["robot_description_planning"]["joint_limits"]
    if set(rows)!=set(JOINTS) or any(
        rows[n].get("has_velocity_limits") is not True or
        rows[n].get("max_velocity")!=profile.joint_velocity_max[i]
        for i,n in enumerate(JOINTS)):
        raise ValueError("joint velocity profile differs")
    inventory=scalar_parameters(params)
    return Contract(routes,scene_digest,tuple(sorted(inventory.items())),profile.tracking_error_max)


@dataclass(frozen=True)
class OwnerWiring:
    """Explicit, already reviewed physical contract and motion profile.

    This is code-level composition, not an operator approval mechanism.
    There is no constructor from a diagnostic receipt or review bundle.
    A future commissioning entrypoint must verify as-built scene/TCP,
    current firmware and accepted motion envelope before supplying this.
    """
    profile: Profile
    contract: Contract

    def __post_init__(self):
        if not isinstance(self.profile,Profile) or not isinstance(self.contract,Contract):
            raise ValueError("typed commissioning inputs required")
        if self.contract.routes!=Routes.physical():
            raise ValueError("physical namespace required")
        p=dict(self.contract.parameters)
        model=p["robot_description"]
        verify_tcp(model,p["robot_description_semantic"])
        expected=scalar_parameters({"moveit_servo":servo_parameters(self.contract.routes,self.profile),
                                   "use_sim_time":False})
        if any(k not in p or type(p[k]) is not type(v) or p[k]!=v for k,v in expected.items()):
            raise ValueError("profile/Servo contract mismatch")
        if self.contract.scene_tracking_max_rad!=self.profile.tracking_error_max:
            raise ValueError("tracking limit mismatch")
        for i,(name,(lo,hi)) in enumerate(zip(JOINTS,self.profile.joint_limits)):
            lower,upper=model_bounds(model)[i]
            prefix="robot_description_planning.joint_limits."+name+"."
            if (lo<lower or hi>upper or p.get(prefix+"has_velocity_limits") is not True
                    or p.get(prefix+"max_velocity")!=self.profile.joint_velocity_max[i]):
                raise ValueError("profile/model joint limits mismatch")


def prepare_owner_start(wiring, first, second, *, now):
    """Derive the startup model and contract from fresh owner feedback.

    Only an already reviewed OwnerWiring is accepted. No change to its
    approved scene fingerprint, profile, robot geometry or Servo routing.
    The returned seed is an observation, not a physical position command.
    This pure preparation step neither starts a pipeline nor commissions
    the robot. The live owner must recheck JTC/SDK agreement before ENABLE
    and each JOG, even if the virtual controller took time to start.
    """
    from .nero_manual_start import initial_virtual_model
    if not isinstance(wiring,OwnerWiring):
        raise ValueError("reviewed owner wiring required")
    model=dict(wiring.contract.parameters)["robot_description"]
    seeded,seed=initial_virtual_model(model,first,second,profile=wiring.profile,now=now)
    params=tuple((key,seeded if key=="robot_description" else value)
                 for key,value in wiring.contract.parameters)
    prepared=OwnerWiring(wiring.profile,replace(wiring.contract,parameters=params))
    return prepared,seed


def existing_owner_factory(wiring, *, approval_directory, socket_path, relay_binary,
                           twist_mode_confirmed):
    """Bind the existing runtime to the single guarded owner, not a new SDK.

    Only an explicitly commissioned caller may supply OwnerWiring.
    No CLI, service install, approval generation, mode change or drive enable.
    The existing runtime retains the independent SDK and session interlocks.
    """
    from pathlib import Path
    from .nero import NODE
    from .protocol import checked_path
    from .luxonis import private_directory
    if not isinstance(wiring,OwnerWiring) or not callable(twist_mode_confirmed):
        raise ValueError("explicit commissioned owner wiring required")
    approval=private_directory(Path(approval_directory))
    socket=checked_path(socket_path)
    if socket.parent==approval or approval.is_relative_to(socket.parent) or socket.parent.is_relative_to(approval):
        raise ValueError("separate private approval and command directories required")
    attached=False

    def attach(owner,native_hold):
        nonlocal attached
        if attached or owner.get_fully_qualified_name()!=NODE:
            raise ValueError("expected single existing guarded owner")
        if getattr(native_hold,"__self__",None) is not owner:
            raise ValueError("HOLD must belong to the same guarded owner")
        # No fallback to a second SDK or synthetic authority.
        from .ros_nero_manual import ManualRuntime
        from .ros_nero_manual_pipeline import RosPipelineMonitor
        monitor=RosPipelineMonitor(owner,wiring.contract,
                                   twist_mode_confirmed=twist_mode_confirmed)
        try:
            runtime=ManualRuntime(owner,profile=wiring.profile,approval_directory=approval,
                                  socket_path=socket,relay_binary=relay_binary,
                                  pipeline_authority=monitor,native_hold=native_hold,
                                  model_urdf=dict(wiring.contract.parameters)["robot_description"])
        except BaseException:
            monitor.close()
            raise
        attached=True
        return runtime
    return attach
