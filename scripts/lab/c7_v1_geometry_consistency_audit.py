#!/usr/bin/env python3
"""C7 V1: independent consistency checks from existing C5/C6 + current ETC3 captures.

No DepthAI, ROS2 or NERO access. Historical camera base geometry and fixed
mount image features are compared to detect changes that prevent approval
of absolute table XYZ. Requires OpenCV with SIFT, NumPy.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,math
from pathlib import Path
import cv2
import numpy as np

STATIONS={
"P1":"C5_P1_X600_Y250_VALIDONLY_20261120",
"P2":"C5_P2_X700_Y250_VALIDONLY_20261120",
"P3":"C5_P3_X700_Y350_VALIDONLY_20261120",
"P4":"C5_P4_X600_Y350_VALIDONLY_20261120",
"P5":"C5_P5_NOMINAL_X500_Y350_VALIDONLY_20261120",
}
STATIC_MOUNT_ROI=(250,210,535,640)
def read_rgb(path):
    img=cv2.imread(str(path),cv2.IMREAD_COLOR)
    if img is None or img.shape[:2]!=(1080,1920):
        raise ValueError(f"RGB image not 1920x1080: {path}")
    return img
def image_features(img,roi):
    mask=np.zeros(img.shape[:2],np.uint8)
    x0,y0,x1,y1=roi
    mask[y0:y1,x0:x1]=255
    detector=cv2.SIFT_create(nfeatures=1800)
    return detector.detectAndCompute(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY),mask)
def affine_align(source,target,roi=STATIC_MOUNT_ROI):
    keys1,d1=image_features(source,roi)
    keys2,d2=image_features(target,roi)
    if d1 is None or d2 is None:raise ValueError("No image features in static ROI")
    good=[m for m,n in cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1,d2,k=2) if m.distance<0.70*n.distance]
    if len(good)<18:raise ValueError(f"Too few feature matches {len(good)}")
    orig=np.array([keys1[m.queryIdx].pt for m in good],float)
    dest=np.array([keys2[m.trainIdx].pt for m in good],float)
    a,mask=cv2.estimateAffinePartial2D(orig,dest,method=cv2.RANSAC,ransacReprojThreshold=2.0,maxIters=5000,confidence=.999)
    if a is None:raise ValueError("Affine estimate failed")
    valid=mask.ravel().astype(bool)
    if valid.sum()<14:raise ValueError("Not enough inliers")
    pred=np.hstack([orig,np.ones((len(orig),1))])@a.T
    d=np.linalg.norm(pred[valid]-dest[valid],axis=1)
    return {"inliers":int(valid.sum()),"matches":len(good),
      "scale_ratio":round(math.hypot(float(a[0,0]),float(a[0,1])),7),
      "scale_change_pct":round((math.hypot(float(a[0,0]),float(a[0,1]))-1)*100,4),
      "rotation_deg":round(math.degrees(math.atan2(float(a[1,0]),float(a[0,0]))),4),
      "translation_px":[round(float(v),4) for v in a[:,2]],
      "inlier_median_reprojection_px":round(float(np.median(d)),4),
      "inlier_rmse_px":round(float(np.sqrt(np.mean(d*d))),4)}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--charuco-root",type=Path,required=True)
    ap.add_argument("--live",type=Path,required=True)
    ap.add_argument("--c5-summary",type=Path,required=True)
    ap.add_argument("--c6-summary",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    if a.output.exists():ap.error("Cannot overwrite audit")
    old=(a.charuco_root/STATIONS["P5"]/"p5valid_01.png")
    ref=read_rgb(old)
    last=read_rgb(a.live/"selected_rgb.jpg")
    by_live={}
    for n in range(1,6):
        p=a.live/f"rgb_{n:02d}.jpg"
        by_live[f"rgb_{n:02d}"]=affine_align(ref,read_rgb(p))
    by_station={}
    for key,folder in STATIONS.items():
        pic=sorted((a.charuco_root/folder).glob("*valid_*.png"))
        if not pic:
            pic=sorted((a.charuco_root/folder).glob("*.png"))
        if not pic:raise ValueError(f"Missing calibration RGB {key}")
        by_station[key]=affine_align(read_rgb(pic[0]),last)
        by_station[key]["ref_image"]=pic[0].name
    c5=json.loads(a.c5_summary.read_text());c6=json.loads(a.c6_summary.read_text())
    capture=json.loads((a.live/"capture_manifest.json").read_text())
    if c5["total_complete_valid_frames"]!=50 or capture["status"]!="REAL_RGB_AND_STEREO800_CAPTURED_UNVALIDATED_GEOMETRY":
        raise ValueError("Source configuration changed")
    if capture["config"]["depth"]!="1280x800_16UC1":
        raise ValueError("Depth source must remain true 800p")
    # Depth temporal repeatability, not absolute metrological accuracy.
    with np.load(a.live/"depth_frames_raw16.npz",allow_pickle=False) as f:
        depth=f["depth_mm"]
    if depth.shape!=(12,800,1280):raise ValueError("Wrong depth frame count")
    region=depth[:,310:490,540:760]
    median=[]
    valid_fraction=[]
    for frame in region:
        ok=(frame>300)&(frame<1400)
        valid_fraction.append(float(ok.mean()))
        median.append(float(np.median(frame[ok])) if ok.sum()>500 else None)
    if any(x is None for x in median):raise ValueError("Sparse central ROI")
    m=np.median(median)
    median_diff=np.abs(np.array(median)-m)
    biases={k:{"bias_mm":v["bias_mm"],"temporal_MAD_mm":v["temporal_MAD_mm"]}
            for k,v in c6["measurements"].items() if k.endswith("_IR_OFF")}
    scales=np.array([x["scale_change_pct"] for x in by_station.values()])
    selected=[by_live[f"rgb_{n:02d}"]["scale_change_pct"] for n in range(3,6)]
    status="SOURCES_CONSISTENT__ABSOLUTE_GEOMETRY_NOT_INDEPENDENTLY_VERIFIED"
    report={
      "status":status,"created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
      "source":"C5_ChArUco_50_frames + C6_IR_OFF_height_ground_truth + LIVE_ETC3_RGB5_depth12",
      "method":"SIFT feature matches on unchanged-looking NERO stationary mount/white supporting plate ROI, RANSAC similarity transform; not PCB feature matching",
      "mount_roi_rgb_xyxy":list(STATIC_MOUNT_ROI),
      "per_live_rgb_scale_vs_c5_P5":by_live,
      "per_c5_station_scale_vs_selected_live":by_station,
      "observed_old_to_live_scale_change_pct_median_across_stations":round(float(np.median(scales)),3),
      "old_to_live_scale_change_pct_min_max":[round(float(scales.min()),3),round(float(scales.max()),3)],
      "current_rgb_last3_scale_change_pct_min_max":[min(selected),max(selected)],
      "RGB_focus_or_camera_intrinsics_change_caused_exactly":"UNKNOWN (sensor autofocus, changed projection/crop, mechanical changes not independently separated)",
      "scale_ratio_not_equal_to_independent_camera_calibration":True,
      "C5_pnp_median_reprojection_rms_px":c5["all_reprojection_rms_px_median"],
      "C5_inter_station_optical_height_range_mm":c5["optical_height_range_across_five_position_medians_mm"],
      "C5_manual_board_XY_not_precision_survey":True,
      "temporal_depth_central_ROI":{"depth_ROI_xyxy":[540,310,760,490],
              "valid_fraction_min_max":[round(min(valid_fraction),4),round(max(valid_fraction),4)],
              "twelve_frame_median_depth_mm":[round(x,3) for x in median],
              "inter_frame_MAD_of_median_mm":round(float(np.median(median_diff)),3),
              "inter_frame_max_abs_delta_mm":round(float(np.max(median_diff)),3),
              "does_not_prove_absolute_depth_accuracy":True},
      "C6_IR_OFF_known_target_height_biases_mm":biases,
      "C6_reference_surface_dependent_bias":True,
      "source_sha256":{
          "C5":hashlib.sha256(a.c5_summary.read_bytes()).hexdigest(),
          "C6":hashlib.sha256(a.c6_summary.read_bytes()).hexdigest(),
          "live_RGB":hashlib.sha256((a.live/"selected_rgb.jpg").read_bytes()).hexdigest(),
          "live_raw_depth":hashlib.sha256((a.live/"depth_frames_raw16.npz").read_bytes()).hexdigest()},
      "geometry_approval_status":"NOT_APPROVED",
      "limits":[
        "Matching a visually stationary robot mount does not validate camera intrinsics or full-scene global translation/scale",
        "RGB live effective pixel scale differs from ChArUco calibration frames; previous C5 extrinsics cannot be assumed physically exact",
        "50 ChArUco frames have internal low reprojection residual but 5 placements are not independently surveyed",
        "Depth from C6 known reference heights IR OFF has surface-dependent systematic errors, not a universal offset",
        "Actual ETC3 PCB color hull includes some housing; full dimension not independently measured",
        "RGB-depth temporal alignment not verified and table-base transform only candidate"],
      "next_independent_physical_check":
        "Measure one identifiable ETC3 rigid point's X,Y on table and outer ECU dimensions X,Y with a ruler/caliper; compare with projected [666,417]mm and [265.5,225.3]mm before considering physical motion.",
      "physical_robot_motion_allowed":False
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("C7_GEOMETRY_CONSISTENCY_AUDIT",status)
    print("SIFT_SCALE_CHANGE_OLD_TO_LIVE_PCT",report["old_to_live_scale_change_pct_min_max"],
          "MEDIAN",report["observed_old_to_live_scale_change_pct_median_across_stations"])
    print("STEREO_TEMPORAL_ROI_MEDIAN_MAD_MM",report["temporal_depth_central_ROI"]["inter_frame_MAD_of_median_mm"])
    print("C6_REFERENCE_HEIGHT_BIASES_IR_OFF",biases)
    print("AUDIT_OUTPUT",a.output)

if __name__=="__main__":main()
