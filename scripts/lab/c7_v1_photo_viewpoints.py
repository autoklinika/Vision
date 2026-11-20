#!/usr/bin/env python3
"""Vision C7 V1 — generate OFFLINE photo-viewpoint/MoveIt IK candidates.

No ROS/MoveIt client, no robot SDK, no TF publisher, no execution path.
All geometry uses operator-reported LAB profile and explicit unapproved hypotheses.
Python standard library only; no camera or physical-robot access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


class InputError(ValueError):
    """Invalid scenario/profile: do not emit a potentially misleading pose."""


def number(value, name, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise InputError(f"{name} out of range")
    return result


def vec(data, name, length):
    if not isinstance(data, list) or len(data) != length:
        raise InputError(f"{name} must have {length} numbers")
    return [number(v, f"{name}[{i}]") for i, v in enumerate(data)]


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def rigid(rotation, position=(0, 0, 0)):
    return [[*rotation[i], position[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def inverse(t):
    r = [[t[i][j] for j in range(3)] for i in range(3)]
    trans = [t[i][3] for i in range(3)]
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    p = [-sum(rt[i][k] * trans[k] for k in range(3)) for i in range(3)]
    return rigid(rt, p)


def transform(t, xyz):
    return [sum(t[i][j] * xyz[j] for j in range(3)) + t[i][3] for i in range(3)]


def rz(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def rx(rad):
    c, s = math.cos(rad), math.sin(rad)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def ry(rad):
    c, s = math.cos(rad), math.sin(rad)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def mat3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def orthonormal(r):
    cols = [[r[i][j] for i in range(3)] for j in range(3)]
    for i in range(3):
        if abs(sum(x * x for x in cols[i]) - 1) > 1e-6:
            return False
        for j in range(i):
            if abs(sum(x * y for x, y in zip(cols[i], cols[j]))) > 1e-6:
                return False
    a, b, c = r
    determinant = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    return abs(determinant - 1) < 1e-6


def validated_pose(matrix, name):
    if not isinstance(matrix, list) or len(matrix) != 4:
        raise InputError(f"{name}: expected 4x4 matrix")
    rows = [vec(r, name, 4) for r in matrix]
    if any(abs(x-y) > 1e-9 for x, y in zip(rows[3], [0, 0, 0, 1])):
        raise InputError(f"{name}: invalid homogeneous last row")
    if not orthonormal([row[:3] for row in rows[:3]]):
        raise InputError(f"{name}: rotation is not proper orthonormal")
    return rows


def quaternion(r):
    """Return normalized quaternion xyzw for proper rotation matrix."""
    tr = sum(r[i][i] for i in range(3))
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        x = (r[2][1] - r[1][2]) / s
        y = (r[0][2] - r[2][0]) / s
        z = (r[1][0] - r[0][1]) / s
        w = s * .25
    else:
        i = max(range(3), key=lambda k: r[k][k])
        if i == 0:
            s = math.sqrt(1 + r[0][0] - r[1][1] - r[2][2]) * 2
            x = s * .25
            y = (r[0][1] + r[1][0]) / s
            z = (r[0][2] + r[2][0]) / s
            w = (r[2][1] - r[1][2]) / s
        elif i == 1:
            s = math.sqrt(1 + r[1][1] - r[0][0] - r[2][2]) * 2
            x = (r[0][1] + r[1][0]) / s
            y = s * .25
            z = (r[1][2] + r[2][1]) / s
            w = (r[0][2] - r[2][0]) / s
        else:
            s = math.sqrt(1 + r[2][2] - r[0][0] - r[1][1]) * 2
            x = (r[0][2] + r[2][0]) / s
            y = (r[1][2] + r[2][1]) / s
            z = s * .25
            w = (r[1][0] - r[0][1]) / s
    q = [x, y, z, w]
    length = math.sqrt(sum(v * v for v in q))
    return [v / length for v in q]


def rotations_from_vendor(profile):
    obj = profile["vendor_T_link7_flange"]
    xyz = vec(obj["xyz_m"], "vendor xyz", 3)
    roll, pitch, yaw = vec(obj["rpy_rad"], "vendor rpy", 3)
    return rigid(mat3(mat3(rz(math.degrees(yaw)), ry(pitch)), rx(roll)), xyz)


def validate_profile(p):
    if p.get("schema_version") != 1:
        raise InputError("Unsupported profile schema_version")
    if p.get("status") != "LAB_ASSUMED_NOT_METROLOGICALLY_APPROVED":
        raise InputError("Only unapproved LAB profile supported")
    policy = p["execution_policy"]
    prohibited = ("allow_trajectory_execution", "publish_static_tf", "activate_production_profile",
                  "send_robot_commands", "use_for_collision_safety")
    if any(policy.get(key) is not False for key in prohibited):
        raise InputError("A LAB profile may never authorize execution or TF activation")
    if p.get("candidate_T_table_base_link_approved") is not False:
        raise InputError("This tool only works with an explicitly unapproved table->base candidate")
    tool = p["tool_hypothesis"]
    if tool["signed_azimuth_options_deg"] != [90, -90]:
        raise InputError("C7 V1 requires both unresolved azimuth signs ±90")
    if (tool["socket_plusZ_relative_flange_plusZ"] != 1 or
            tool["socket_plusZ_sign_physically_verified"] is not False or
            tool["axial_offset_physically_verified"] is not False):
        raise InputError("Unexpected physical assumptions in C7 V1")
    if number(tool["flange_to_socket_axial_offset_mm"], "axial") != 0:
        raise InputError("Only the unverified zero-offset nominal candidate is currently implemented")
    t = validated_pose(p["candidate_T_table_base_link"], "candidate_T_table_base_link")
    flange = rotations_from_vendor(p)
    lens_offset = vec(p["sony_dummy_v2"]["socket_to_lens_front_center_mm"], "lens", 3)
    if lens_offset != [0.0, 74.0, 36.0]:
        raise InputError("Unexpected socket-to-lens CAD geometry")
    optical = vec(p["sony_dummy_v2"]["optical_axis_in_socket"], "optical", 3)
    if optical != [0.0, 1.0, 0.0]:
        raise InputError("Expected Sony CAD +Y optical direction")
    table = p["measured_table_mm"]
    width = number(table["width_x"], "table width", minimum=1)
    depth = number(table["depth_y"], "table depth", minimum=1)
    return t, flange, lens_offset, width, depth


def validate_scene(s, width, depth):
    prohibited_scene_keys = ("execute", "execution", "allow_trajectory_execution", "move_robot", "publish_tf", "activate")
    if any(key in s or key in s.get("camera", {}) for key in prohibited_scene_keys):
        raise InputError("Execution/activation directives are forbidden in photo planning input")
    if s.get("schema_version") != 1:
        raise InputError("Unsupported scene schema_version")
    if s.get("evidence_kind") not in ("synthetic_fixture", "operator_measured", "vision_perception_candidate"):
        raise InputError("Scene source must identify synthetic, operator-measured or perception-candidate")
    for key in ("scenario_id", "ecu_type"):
        if not isinstance(s.get(key), str) or not s[key].strip():
            raise InputError(f"Missing {key}")
    pcb = s["pcb"]
    center = vec(pcb["center_table_xy_mm"], "center", 2)
    size = vec(pcb["size_xy_mm"], "size", 2)
    if any(v <= 0 for v in size):
        raise InputError("PCB sizes must be positive")
    z = number(pcb["top_z_mm"], "top_z_mm", minimum=0)
    yaw = number(pcb.get("yaw_table_deg", 0), "yaw_table_deg")
    camera = s["camera"]
    distance = number(camera["lens_front_working_distance_mm"], "lens working distance", minimum=1)
    fraction = number(camera.get("quadrant_fraction", .28), "quadrant fraction", minimum=0)
    if fraction >= .5:
        raise InputError("quadrant_fraction must be below .5")
    # Verify all actual PCB corners, not only the center, are on the table.
    a = math.radians(yaw)
    c, ss = math.cos(a), math.sin(a)
    for dx in (-size[0]/2, size[0]/2):
        for dy in (-size[1]/2, size[1]/2):
            x = center[0] + c*dx - ss*dy
            y = center[1] + ss*dx + c*dy
            if not (0 < x < width and 0 < y < depth):
                raise InputError("PCB footprint extends outside measured tabletop")
    return center, size, z, yaw, distance, fraction


def near(a, b, tolerance=1e-8):
    return max(abs(x-y) for x, y in zip(a, b)) <= tolerance


def generate(profile, scene):
    t_table_base, t_link7_flange, lens_offset_mm, width, depth = validate_profile(profile)
    center, size, top_z, yaw, distance, fraction = validate_scene(scene, width, depth)
    # Socket +Y is the CAD lens optical direction. Top-down photo: +Y points down table Z.
    # Socket +Z points toward back of PCB (+Y after PCB yaw), an arbitrary image-up hypothesis.
    r_table_socket0 = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]
    r_table_socket = mat3(rz(yaw), r_table_socket0)
    if not orthonormal(r_table_socket):
        raise InputError("Invalid camera look-down frame")
    lens_offset_m = [v / 1000 for v in lens_offset_mm]
    t_base_table = inverse(t_table_base)
    t_flange_link7 = inverse(t_link7_flange)
    offsets = [
        ("center", 0, 0),
        ("front_left", -fraction, -fraction),
        ("front_right", fraction, -fraction),
        ("back_right", fraction, fraction),
        ("back_left", -fraction, fraction),
    ]
    results = []
    for label, xf, yf in offsets:
        ox, oy = xf * size[0], yf * size[1]
        theta = math.radians(yaw)
        target = [center[0] + math.cos(theta)*ox - math.sin(theta)*oy,
                  center[1] + math.sin(theta)*ox + math.cos(theta)*oy]
        if not (0 < target[0] < width and 0 < target[1] < depth):
            raise InputError("Candidate view target outside tabletop")
        lens_table = [target[0] / 1000, target[1] / 1000, (top_z + distance) / 1000]
        socket_offset_table = [
            sum(r_table_socket[i][j] * lens_offset_m[j] for j in range(3)) for i in range(3)
        ]
        socket_xyz = [lens_table[i] - socket_offset_table[i] for i in range(3)]
        t_table_socket = rigid(r_table_socket, socket_xyz)
        for signed_azimuth in profile["tool_hypothesis"]["signed_azimuth_options_deg"]:
            # From CAD optical +Y to (cos(a), sin(a), 0) in flange.
            r_flange_socket = rz(90 - signed_azimuth)
            t_flange_socket = rigid(r_flange_socket)
            t_table_link7 = multiply(multiply(t_table_socket, inverse(t_flange_socket)), t_flange_link7)
            t_base_link7 = multiply(t_base_table, t_table_link7)
            pose_rotation = [r[:3] for r in t_base_link7[:3]]
            if not orthonormal(pose_rotation):
                raise InputError("Invalid computed robot pose")
            # Self-consistency: the computed link7 candidate returns the requested lens point.
            check = multiply(multiply(t_table_base, t_base_link7),
                             multiply(t_link7_flange, t_flange_socket))
            lens_reprojected = transform(check, lens_offset_m)
            if not near(lens_reprojected, lens_table):
                raise InputError("Lens center transform chain failed round trip")
            boresight_table = [sum(r_table_socket[i][j] * [0,1,0][j] for j in range(3)) for i in range(3)]
            if not near(boresight_table, [0, 0, -1]):
                raise InputError("Camera is not looking vertically down")
            results.append({
                "view_id": label,
                "mount_signed_azimuth_assumption_deg": signed_azimuth,
                "target_pcb_table_xy_mm": [round(v, 4) for v in target],
                "camera_lens_front_center_table_xyz_mm": [round(v * 1000, 4) for v in lens_table],
                "sony_optical_direction_table_unit": [round(v, 6) for v in boresight_table],
                "link7_IK_candidate": {
                    "header_frame_id": "base_link",
                    "link_name": "link7",
                    "position_m": [round(t_base_link7[i][3], 9) for i in range(3)],
                    "quaternion_xyzw": [round(v, 10) for v in quaternion(pose_rotation)],
                    "source": "candidate C2 table_base + C7 nominal tool, not physically validated"
                },
                "inverse_kinematics_checked": False,
                "collision_checked": False,
                "trajectory_generated": False,
                "execution_allowed": False,
            })
    return {
        "schema_version": 1,
        "status": "OFFLINE_VIEWPOINT_CANDIDATES_ONLY",
        "profile_id": profile["profile_id"],
        "scenario_id": scene["scenario_id"],
        "ecu_type": scene["ecu_type"],
        "scene_evidence_kind": scene["evidence_kind"],
        "working_distance_mm": distance,
        "real_optical_center_not_calibrated": True,
        "table_to_base_tf_not_approved": True,
        "signed_azimuth_not_resolved": True,
        "source_profile_sha256": hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
        "source_scene_sha256": hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest(),
        "views_requested": len(offsets),
        "mount_variants_per_view": 2,
        "candidate_count": len(results),
        "IK_solved": False,
        "MoveIt_planning_executed": False,
        "physical_execution_allowed": False,
        "active_TF_published": False,
        "candidates": results
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text())
        scene = json.loads(args.scene.read_text())
        result = generate(profile, scene)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except (InputError, ValueError, KeyError, TypeError, FileExistsError) as exc:
        parser.error(str(exc))
    print(f"C7_V1_OFFLINE_VIEWPOINT_CANDIDATES_PASS count={result['candidate_count']} output={args.output}")
    print("IK=NOT_CHECKED MOVEIT=NOT_CALLED PHYSICAL_EXECUTION=DISALLOWED TF=UNPUBLISHED")


if __name__ == "__main__":
    main()
