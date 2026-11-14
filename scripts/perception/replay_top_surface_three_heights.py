#!/usr/bin/env python3
"""Offline replay of automatic top-face segmentation for Vision OAK-D.

No USB, no DepthAI, no camera process or robot interfaces. Three coarse object
ROIs were chosen BEFORE previous 34/50.4/101mm capture and are identical for
all frames/settings; no TOP-FACE ROI is supplied. Reference heights are used
ONLY in this QA reporting layer, never by segment_top_surface().
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from top_surface import segment_top_surface

DATA=Path("/srv/vision-data/staging/oak-three-heights-private-20261113")
OUT=Path("/srv/vision-data/staging/vision-top-face-private-20261113")

# All coordinates are rectified-left depth pixels (not RGB pixels).
SCENE_ROIS={
    "beige_box": {
        "object":(475,170,625,330),"table":(350,70,755,425),
        "reference_mm":34.0,
    },
    "red_cylinder": {
        "object":(403,299,521,404),"table":(275,223,670,513),
        "reference_mm":50.4,
    },
    "white_red_box": {
        "object":(560,427,805,637),"table":(490,337,875,710),
        "reference_mm":101.0,
    },
}


def summarize(rows,reference):
    heights=[x["height_mm"] for x in rows if x["height_mm"] is not None]
    accepted=[x for x in rows if x["validity"]=="EXPLORATORY_UNVERIFIED_PROJECTION"]
    good=[x["height_mm"] for x in accepted]
    result={
        "frames":len(rows),
        "numeric_frames":len(heights),
        "geometry_accepted":len(good),
        "geometry_accepted_pct":round(100*len(good)/len(rows),1) if rows else 0,
        "geometry_rejected_reasons":{},
        "median_mm_all_numeric":round(float(np.median(heights)),3) if heights else None,
        "median_mm_accepted":round(float(np.median(good)),3) if good else None,
        "std_mm_accepted":round(float(np.std(good,ddof=1)),3) if len(good)>1 else None,
        "p05_p95_accepted_mm":[round(float(v),3) for v in np.quantile(good,[.05,.95])] if good else None,
        "reference_mm_QA_only":reference,
        "metrology_certified":False,
        "robot_ready":False,
    }
    for x in rows:
        if x["validity"]!="EXPLORATORY_UNVERIFIED_PROJECTION":
            key=x["reason"]
            result["geometry_rejected_reasons"][key]=result["geometry_rejected_reasons"].get(key,0)+1
    if good:
        result["median_bias_mm_accepted"]=round(float(np.median(good)-reference),3)
    else:
        result["median_bias_mm_accepted"]=None

    # NOTE: One short-correlated capture does not certify metrology.
    passes=(len(good)>=round(.95*len(rows))
            and len(good)>=15
            and abs(np.median(good)-reference)<=1.0
            and float(np.std(good,ddof=1))<=1.0
            and max(abs(np.quantile(good,.05)-reference),
                    abs(np.quantile(good,.95)-reference))<=2.0)
    result["research_gate"]="RESEARCH_GATE_PASS_ONLY" if passes else "RESEARCH_GATE_FAIL"
    return result


def run():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=OUT)
    a=ap.parse_args()
    os.umask(0o077)
    a.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    record={
        "method":"automatic_mode_guided_top_plateau_connected_component",
        "depth_frame":"stereo_left_rectified_optical",
        "input":"private real RAW16 replay",
        "top_face_roi_manual":False,
        "coarse_roi_preselected_before_capture":True,
        "reference_used_by_estimator":False,
        "hardware_touched":False,
        "metrology_certified":False,
        "robot_ready":False,
        "phases":[],
    }
    private_rows={}
    for mode in ("subpixel_on","subpixel_off"):
        for phase in ("off_before","dot5","off_after"):
            p=DATA/mode/(phase+"_frames.npz")
            with np.load(p,allow_pickle=False) as f:
                frames=f["depth_mm"]
                K=f["K"]
                n_frames=len(frames)
                cases={name:[] for name in SCENE_ROIS}
                for idx,frame in enumerate(frames):
                    for name,roi in SCENE_ROIS.items():
                        measure=segment_top_surface(
                            frame,K,roi["object"],roi["table"])
                        row=dict(measure.metadata)
                        # mask is deliberately not added to the JSON result
                        cases[name].append(row)
            detail={"mode":mode,"phase":phase,"frame_count":n_frames,"targets":{}}
            for name,roi in SCENE_ROIS.items():
                detail["targets"][name]=summarize(
                    cases[name],roi["reference_mm"])
            record["phases"].append(detail)
            private_rows[mode+"_"+phase]=cases
            print("TOP_SURFACE_REPLAY "+json.dumps(detail,ensure_ascii=False),flush=True)
    for filename,obj in (
        ("top_surface_aggregate_private.json",record),
        ("top_surface_per_frame_private.json",private_rows),
    ):
        p=a.output/filename
        p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n")
        p.chmod(0o600)
    print("AUTO_TOP_SURFACE_FULL_REPLAY_COMPLETE",flush=True)


if __name__=="__main__":
    run()
