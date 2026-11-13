#!/usr/bin/env python3
"""Controlled OAK stereo-top vs tabletop plane benchmark. No robot/AI.

Camera service must be healthy and exclusive USB owner. This benchmark stops
the production unit, runs one OAK pipeline, and restores the original unit
in finally. Captures a small RAW16 depth replay archive to PRIVATE NVMe only.
IR DOT is always reset to OFF. This is research, not metrology validation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
from urllib.request import urlopen

import cv2
import depthai as dai
import numpy as np

PERCEPTION = Path(__file__).resolve().parent
sys.path.insert(0, str(PERCEPTION))
from height_planes import estimate_height_planes

OUT = Path("/srv/vision-data/staging/oak-height-planes-private-20261113")
ENV = Path("/srv/vision-data/tools/vision-camera-service/camera.env")
UNIT = "vision-oak-camera.service"
OBJECT_ROI = (410, 312, 510, 388)
TABLE_ROI = (280, 240, 640, 495)
PHASES = [("off_1",0.),("dot5",.05),("off_2",0.),
          ("dot10",.10),("off_3",0.)]
REFERENCE_MM = 50.4
PHASE_SECONDS = 11.
SETTLE_SECONDS = 2.5
WARMUP_SECONDS = 12.
MAX_TEMP_C = 62.
os.umask(0o077)
os.environ["XDG_RUNTIME_DIR"] = "/run/user/" + str(os.getuid())
os.environ["DBUS_SESSION_BUS_ADDRESS"] = (
    "unix:path=" + os.environ["XDG_RUNTIME_DIR"] + "/bus"
)


def sys_unit(*args):
    return subprocess.run(["systemctl","--user",*args],capture_output=True,
                          text=True,timeout=35)


def prod_url():
    values = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key,value=line.split("=",1)
            values[key.strip()]=value.strip().strip("'\"")
    return "http://" + values["VISION_BIND"] + ":" + values["VISION_PORT"]


def prod_status(url):
    with urlopen(url + "/api/status",timeout=3) as r:
        return json.load(r)


def wait_healthy(url, limit_s=40):
    deadline=time.monotonic()+limit_s
    while time.monotonic()<deadline:
        try:
            status=prod_status(url)
            if status.get("online") and status.get("usb")=="UsbSpeed.SUPER":
                return status
        except Exception:
            pass
        time.sleep(.3)
    return None


def summarize_phase(rows):
    valid=[r for r in rows if r.get("validity")=="EXPLORATORY_UNVERIFIED_PROJECTION"]
    result={"attempted":len(rows),"usable":len(valid),
            "pass_rate_pct":round(len(valid)/max(1,len(rows))*100,2)}
    for key in ("height_mm","object_roi_valid_pct","table_rmse_mm",
                "top_rmse_mm","top_table_normal_angle_deg",
                "top_inlier_count","top_candidate_points"):
        vals=[]
        for r in valid:
            x = r.get(key, r.get("quality",{}).get(key))
            if x is not None:
                vals.append(x)
        if vals:
            result[key+"_median"]=round(float(statistics.median(vals)),3)
            result[key+"_p05"]=round(float(np.percentile(vals,5)),3)
            result[key+"_p95"]=round(float(np.percentile(vals,95)),3)
            if key=="height_mm":
                result["height_mm_sample_std"]=(
                    round(float(np.std(vals,ddof=1)),3) if len(vals)>1 else None)
                result["error_vs_50p4_mm"]=round(result[key+"_median"]-REFERENCE_MM,3)
    reasons={}
    for row in rows:
        reason=row.get("reason")
        reasons[reason]=reasons.get(reason,0)+1
    result["reason_counts"]=reasons
    return result


def scene(result):
    with dai.Pipeline() as p:
        device=p.getDefaultDevice()
        speed=str(device.getUsbSpeed())
        if speed!="UsbSpeed.SUPER":
            raise RuntimeError("Camera did not negotiate USB3 SuperSpeed")
        if not device.getIrDrivers():
            raise RuntimeError("IR drivers unavailable; do not start pilot")
        cam=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        encoder=p.create(dai.node.VideoEncoder).build(
            cam.requestOutput((1920,1080),type=dai.ImgFrame.Type.NV12,fps=30),
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
        result={"reference_height_mm":REFERENCE_MM,
                "object_roi":OBJECT_ROI,"table_roi":TABLE_ROI,
                "usb":speed,"timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                "rows":[],"state":"STARTED",
                "geometry_frame":"stereo_left_rectified_optical",
                "ground_truth_used_by_estimator":False}
        running=False
        try:
            p.start()
            running=True
            if not device.setIrLaserDotProjectorIntensity(0.):
                raise RuntimeError("initial IR dot OFF failed")
            if not device.setIrFloodLightIntensity(0.):
                raise RuntimeError("initial IR flood OFF failed")
            print("WARMUP_START", flush=True)
            begin=time.monotonic()
            while time.monotonic()-begin < WARMUP_SECONDS:
                r=qr.tryGet();dep=qd.tryGet()
                if r is None and dep is None:
                    time.sleep(.003)
            print("WARMUP_COMPLETE", flush=True)
            base_K=None
            for name,intensity in PHASES:
                if not device.setIrLaserDotProjectorIntensity(intensity):
                    raise RuntimeError("IR dot request rejected: " + name)
                if not device.setIrFloodLightIntensity(0.):
                    raise RuntimeError("IR flood OFF failed")
                start=time.monotonic()
                metrics=[]
                depth_count=0
                rgb_count=0
                lost_depth_seq=0
                last_depth_seq=None
                example=None
                last_temp_at=0.
                active_K=None
                while time.monotonic()-start < PHASE_SECONDS:
                    rgb=qr.tryGet()
                    dep=qd.tryGet()
                    if rgb is not None:
                        rgb_count+=1
                    if dep is not None:
                        depth_count+=1
                        seq=dep.getSequenceNum()
                        if last_depth_seq is not None and seq>last_depth_seq+1:
                            lost_depth_seq+=seq-last_depth_seq-1
                        last_depth_seq=seq
                        if time.monotonic()-start > SETTLE_SECONDS and depth_count%8==0:
                            raw=dep.getFrame()
                            tr=dep.getTransformation()
                            if not tr.isValid() or list(tr.getSize())!=[1280,800]:
                                raise RuntimeError("Invalid rectified-left output geometry")
                            k=np.asarray(tr.getIntrinsicMatrix(),dtype=np.float64)
                            if base_K is not None and not np.allclose(k,base_K,atol=.05):
                                raise RuntimeError("Output K changed unexpectedly")
                            base_K=k.copy()
                            active_K=k.copy()
                            m=estimate_height_planes(
                                raw,k,OBJECT_ROI,TABLE_ROI)
                            metrics.append(m)
                            if example is None and len(metrics)>=5:
                                example=raw.copy()
                    now=time.monotonic()
                    if now-last_temp_at > 3:
                        last_temp_at=now
                        temp=float(device.getChipTemperature().average)
                        if temp >= MAX_TEMP_C:
                            raise RuntimeError("Temperature abort")
                    if rgb is None and dep is None:
                        time.sleep(.002)
                row={"phase":name,"ir_dot_pct":intensity*100,
                     "rgb_fps":round(rgb_count/PHASE_SECONDS,2),
                     "depth_fps":round(depth_count/PHASE_SECONDS,2),
                     "depth_sequence_gaps":lost_depth_seq,
                     "chip_temp_C":round(float(device.getChipTemperature().average),2),
                     "intrinsics":active_K.tolist() if active_K is not None else None,
                     "stats":summarize_phase(metrics),
                     "private_replay":None}
                if example is not None:
                    path=OUT / (name+"_depth_raw16.npy")
                    np.save(path,example,allow_pickle=False)
                    path.chmod(0o600)
                    row["private_replay"]=path.name
                result["rows"].append(row)
                print("PLANE_PHASE",json.dumps({
                    k:v for k,v in row.items() if k not in ("intrinsics","private_replay")
                }),flush=True)
                if (row["stats"]["attempted"]<16 or
                        row["stats"]["usable"]<10):
                    raise RuntimeError("Plane measurement not sufficiently reliable")
            result["state"]="COMPLETE"
        finally:
            try:
                result["ir_off_ack"]={
                    "dot":bool(device.setIrLaserDotProjectorIntensity(0.)),
                    "flood":bool(device.setIrFloodLightIntensity(0.)),
                }
            except Exception as exc:
                result["ir_off_error"]=type(exc).__name__
            if running and p.isRunning():
                p.stop();p.wait()
        return result


def main():
    OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
    url=prod_url()
    first=prod_status(url)
    if (not first.get("online") or first.get("usb")!="UsbSpeed.SUPER"
            or sys_unit("is-active",UNIT).stdout.strip()!="active"):
        raise RuntimeError("Production camera not healthy; refusing interruption")
    report={"baseline":{
        "online":first["online"],"rgb_fps":first["rgb_fps"],
        "depth_fps":first["depth_fps"],"chip_temp_C":first["chip_temp_C"]},
        "state":"STARTED"}
    stopped=False
    try:
        response=sys_unit("stop",UNIT)
        if response.returncode:
            raise RuntimeError("Stopping existing USB owner failed")
        stopped=True
        if sys_unit("is-active",UNIT).stdout.strip()=="active":
            raise RuntimeError("Production USB owner still active")
        scene(report)
    except BaseException as exc:
        report["state"]="TEST_ERROR"
        report["error_type"]=type(exc).__name__
        report["error_message"]=str(exc)[:160]
    finally:
        if stopped:
            status=sys_unit("start",UNIT)
            report["production_start_command_ok"]=status.returncode==0
            health=wait_healthy(url)
            report["production_restored"]=bool(health)
            if health:
                report["production_after"]={
                    "online":health["online"],"rgb_fps":health["rgb_fps"],
                    "depth_fps":health["depth_fps"],"usb":health["usb"],
                    "error":health["error"],"chip_temp_C":health["chip_temp_C"],
                }
        path=OUT/"height_planes_live_results.json"
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        path.chmod(0o600)
        print("HEIGHT_PLANES_SUMMARY",json.dumps({
            "state":report["state"],"error":report.get("error_message"),
            "production_restored":report.get("production_restored"),
            "ir_off_ack":report.get("ir_off_ack"),
            "phases":[{"phase":x["phase"],"rgb_fps":x["rgb_fps"],
                       "depth_fps":x["depth_fps"],"temperature":x["chip_temp_C"],
                       **x["stats"]} for x in report.get("rows",[])],
        },ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
