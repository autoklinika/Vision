#!/usr/bin/env python3
"""Analyze private RAW16 three-height records using unchanged height_planes.v1.

All ROIs defined on FIRST visual observation before any live phase. The
reference heights are used only in QA, NEVER passed to the estimator.
Outputs aggregate JSON and private sample-level scalar results only.
No files with RGB or RAW16 are published to GitHub.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
import sys
import time

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parent))
from height_planes import estimate_height_planes, evaluate_reference_gate

ROOT=Path("/srv/vision-data/staging/oak-three-heights-private-20261113")
TARGETS={
    "beige_box": {
        "height_reference_mm":34.0,
        "object_roi_xyxy":(475,170,625,330),
        "table_roi_xyxy":(350,70,755,425),
        "shape":"rectangular_flat_top",
    },
    "red_cylinder": {
        "height_reference_mm":50.4,
        "object_roi_xyxy":(403,299,521,404),
        "table_roi_xyxy":(275,223,670,513),
        "shape":"circular_top_stereo_sparse",
    },
    "white_red_box": {
        "height_reference_mm":101.0,
        "object_roi_xyxy":(560,427,805,637),
        "table_roi_xyxy":(490,337,875,710),
        "shape":"rectangular_flat_top",
    },
}

def summary(values, attempted, reference):
    pass_values=[r for r in values if r["validity"]=="EXPLORATORY_UNVERIFIED_PROJECTION"]
    hs=np.asarray([v["height_mm"] for v in pass_values],dtype=np.float64)
    ok=len(hs)
    result={"attempted":attempted,"accepted":ok,
            "accepted_pct":round(100*ok/max(1,attempted),2),
            "physical_reference_mm":reference,
            "status":"MEASURED" if ok else "NOT_READY"}
    if not ok:
        return result
    result.update({
        "height_median_mm":round(float(np.median(hs)),3),
        "height_mean_mm":round(float(np.mean(hs)),3),
        "height_sample_std_mm":round(float(hs.std(ddof=1)),3) if ok>1 else None,
        "height_p05_mm":round(float(np.percentile(hs,5)),3),
        "height_p95_mm":round(float(np.percentile(hs,95)),3),
        "height_min_mm":round(float(hs.min()),3),
        "height_max_mm":round(float(hs.max()),3),
        "median_bias_mm":round(float(np.median(hs)-reference),3),
        "abs_error_p95_mm":round(float(np.percentile(np.abs(hs-reference),95)),3),
        "top_inlier_count_median":int(median(v["quality"]["top_inlier_count"] for v in pass_values)),
        "angle_deg_median":round(float(median(v["quality"]["top_table_normal_angle_deg"] for v in pass_values)),2),
        "top_rmse_mm_median":round(float(median(v["quality"]["top_rmse_mm"] for v in pass_values)),3),
        "table_rmse_mm_median":round(float(median(v["quality"]["table_rmse_mm"] for v in pass_values)),3),
        "depth_roi_valid_pct_median":round(float(median(v["quality"]["object_roi_valid_pct"] for v in pass_values)),2),
    })
    stats={
        "attempted":attempted,
        "usable":ok,
        "height_mm_median":result["height_median_mm"],
        "height_mm_p05":result["height_p05_mm"],
        "height_mm_p95":result["height_p95_mm"],
        "height_mm_sample_std":result["height_sample_std_mm"],
    }
    gate=evaluate_reference_gate(stats,reference)
    result["qa_gate"]=gate["status"]
    result["qa_reasons"]=gate["reasons"]
    result["metrology_certified"]=False
    return result


def analyze(mode):
    folder=ROOT/mode
    src=folder/"capture_result.json"
    capture=json.loads(src.read_text())
    aggregate={
        "mode":mode,"subpixel":capture.get("subpixel"),
        "capture_state":capture.get("state"),
        "production_restored":capture.get("production_restored"),
        "ir_off_ack":capture.get("ir_off_ack"),
        "target_roi_source":"manual_prior_rgb_and_raw_depth_visual_check_not_camera_registered",
        "reference_used_in_estimator":False,
        "metrology_certified":False,
        "safety_function":False,
        "camera_frame":"stereo_left_rectified_optical",
        "table_frame":"UNAVAILABLE",
        "robot_frame":"UNAVAILABLE",
        "phases":[],
    }
    full_results={}
    for phase in capture.get("phases",[]):
        tag=phase["phase"]
        with np.load(folder/phase["private_file"],allow_pickle=False) as data:
            frames=data["depth_mm"]
            K=data["K"]
            timestamps=data["device_timestamp_ns"]
        if len(frames)!=phase["frames_saved"]:
            raise RuntimeError("Mismatch in recorded frame count")
        row={"name":tag, "dot_pct":phase["dot_pct"],
             "rgb_fps":phase["rgb_fps"],"depth_fps":phase["depth_fps"],
             "missing_depth_seq":phase["depth_sequence_gaps"],
             "stored_frames":len(frames),
             "timestamp_span_seconds":round((int(timestamps[-1])-int(timestamps[0]))/1e9,2),
             "targets":{}}
        private={}
        start=time.perf_counter()
        for target,config in TARGETS.items():
            measurements=[]
            for frame in frames:
                m=estimate_height_planes(
                    frame,K,
                    config["object_roi_xyxy"],config["table_roi_xyxy"],
                    min_relative_height_mm=18.0,
                    max_relative_height_mm=150.0
                )
                measurements.append(m)
            row["targets"][target]=summary(
                measurements,len(measurements),config["height_reference_mm"])
            private[target]=measurements
        row["offline_processing_seconds"]=round(time.perf_counter()-start,2)
        aggregate["phases"].append(row)
        full_results[tag]=private
        print("THREE_HEIGHT_ANALYSIS_PHASE", json.dumps({
            "name":tag,"mode":mode,
            "targets":{k:{field:v.get(field) for field in (
               "accepted","attempted","height_median_mm","median_bias_mm",
               "height_sample_std_mm","qa_gate")}
               for k,v in row["targets"].items()}},
            ensure_ascii=False),flush=True)
    privatepath=folder/"three_heights_per_frame_private.json"
    privatepath.write_text(json.dumps(full_results,ensure_ascii=False,indent=2)+"\n")
    privatepath.chmod(0o600)
    aggregates=folder/"three_heights_aggregate.json"
    aggregates.write_text(json.dumps(aggregate,ensure_ascii=False,indent=2)+"\n")
    aggregates.chmod(0o600)
    print("THREE_HEIGHT_AGGREGATE",json.dumps(aggregate,ensure_ascii=False),flush=True)


if __name__=="__main__":
    if len(sys.argv)!=2 or sys.argv[1] not in ("subpixel_on","subpixel_off"):
        raise SystemExit("Usage: analyze_three_height_oak.py subpixel_on|subpixel_off")
    analyze(sys.argv[1])
