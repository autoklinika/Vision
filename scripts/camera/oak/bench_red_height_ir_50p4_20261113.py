#!/usr/bin/env python3
"""Bench geometric ABABA, RED reference 50.4 mm, non-production, no robot.

Depth ROI is MANUALLY localized in rectified-left optical image, not transferred
from RGB without calibration. Fixed camera/table orientation assumed for 90 s.
The reported errors are exploratory; factory optics not metric-verified.
Only aggregate metrics written, no photos or private frames persisted.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time

import cv2
import depthai as dai
import numpy as np

ROOT = Path("/srv/vision-data/staging/oak-calibration-check-20261113")
RESULT_PATH = ROOT / "height_ir_5_10_15_sweep_results.json"
SERVICE = "vision-oak-camera.service"
VENV = "/srv/vision-data/tools/vision-camera-service/venv/bin/python"
K = np.array([[796.5962524414,0,634.9946899414],
              [0,796.7395019531,378.5088500977],
              [0,0,1.]], dtype=np.float64)
REFERENCE_HEIGHT_MM = 50.4
TARGET_ROI = (410, 312, 510, 388)  # xyxy in depth image, NOT RGB
PHASES = [("off_1",0.),("dot05",.05),("off_2",0.),("dot10",.10),("off_3",0.),("dot15",.15),("off_4",0.)]
SECONDS_PER_PHASE = 12
SETTLE_SECONDS = 2.5
WARMUP_SECONDS = 18.0
TEMP_LIMIT_C = 62.
os.environ["XDG_RUNTIME_DIR"] = "/run/user/" + str(os.getuid())
os.environ["DBUS_SESSION_BUS_ADDRESS"] = ("unix:path=" + os.environ["XDG_RUNTIME_DIR"] + "/bus")
os.umask(0o077)


def unit(*args):
    return subprocess.run(["systemctl","--user",*args],
                          timeout=30, capture_output=True,text=True)

def private_prod_url():
    vals={}
    for line in Path("/srv/vision-data/tools/vision-camera-service/camera.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k,v=line.split("=",1)
            vals[k.strip()]=v.strip().strip("\"'")
    return "http://"+vals["VISION_BIND"]+":"+vals["VISION_PORT"]

def prod_status(url):
    from urllib.request import urlopen
    with urlopen(url+"/api/status",timeout=3) as r:
        return json.load(r)

def wait_prod(url, seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            st=prod_status(url)
            if st["online"] and st["usb"]=="UsbSpeed.SUPER":
                return st
        except Exception:
            pass
        time.sleep(.4)
    return None

def plane_fit(depth):
    """Seed once with global dominant plane; same geometric reference for all phases."""
    import sys
    sys.path.insert(0,"/srv/vision-data/staging/vision-oak-optics-20261113/scripts/perception")
    from perception_engine import deproject_depth,fit_plane
    pts,_,_=deproject_depth(depth,K,stride=4)
    plane=fit_plane(pts,threshold_m=.012,iterations=130,min_fraction=.40)
    if (plane is None or plane["inlier_fraction"] < .52
         or abs(plane["normal"][2])<.96 or plane["residual_rmse_m"]>.009):
        raise RuntimeError("No stable reference table plane")
    return plane


def measure(depth, plane):
    h,w=depth.shape
    if (h,w)!=(800,1280) or depth.dtype!=np.uint16:
        raise RuntimeError("Unexpected depth output dimensions")
    x0,y0,x1,y1=TARGET_ROI
    yy,xx=np.mgrid[y0:y1,x0:x1]
    zz=depth[y0:y1,x0:x1].astype(np.float64)*.001
    n=np.asarray(plane["normal"])
    hmm=1000*(n[0]*(xx-K[0,2])*zz/K[0,0]+
              n[1]*(yy-K[1,2])*zz/K[1,1]+
              n[2]*zz + plane["offset_m"])
    valid=(depth[y0:y1,x0:x1]>0)&(depth[y0:y1,x0:x1]<2500)
    # Nearby unchanged tabletop acts as a drift check (not a second model fit).
    ty,tx=np.mgrid[270:440,270:390]
    tdepth=depth[270:440,270:390].astype(np.float64)*.001
    table_h=1000*(n[0]*(tx-K[0,2])*tdepth/K[0,0]+
                  n[1]*(ty-K[1,2])*tdepth/K[1,1]+
                  n[2]*tdepth+plane["offset_m"])
    table_vals=table_h[(depth[270:440,270:390]>0)&
                       (depth[270:440,270:390]<2500)&
                       (np.abs(table_h)<35.)]
    table_offset=float(np.median(table_vals)) if len(table_vals)>500 else None
    top=valid&(hmm>=32)&(hmm<=80)
    # Pre-registered statistics: all valid top-candidate pixels in fixed ROI.
    vals=hmm[top]
    row={"depth_roi_valid_pct":round(100*float(valid.mean()),3),
         "valid_top_pixel_count":int(vals.size),
         "valid_top_pixel_fraction":round(float(top.mean()),4),
         "nearby_table_offset_mm":round(table_offset,3) if table_offset is not None else None,
         "nearby_table_pixel_count":len(table_vals)}
    if vals.size<200:
        row["state"]="NOT_READY_INSUFFICIENT_TARGET"
        return row
    q=np.percentile(vals,[10,25,50,75,90,95])
    for label,val in zip(("p10","p25","median","p75","p90","p95"),q):
        row["height_"+label+"_mm"]=round(float(val),3)
    # Primary estimator registered before live test: 75th percentile within
    # the fixed ROI, to reduce side/edge contamination. Report median too.
    row["estimated_height_mm"]=row["height_p75_mm"]
    row["error_vs_50p4_mm"]=round(row["estimated_height_mm"]-REFERENCE_HEIGHT_MM,3)
    row["state"]="MEASURED_EXPLORATORY"
    return row


def summarize(rows):
    data=[r for r in rows if r.get("state")=="MEASURED_EXPLORATORY"]
    if not data:
        return {"status":"NOT_READY","usable":0}
    result={"status":"PASS_EXPLORATORY","usable":len(data),
            "estimated_height_p75_median_mm":round(float(statistics.median(x["estimated_height_mm"] for x in data)),3),
            "estimated_height_p75_std_mm":round(float(np.std([x["estimated_height_mm"] for x in data],ddof=1)),3) if len(data)>1 else None,
            "height_median_pixel_median_mm":round(float(statistics.median(x["height_median_mm"] for x in data)),3),
            "target_valid_pixel_count_median":int(statistics.median(x["valid_top_pixel_count"] for x in data)),
            "depth_roi_valid_pct_median":round(float(statistics.median(x["depth_roi_valid_pct"] for x in data)),3)}
    result["error_vs_50p4_mm"]=round(result["estimated_height_p75_median_mm"]-REFERENCE_HEIGHT_MM,3)
    offsets=[x["nearby_table_offset_mm"] for x in data if x.get("nearby_table_offset_mm") is not None]
    result["table_offset_median_mm"]=round(float(statistics.median(offsets)),3) if offsets else None
    return result


def aruco_count(jpeg):
    frame=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_GRAYSCALE)
    if frame is None: return {}
    aruco=cv2.aruco
    dictionary=aruco.getPredefinedDictionary(aruco.DICT_5X5_50)
    corners,ids,_=aruco.ArucoDetector(dictionary,aruco.DetectorParameters()).detectMarkers(frame)
    count=len(ids) if ids is not None else 0
    try:
        board=aruco.CharucoBoard((5,7),.03,.015,dictionary)
        cc,ci,_,_=aruco.CharucoDetector(board).detectBoard(frame)
        charuco=len(ci) if ci is not None else 0
    except Exception:
        charuco=None
    return {"aruco_markers":count,"charuco_corners":charuco,
            "rgb_laplacian_var":round(float(cv2.Laplacian(frame,cv2.CV_64F).var()),2)}


def do_measurement(report):
    with dai.Pipeline() as p:
        device=p.getDefaultDevice()
        report["usb"]=str(device.getUsbSpeed())
        if report["usb"]!="UsbSpeed.SUPER": raise RuntimeError("Need USB3; no IR activated")
        report["ir_drivers_present"]=bool(device.getIrDrivers())
        if not report["ir_drivers_present"]: raise RuntimeError("No IR driver")
        rgb=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        encoder=p.create(dai.node.VideoEncoder).build(
            rgb.requestOutput((1920,1080),type=dai.ImgFrame.Type.NV12,fps=30),
            frameRate=30,profile=dai.VideoEncoderProperties.Profile.MJPEG,quality=80)
        qr=encoder.out.createOutputQueue(maxSize=4,blocking=False)
        left=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
        stereo=p.create(dai.node.StereoDepth)
        left.requestFullResolutionOutput(fps=30).link(stereo.left)
        right.requestFullResolutionOutput(fps=30).link(stereo.right)
        stereo.setRectification(True)
        stereo.setLeftRightCheck(True)
        stereo.setExtendedDisparity(False)
        qd=stereo.depth.createOutputQueue(maxSize=4,blocking=False)
        running=False
        try:
            p.start(); running=True
            if not device.setIrLaserDotProjectorIntensity(0.):
                raise RuntimeError("Could not reset dot before test")
            if not device.setIrFloodLightIntensity(0.):
                raise RuntimeError("Could not reset flood before test")
            print("SENSOR_WARMUP_START",WARMUP_SECONDS,flush=True)
            t_warm=time.monotonic()
            while time.monotonic()-t_warm < WARMUP_SECONDS:
                a=qr.tryGet()
                b=qd.tryGet()
                if a is None and b is None:
                    time.sleep(.004)
            print("SENSOR_WARMUP_DONE",flush=True)
            plane=None
            previous_rgb=None
            for label,irr in PHASES:
                ack=device.setIrLaserDotProjectorIntensity(float(irr))
                if not ack: raise RuntimeError("IR dot command failed for "+label)
                if not device.setIrFloodLightIntensity(0.):
                    raise RuntimeError("IR flood OFF command failed for "+label)
                t0=time.monotonic()
                row={"phase":label,"dot_command_pct":round(irr*100,1),
                     "settle_seconds":SETTLE_SECONDS,"duration_s":SECONDS_PER_PHASE,
                     "height_reference_mm":REFERENCE_HEIGHT_MM}
                frame_count=rgb_count=0
                samples=[]
                rgb_example=None
                frames_prev_seq=None
                depth_seq_missing=0
                while time.monotonic()-t0<SECONDS_PER_PHASE:
                    c=qr.tryGet(); q=qd.tryGet()
                    if c is not None:
                        rgb_count+=1
                        rgb_example=bytes(c.getData())
                    if q is not None:
                        frame_count+=1
                        seq=q.getSequenceNum()
                        if frames_prev_seq is not None and seq>frames_prev_seq+1:
                            depth_seq_missing+=seq-frames_prev_seq-1
                        frames_prev_seq=seq
                        now=time.monotonic()
                        if now-t0 >= SETTLE_SECONDS and frame_count%5==0:
                            raw=q.getFrame()
                            if plane is None:
                                plane=plane_fit(raw)
                                report["reference_plane"]=plane
                            samples.append(measure(raw,plane))
                            if len(samples) % 12 == 1:
                                temp=float(device.getChipTemperature().average)
                                if temp>=TEMP_LIMIT_C:
                                    raise RuntimeError(f"CHIP_TEMPERATURE_ABORT_{temp:.1f}C")
                    if c is None and q is None:time.sleep(.002)
                row["depth_fps"]=round(frame_count/SECONDS_PER_PHASE,2)
                row["rgb_fps"]=round(rgb_count/SECONDS_PER_PHASE,2)
                row["missing_depth_sequence"]=depth_seq_missing
                row["sample_count"]=len(samples)
                row["stats"]=summarize(samples)
                row["temperature_C"]=round(float(device.getChipTemperature().average),1)
                row["markers"]=aruco_count(rgb_example) if rgb_example else None
                # Keep complete scalar per-frame sample values for audit, no imagery.
                row["samples"]=samples
                report["rows"].append(row)
                # The depth-only height ROI does not depend on ChArUco matching.
                # Autofocus / lighting can temporarily reduce marker count;
                # record it as a warning rather than abort a valid depth A/B.
                row["board_quality_warning"] = bool(
                    (row["markers"] or {}).get("aruco_markers",0)<14)
                if row["stats"].get("usable",0)<18:
                    raise RuntimeError("not enough valid target height samples")
                print("HEIGHT_PHASE",json.dumps({k:v for k,v in row.items() if k!="samples"}),flush=True)
            report["state"]="ALL_PHASES_COMPLETE"
        finally:
            try:
                a=device.setIrLaserDotProjectorIntensity(0.)
                b=device.setIrFloodLightIntensity(0.)
                report["ir_off_ack"]={"dot":bool(a),"flood":bool(b)}
            except Exception as exc:
                report["ir_off_error"]=type(exc).__name__
            if running and p.isRunning():
                p.stop();p.wait()


def main():
    ROOT.mkdir(mode=0o700,exist_ok=True,parents=True)
    url=private_prod_url()
    initial=prod_status(url)
    if not initial.get("online") or initial.get("usb")!="UsbSpeed.SUPER":
        raise RuntimeError("Healthy Camera Service and USB3 required before test")
    if unit("is-active",SERVICE).stdout.strip()!="active":
        raise RuntimeError("Camera unit not active")
    report={"reference_height_mm":REFERENCE_HEIGHT_MM,"target_roi_rectified_left_xyxy":TARGET_ROI,
            "reference_note":"IR OFF/Dot 5/10/15 are exploratory; fixed depth ROI and warmup pre-registered before test.",
            "baseline":{"rgb_fps":initial["rgb_fps"],"depth_fps":initial["depth_fps"],
                        "usb":initial["usb"],"chip_temp_C":initial["chip_temp_C"]},
            "rows":[],"state":"STARTING"}
    stopped=False
    try:
        s=unit("stop",SERVICE)
        if s.returncode:raise RuntimeError("Could not stop production camera")
        stopped=True
        if unit("is-active",SERVICE).stdout.strip()=="active":
            raise RuntimeError("Two camera owners forbidden")
        do_measurement(report)
    except BaseException as exc:
        report["state"]="TEST_ERROR"
        report["exception"]=repr(exc)[:180]
        raise
    finally:
        if stopped:
            result=unit("start",SERVICE)
            report["production_start_command_ok"]=result.returncode==0
            st=wait_prod(url,40)
            report["production_restored_online"]=bool(st)
            if st:
                report["production_after"]={"rgb_fps":st["rgb_fps"],
                    "depth_fps":st["depth_fps"],"usb":st["usb"],
                    "error":st["error"],"chip_temp_C":st["chip_temp_C"]}
        RESULT_PATH.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        RESULT_PATH.chmod(0o600)
        print("HEIGHT_ABABA_SUMMARY",json.dumps({
            "state":report["state"],"ir_off_ack":report.get("ir_off_ack"),
            "production_restored":report.get("production_restored_online"),
            "phases":[{"phase":r["phase"],"fps":r["depth_fps"],"temp":r["temperature_C"],
                       "markers":r["markers"],"samples":r["sample_count"],
                       **r["stats"]} for r in report["rows"]]},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
