"""Private, offline review bundle for the manual station model.

No hardware or ROS initialization. This bundle is deliberately not an
approved physical profile, an owner factory, or a launch configuration.
The commissioning path must obtain separate live evidence and approval.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .nero_joint_limits import JOINTS, intersection, model_bounds, valid_pair, valid_source
from .nero_manual import finite, vector7

SCHEMA = "vision.nero.manual-station-candidate.v1"
STATUS = "OFFLINE_REVIEW_ONLY"
FILES = (
    "source.urdf", "model.urdf", "model.srdf", "scene.cdr",
    "assembly.json", "controller-limits.json", "historical-pose.json",
)
MAX_BYTES = 16 * 1024 * 1024
REVIEW = (
    "LIVE_RECEIVER_AND_FEEDBACK",
    "AS_BUILT_TOOL_AND_STATION_CLEARANCE",
    "OPERATOR_TCP_REFERENCE_SELECTION",
    "CURRENT_FIRMWARE_LIMITS_AND_SPEED_PROFILE",
    "EXCLUSIVE_OWNER_AND_HOLD_ACCEPTANCE",
    "SUPERVISED_PHYSICAL_ACCEPTANCE",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bounded(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular review artifact required: " + path.name)
    with path.open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    if not 0 < len(data) <= MAX_BYTES:
        raise ValueError("invalid review artifact size: " + path.name)
    return data


def decode(data):
    def pairs(rows):
        result = {}
        for k, v in rows:
            if k in result:
                raise ValueError("duplicate JSON field")
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def xml_root(data):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("external XML declarations forbidden")
    root = ET.fromstring(data)
    if root.tag != "robot":
        raise ValueError("robot description required")
    return root


def only(root, xpath):
    rows = root.findall(xpath)
    if len(rows) != 1:
        raise ValueError("missing or ambiguous model element: " + xpath)
    return rows[0]


def mount_face_model(urdf, srdf, assembly):
    """Only reparent the empty TCP link; retain all collision geometry."""
    if (assembly.get("physicalExecutionAllowed") is not False
            or assembly.get("armKinematicsUnchanged") is not True
            or assembly.get("adapterAddedOffsetMm") != 0
            or assembly.get("toolTouchLinks") != ["flange_link"]):
        raise ValueError("unexpected source assembly")
    offset = assembly.get("faceOffsetInFlangeFrameMm")
    if not finite(offset) or not 0 < offset <= 100:
        raise ValueError("explicit measured/model flange face required")
    root = xml_root(urdf)
    semantic = xml_root(srdf)
    if root.get("name") != semantic.get("name"):
        raise ValueError("URDF/SRDF robot mismatch")
    moving = [j.get("name") for j in root.findall("joint") if j.get("type") != "fixed"]
    if tuple(moving) != JOINTS:
        raise ValueError("unexpected movable joints")
    model_bounds(urdf)
    chain = only(semantic, 'group[@name="arm"]/chain')
    if chain.attrib != {"base_link": "base_link", "tip_link": "tcp_link"}:
        raise ValueError("unexpected arm chain")
    tcp_link = only(root, 'link[@name="tcp_link"]')
    if list(tcp_link):
        raise ValueError("TCP must be a geometry-free frame")
    tcp = only(root, 'joint[@name="tcp_joint"]')
    flange = only(root, 'joint[@name="flange_joint"]')
    if (tcp.get("type") != "fixed" or flange.get("type") != "fixed"
            or only(tcp,"parent").get("link") != "link7"
            or only(tcp,"child").get("link") != "tcp_link"
            or only(flange,"parent").get("link") != "link7"
            or only(flange,"child").get("link") != "flange_link"
            or tuple(map(float,only(tcp,"origin").get("xyz").split())) != (0.,0.,0.)
            or tuple(map(float,only(tcp,"origin").get("rpy").split())) != (0.,0.,0.)):
        raise ValueError("unexpected source TCP/flange transform")
    # Mechanical mount face center, with the factory flange axes. It is
    # not the camera optical center and is not a commissioned tool frame.
    only(tcp,"parent").set("link","flange_link")
    only(tcp,"origin").set("xyz","0 0 "+str(offset/1000))
    return ET.tostring(root, encoding="utf-8")


def collision_meshes(model, mesh_root, assembly, mesh_source_root=None):
    root = xml_root(model)
    prefix = "package://agx_arm_description/"
    base = Path(mesh_root).resolve(strict=True)
    # A colcon symlink install is supported only with an explicitly
    # declared source package. Each resolved filename must still agree
    # with its exact package-relative name. No arbitrary symlink targets.
    source = Path(mesh_source_root).resolve(strict=True) if mesh_source_root else None
    hashes = {}
    for mesh in root.findall("link/collision/geometry/mesh"):
        uri = mesh.get("filename","")
        if not uri.startswith(prefix):
            raise ValueError("unexpected collision mesh package")
        relative=Path(uri[len(prefix):])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid collision mesh path")
        target=(base/relative).resolve(strict=True)
        if target != base/relative and (source is None or target != source/relative):
            raise ValueError("collision mesh outside declared package")
        hashes[uri] = sha(read_bounded(target))
    flange = only(root, 'link[@name="flange_link"]/collision/geometry/mesh')
    if hashes.get(flange.get("filename")) != assembly.get("factoryFlangeMeshSha256"):
        raise ValueError("factory flange collision mesh differs")
    if len(hashes) != 9:
        raise ValueError("expected nine distinct NERO collision meshes")
    return hashes


def check_interpolator(model):
    root=xml_root(model)
    ctrl=only(root,"ros2_control")
    if only(ctrl,"hardware").findtext("plugin")!="mock_components/GenericSystem":
        raise ValueError("review bundle requires GenericSystem only")
    joints=ctrl.findall("joint")
    if tuple(j.get("name") for j in joints)!=JOINTS:
        raise ValueError("unexpected interpolation joint inventory")
    for j in joints:
        if [x.get("name") for x in j.findall("command_interface")]!=["position"]:
            raise ValueError("unexpected interpolation command interface")
        if set(x.get("name") for x in j.findall("state_interface"))!={"position","velocity"}:
            raise ValueError("unexpected interpolation state interface")


def archived_limits(model, firmware):
    if (firmware.get("schema") != "vision.nero.firmware-limit-observation.v1"
            or not valid_source(firmware.get("source"))):
        raise ValueError("expected recorded controller limit observation")
    started, captured = firmware["startedAt"], firmware["capturedAt"]
    if not finite(started) or not finite(captured) or not 0 < captured-started <= 30:
        raise ValueError("invalid observation window")
    rows = firmware["controllerRows"]
    if len(rows)!=7 or tuple(r["joint"] for r in rows)!=JOINTS:
        raise ValueError("incomplete or misordered firmware observation")
    bounds, speeds = [], []
    for r in rows:
        angles, speed, stamp = r["angleRad"],r["maxVelocityRadS"],r["responseAt"]
        if (not valid_pair(angles) or not finite(speed) or not 0 < speed <= 100
                or not finite(stamp) or not started <= stamp <= captured):
            raise ValueError("unverified controller limit")
        bounds.append(tuple(angles))
        speeds.append(speed)
    software = model_bounds(model)
    if tuple(tuple(r) for r in firmware["modelRad"]) != software:
        raise ValueError("recorded model limits differ from candidate")
    combined = intersection(intersection(firmware["sdkRad"],software),bounds)
    return {"source":"HISTORICAL_OBSERVATION","capturedAt":captured,
            "sdkVersion":firmware["source"]["sdkVersion"],
            "firmwareProfile":firmware["source"]["firmwareProfile"],
            "jointPositionRad":[list(r) for r in combined],
            "controllerMaxVelocityRadS":speeds,
            "manualSpeedProfileApproved":False}


def historical_pose(pose, limits):
    if (pose.get("status") != "OPERATOR_REPORTED_OEM_LINE_MOTION_COMPLETE"
            or pose.get("physicalMotionCommandedByAssistant") is not False
            or pose.get("errorCode") != 0
            or pose.get("motorsEnabled") != [True]*7
            or pose.get("motorVelocityRadS") != [0.]*7
            or not vector7(pose.get("canJointDeg"))
            or not isinstance(pose.get("utc"),str)):
        raise ValueError("historical stationary raised pose required")
    q = tuple(map(math.radians,pose["canJointDeg"]))
    if not all(lo<=x<=hi for x,(lo,hi) in zip(q,limits["jointPositionRad"])):
        raise ValueError("recorded pose outside archived joint limits")
    return {"source":"HISTORICAL_REPLAY_NOT_LIVE","utc":pose["utc"],"positionsRad":list(q)}


@dataclass(frozen=True)
class Candidate:
    manifest: dict
    urdf: str
    srdf: str
    scene: bytes
    historical_q: tuple


def derive(files, mesh_root, mesh_source_root=None):
    assembly = decode(files["assembly.json"])
    for filename,key in (("source.urdf","robotDescriptionSha256"),
                         ("model.srdf","semanticDescriptionSha256"),("scene.cdr","sceneSha256")):
        if sha(files[filename]) != assembly.get(key):
            raise ValueError("source assembly hash mismatch: "+filename)
    model = mount_face_model(files["source.urdf"],files["model.srdf"],assembly)
    check_interpolator(model)
    meshes=collision_meshes(model,mesh_root,assembly,mesh_source_root)
    limits = archived_limits(model,decode(files["controller-limits.json"]))
    pose = historical_pose(decode(files["historical-pose.json"]),limits)
    metadata = {
        "schema":SCHEMA,"status":STATUS,"physicalExecutionAllowed":False,
        "tcp":{"parent":"flange_link","child":"tcp_link","definition":"MECHANICAL_MOUNT_FACE_CENTER",
               "offsetMm":[0,0,assembly["faceOffsetInFlangeFrameMm"]],
               "rpyRad":[0,0,0],"opticalCenter":False,"operatorApproved":False},
        "limits":limits,"historicalPose":pose,"reviewRequired":list(REVIEW),
        "armKinematicsChanged":False,"collisionGeometryChanged":False,
        "collisionMeshSha256":meshes,
    }
    return model,metadata


def prepare(source, firmware, pose, output, *, mesh_root, mesh_source_root=None):
    source, output = Path(source),Path(output)
    if output.exists():
        raise FileExistsError("candidate bundles are never overwritten")
    files = {name:read_bounded(source/("model.urdf" if name=="source.urdf" else name))
             for name in ("source.urdf","model.srdf","scene.cdr","assembly.json")}
    files["controller-limits.json"]=read_bounded(firmware)
    files["historical-pose.json"]=read_bounded(pose)
    model,metadata=derive(files,mesh_root,mesh_source_root)
    files["model.urdf"]=model
    metadata["sha256"]={name:sha(data) for name,data in files.items()}
    output.mkdir(mode=0o700,parents=False)
    for name,data in files.items():
        with (output/name).open("xb") as f:
            f.write(data)
    with (output/"manifest.json").open("x",encoding="utf-8") as f:
        json.dump(metadata,f,sort_keys=True,indent=2,allow_nan=False)
        f.write("\n")
    return load(output,mesh_root=mesh_root,mesh_source_root=mesh_source_root)


def load(root, *, mesh_root, mesh_source_root=None):
    root=Path(root)
    if root.is_symlink() or set(x.name for x in root.iterdir()) != set(FILES)|{"manifest.json"}:
        raise ValueError("unexpected candidate artifact inventory")
    metadata=decode(read_bounded(root/"manifest.json"))
    files={name:read_bounded(root/name) for name in FILES}
    model,expected=derive(files,mesh_root,mesh_source_root)
    expected["sha256"]={name:sha(data) for name,data in files.items()}
    if files["model.urdf"]!=model or metadata!=expected:
        raise ValueError("candidate model or manifest differs from derived sources")
    return Candidate(metadata,model.decode(),files["model.srdf"].decode(),
                     files["scene.cdr"],tuple(metadata["historicalPose"]["positionsRad"]))
