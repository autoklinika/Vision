#!/usr/bin/env python3
"""Offline ChArUco 2D/PnP consistency: independently measured chess square 29.5 mm.

PnP uses factory-derived RGB intrinsics and an assumed ArUco marker ratio,
therefore pose is exploratory. NEVER interpret camera RGB pose as rectified
stereo or NERO coordinates. No device/USB connections, no image export.
"""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np

IMAGE = Path("/srv/vision-data/staging/oak-calibration-check-20261113/current_rgb.jpg")
OPTICS = Path("/srv/vision-data/staging/oak-optics-live-20261113/results_survey.json")
SQUARE_MM = 29.5
BOARD_SQUARES = (5, 7)
MARKER_LENGTH_RATIO_ASSUMED = 0.5

def verify(image, k, square_mm=SQUARE_MM):
    if image is None or not np.isfinite(square_mm) or square_mm <= 0:
        raise ValueError("Need image and positive real chess-square length")
    ar = cv2.aruco
    dictionary=ar.getPredefinedDictionary(ar.DICT_5X5_50)
    board=ar.CharucoBoard(BOARD_SQUARES,square_mm/1000,
                          square_mm*MARKER_LENGTH_RATIO_ASSUMED/1000,dictionary)
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    corners, ids, marker_corners, marker_ids=ar.CharucoDetector(board).detectBoard(gray)
    n_corners=len(ids) if ids is not None else 0
    n_markers=len(marker_ids) if marker_ids is not None else 0
    out={"square_size_measured_mm":square_mm,
         "board_squares_xy":list(BOARD_SQUARES),
         "board_outer_nominal_mm":[round(BOARD_SQUARES[0]*square_mm,2),
                                   round(BOARD_SQUARES[1]*square_mm,2)],
         "marker_length_ratio_assumed":MARKER_LENGTH_RATIO_ASSUMED,
         "marker_length_measured":False,
         "rgb_markers_detected":n_markers,"charuco_corners_detected":n_corners,
         "pose_frame":"rgb_optical",
         "depth_alignment":"UNVERIFIED_NOT_ALIGNED",
         "robot_base":"UNAVAILABLE",
         "table_frame":"UNAVAILABLE",
         "metric_accuracy_certified":False}
    if n_corners < 12:
        out["status"]="NOT_READY_INSUFFICIENT_CORNERS"
        return out
    # Homography does not use RGB K and verifies 2D planar consistency only.
    points_board=np.asarray(board.getChessboardCorners(),dtype=np.float64)[ids.flatten(),:]
    points_img=np.asarray(corners,dtype=np.float64).reshape(-1,2)
    mat, mask = cv2.findHomography(points_board[:,:2], points_img,cv2.RANSAC,2.0)
    if mat is None:
        out["status"]="HOMOGRAPHY_FAIL"
        return out
    projections=cv2.perspectiveTransform(points_board[:,:2].astype("float32").reshape(-1,1,2),mat).reshape(-1,2)
    reproj=np.linalg.norm(projections-points_img,axis=1)
    out["homography_rms_px"]=round(float(np.sqrt(np.mean(reproj*reproj))),3)
    out["homography_p95_px"]=round(float(np.percentile(reproj,95)),3)
    out["homography_inliers"]=int(mask.sum())
    # PnP is only a consistency diagnostic of the K, not a calibration/metric proof.
    K=np.asarray(k,dtype=np.float64)
    if K.shape != (3,3) or K[0,0]<=0 or K[1,1]<=0 or not np.isfinite(K).all():
        out["status"]="INVALID_K"
        return out
    ok,rvec,tvec,inliers=cv2.solvePnPRansac(points_board,points_img,K,None,
                 iterationsCount=250,reprojectionError=3.0,confidence=.99)
    if not ok:
        out["status"]="PNP_FAIL"
        return out
    if len(inliers) >= 8:
        rvec,tvec=cv2.solvePnPRefineLM(points_board[inliers.flatten()],
                                       points_img[inliers.flatten()],
                                       K,None,rvec,tvec)
    projected,_=cv2.projectPoints(points_board,rvec,tvec,K,None)
    err=np.linalg.norm(projected.reshape(-1,2)-points_img,axis=1)
    R,_=cv2.Rodrigues(rvec)
    board_normal=R[:,2]
    inclination=np.degrees(np.arccos(np.clip(abs(board_normal[2]),0,1)))
    out.update({
       "status":"RGB_PLANAR_POSE_EXPLORATORY",
       "pnp_inliers":int(len(inliers)),
       "pnp_rms_reprojection_px":round(float(np.sqrt(np.mean(err**2))),3),
       "pnp_p95_reprojection_px":round(float(np.percentile(err,95)),3),
       "board_origin_in_rgb_optical_m":np.asarray(tvec).flatten().round(6).tolist(),
       "board_normal_in_rgb_optical":board_normal.round(5).tolist(),
       "board_inclination_relative_rgb_view_axis_deg":round(float(inclination),3),
       "distance_rgb_optical_origin_to_board_origin_m":round(float(np.linalg.norm(tvec)),4),
       "intrinsics_source":"depthai_imgframe_transformation_from_prior_successful_acquisition",
       "distortion_model":"ASSUMED_RECTIFIED_RGB_ZERO_DISTORTION_NOT_VERIFIED",
       "physical_print_measurement_source":"user_measured_square_side_29p5mm",
       "depth_registration":"NOT_COMPUTED_NO_CROSS_CAMERA_EXTRINSICS",
    })
    return out

def main():
    rgb=cv2.imread(str(IMAGE))
    metadata=json.loads(OPTICS.read_text())
    options=metadata["phases"][0]["optics"]["rgb_transform"]
    result=verify(rgb,options["K"])
    print(json.dumps(result,indent=2,ensure_ascii=False))
    path=Path("/srv/vision-data/staging/oak-calibration-check-20261113/charuco_29p5_scale_results.json")
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    path.chmod(0o600)
if __name__=="__main__":
    main()
