#!/usr/bin/env python3
"""C7 V1 adapter for Vision Perception outputs, strictly PLAN-ONLY.

Historical Vision Perception exports are CAMERA-FRAME ONLY. Such data may be
inspected and archived, but MUST NOT be transformed into a fabricated table
pose or a photo/MoveIt target. Only explicit PCB-in-table-frame observations
can be converted into a C7 V1 scene, still explicitly unapproved for motion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


class BlockedInput(ValueError):
    pass


def _finite(value, label, low=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BlockedInput(f"{label} is not a finite number")
    n = float(value)
    if low is not None and n < low:
        raise BlockedInput(f"{label} below minimum {low}")
    return n


def _vector(seq, label, length):
    if not isinstance(seq, list) or len(seq) != length:
        raise BlockedInput(f"{label} expected {length} values")
    return [_finite(x, f"{label}[{i}]") for i, x in enumerate(seq)]


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def import_observation(raw: dict, *, source_path: str = "") -> dict:
    """Returns a reasoned BLOCKED result or an unapproved C7 V1 JSON scene."""
    if not isinstance(raw, dict):
        raise BlockedInput("Perception record must be JSON object")
    schema = raw.get("schema_version")
    if schema == "perception.scene_observation.v1":
        if raw.get("safety_function") is not False:
            raise BlockedInput("Missing false non-safety flag")
        if raw.get("table_frame", {}).get("status") != "UNAVAILABLE" or raw.get("robot_base_frame", {}).get("status") != "UNAVAILABLE":
            # The actual v1 contract only supports unavailable poses; a new schema is mandatory for later table-space records.
            raise BlockedInput("v1 camera-only contract cannot carry a certified table/base pose")
        frame = raw.get("frame_of_reference")
        if frame != "stereo_left_rectified_optical":
            raise BlockedInput("Unexpected optical frame")
        objects = raw.get("objects", [])
        if not isinstance(objects, list):
            raise BlockedInput("Invalid objects")
        camera_positions = [
            {"object_id": obj.get("object_id"), "class": obj.get("class"),
             "position_camera_m": _vector(obj["position_camera_m"], "camera xyz", 3)}
            for obj in objects if isinstance(obj, dict) and isinstance(obj.get("position_camera_m"), list)
        ]
        return {
            "status": "BLOCKED_CAMERA_FRAME_ONLY",
            "reason_codes": ["TABLE_FRAME_UNAVAILABLE", "ROBOT_BASE_FRAME_UNAVAILABLE",
                             "PCB_IDENTITY_AND_TOP_SURFACE_NOT_CONFIRMED"],
            "observed_schema": schema,
            "source_bundle_id": raw.get("source_bundle_id"),
            "source_path": source_path,
            "source_hash_sha256": _hash(raw),
            "camera_geometry": camera_positions,
            "validity": raw.get("validity"),
            "PCB_table_scene": None,
            "MoveIt_targets_generated": False,
            "physical_execution_allowed": False
        }
    if schema == "vision.historical_ecu_geometry.v1":
        summary = raw.get("summary")
        if not isinstance(summary, dict):
            raise BlockedInput("Historical ECU summary missing")
        if summary.get("table_frame") != "UNAVAILABLE" or summary.get("robot_base_frame") != "UNAVAILABLE":
            raise BlockedInput("Historical source unexpectedly contains table frame")
        if summary.get("camera_frame") != "stereo_left_rectified_optical":
            raise BlockedInput("Historical source camera optical frame mismatch")
        if summary.get("metrology_verified") is not False:
            raise BlockedInput("Historical source must remain explicitly unverified")
        source_frames = int(_finite(summary.get("frames_total"), "frames", 1))
        detected = int(_finite(summary.get("frames_geometry_detected"), "detected", 0))
        if detected > source_frames or source_frames < 1:
            raise BlockedInput("Invalid historical frame count")
        stats = summary.get("stats")
        if not isinstance(stats, dict):
            raise BlockedInput("Historical size stats unavailable")
        fields = ("core_footprint_length_mm", "core_footprint_width_mm",
                  "height_visible_envelope_p99_mm")
        measured = {f: _finite(stats[f]["median"], f, 0) for f in fields}
        return {
            "status": "BLOCKED_HISTORICAL_ETC3_VISIBLE_PCB_UNSEGMENTED_CAMERA_ONLY",
            "reason_codes": ["OPEN_PCB_VISIBLE_IN_RGB_BUT_NOT_SEGMENTED_IN_DEPTH",
                             "TABLE_FRAME_UNAVAILABLE", "ROBOT_BASE_FRAME_UNAVAILABLE",
                             "WHOLE_ECU_FOOTPRINT_NOT_PCB_SIZE",
                             "METROLOGY_NOT_VALIDATED"],
            "observed_schema": schema,
            "camera_frame": "stereo_left_rectified_optical",
            "source_path": source_path,
            "source_hash_sha256": _hash(raw),
            "frames_total": source_frames, "frames_geometry_detected": detected,
            "exploratory_visible_ECU_assembly_envelope_camera_frame_mm": measured,
            "pcb_visible_in_source_rgb": True,
            "pcb_individual_surface_segmentation_status": "UNAVAILABLE",
            "PCB_table_scene": None,
            "MoveIt_targets_generated": False,
            "physical_execution_allowed": False
        }
    if schema == "vision.perception_pcb_table.v1":
        # A narrow future table-space interface: it must be an explicit PCB
        # surface observation, never repurposed from camera-frame ECU housing.
        if raw.get("safety_function") is not False:
            raise BlockedInput("Perception cannot declare a safety function")
        if raw.get("status") not in ("CANDIDATE_UNVERIFIED", "OPERATOR_MEASURED_UNVERIFIED"):
            raise BlockedInput("Only candidate/unverified records permitted")
        if raw.get("frame_of_reference") != "table":
            raise BlockedInput("PCB frame must be table")
        if raw.get("object_class") != "pcb" or raw.get("pcb_surface") != "top":
            raise BlockedInput("PCB top surface not explicitly segmented")
        if raw.get("fixture_only") is True:
            if raw.get("source_kind") != "synthetic_fixture":
                raise BlockedInput("Test fixture must be explicitly declared synthetic")
        elif raw.get("source_kind") not in ("vision_perception_candidate", "operator_measured"):
            raise BlockedInput("Invalid provenance")
        if raw.get("fixture_only") not in (None, True, False):
            raise BlockedInput("Invalid fixture_only marker")
        if raw.get("calibration_approved") is not False:
            raise BlockedInput("C7 V1 does not consume approved TF as an implicit shortcut")
        if not isinstance(raw.get("source_bundle_id"), str) or not raw["source_bundle_id"]:
            raise BlockedInput("Missing traceable source bundle")
        if not isinstance(raw.get("source_artifact_sha256"), str) or len(raw["source_artifact_sha256"]) != 64:
            raise BlockedInput("Missing full SHA256 artifact provenance")
        if not all(x in "0123456789abcdef" for x in raw["source_artifact_sha256"].lower()):
            raise BlockedInput("Invalid sha256 evidence hash")
        pcb=raw.get("pcb")
        if not isinstance(pcb,dict):
            raise BlockedInput("PCB geometric object missing")
        center=_vector(pcb.get("center_table_xy_mm"), "center_table_xy_mm", 2)
        dims=_vector(pcb.get("size_xy_mm"), "size_xy_mm", 2)
        z=_finite(pcb.get("top_z_mm"), "top_z_mm", 0)
        yaw=_finite(pcb.get("yaw_table_deg"), "yaw_table_deg")
        if not all(s > 0 for s in dims):
            raise BlockedInput("PCB dimensions must be positive")
        camera=raw.get("camera")
        if not isinstance(camera,dict):
            raise BlockedInput("Camera working-distance plan missing")
        distance=_finite(camera.get("lens_front_working_distance_mm"), "working_distance_mm", 1)
        output={
            "schema_version": 1, "scenario_id": "C7_"+raw["source_bundle_id"],
            "ecu_type": raw.get("ecu_type", "ETC3"),
            "evidence_kind": raw["source_kind"],
            "source_observation": {
                "schema_version":schema,
                "source_bundle_id":raw["source_bundle_id"],
                "source_artifact_sha256":raw["source_artifact_sha256"],
                "source_path":source_path,
                "source_record_sha256":_hash(raw),
                "transform_status":"CANDIDATE_UNVERIFIED"
            },
            "pcb":{
                "center_table_xy_mm":center,"size_xy_mm":dims,
                "top_z_mm":z,"yaw_table_deg":yaw
            },
            "camera":{
                "lens_front_working_distance_mm":distance,
                "quadrant_fraction":_finite(camera.get("quadrant_fraction",0.28),
                                           "quadrant_fraction",0)
            }
        }
        # Optional scene obstacle representing the *whole ECU assembly*, not
        # PCB substrate. Required for real C7 live data to avoid treating the
        # PCB's median height as the highest connector/case collision surface.
        env=raw.get("obstacle_envelope")
        if env is not None:
            if not isinstance(env,dict) or env.get("source_status") != "EXPLORATORY_UNVERIFIED":
                raise BlockedInput("Whole-ECU obstacle must declare its unverified provenance")
            ocenter=_vector(env.get("center_table_xy_mm"),"obstacle center_table_xy_mm",2)
            osize=_vector(env.get("size_xy_mm"),"obstacle size_xy_mm",2)
            oz=_finite(env.get("height_above_table_mm"),"obstacle height_above_table_mm",0.1)
            oyaw=_finite(env.get("yaw_table_deg",0),"obstacle yaw_table_deg")
            if min(osize)<=0 or oz < z:
                raise BlockedInput("Invalid obstacle size or connector height smaller than PCB top")
            output["obstacle_envelope"]={
                "source_status":"EXPLORATORY_UNVERIFIED",
                "center_table_xy_mm":ocenter,
                "size_xy_mm":osize,
                "height_above_table_mm":oz,
                "yaw_table_deg":oyaw,
                "not_safety_approved":True
            }
        if not isinstance(output["ecu_type"],str) or not output["ecu_type"].strip():
            raise BlockedInput("ECU identity required")
        return {
            "status":"UNAPPROVED_PCB_SCENE_READY_FOR_OFFLINE_VIEWPOINTS",
            "scene":output,
            "source_schema":schema,"source_hash_sha256":_hash(raw),
            "table_TF_approved":False,"execution_allowed":False
        }
    raise BlockedInput(f"Unsupported perception schema {schema!r}; no implicit fallback")


def import_legacy_etc3(data: dict, *, source_path: str) -> dict:
    """Read actual private ECU camera-frame replay; RGB may visibly contain PCB, but no isolated PCB metrology."""
    if not isinstance(data,dict) or "summary" not in data:
        raise BlockedInput("Missing real historical ECU summary")
    return import_observation({"schema_version":"vision.historical_ecu_geometry.v1",
                               "summary":data["summary"]},source_path=source_path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--legacy-etc3", action="store_true")
    a=p.parse_args()
    try:
        data=json.loads(a.input.read_text())
        result=(import_legacy_etc3(data,source_path=str(a.input)) if a.legacy_etc3
                else import_observation(data,source_path=str(a.input)))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x") as f:
            json.dump(result,f,indent=2,ensure_ascii=False)
            f.write("\n")
    except (BlockedInput,ValueError,TypeError,KeyError,FileExistsError) as e:
        p.error(str(e))
    print("VISION_PERCEPTION_IMPORT",result["status"],"to",a.output)
    print("MOTION_FORBIDDEN; NO ROS OR CAN ACCESS")
if __name__=="__main__":main()
