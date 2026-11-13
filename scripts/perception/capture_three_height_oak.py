#!/usr/bin/env python3
"""Controlled three-height acquisition: DepthAI StereoDepth, private RAW16 replay.

Exactly one camera USB owner. Unit preflight, stop, direct DepthAI pipeline,
emitter shutdown in finally, then original production unit restore + health.
No NERO/ROS2/AI or EEPROM writes. Test flags not used by production unit.
No photos or private images in GitHub.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

import cv2
import depthai as dai
import numpy as np

OUT = Path("/srv/vision-data/staging/oak-three-heights-private-20261113")
UNIT = "vision-oak-camera.service"
ENV = Path("/srv/vision-data/tools/vision-camera-service/camera.env")
os.umask(0o077)
os.environ["XDG_RUNTIME_DIR"]="/run/user/"+str(os.getuid())
os.environ["DBUS_SESSION_BUS_ADDRESS"]="unix:path="+os.environ["XDG_RUNTIME_DIR"]+"/bus"

def systemctl(*args):
    return subprocess.run(["systemctl","--user",*args],capture_output=True,text=True,timeout=35)

def url():
    env={}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k,v=line.split("=",1);env[k.strip()]=v.strip().strip("'\"")
    return "http://"+env["VISION_BIND"]+":"+env["VISION_PORT"]

def health(base):
    try:
        with urlopen(base+"/api/status",timeout=3) as response:
            return json.load(response)
    except Exception:
        return None

def wait_online(base, timeout=40):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        stat=health(base)
        if stat and stat.get("online") and stat.get("usb")=="UsbSpeed.SUPER":
            return stat
        time.sleep(.35)
    return None

def capture(subpixel: bool, report: dict):
    label="subpixel_on" if subpixel else "subpixel_off"
    folder=OUT/label
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    phases=[("off_before",0.),("dot5",.05),("off_after",0.)]
    with dai.Pipeline() as p:
        dev=p.getDefaultDevice()
        if str(dev.getUsbSpeed())!="UsbSpeed.SUPER":
            raise RuntimeError("No USB3 SuperSpeed")
        if not dev.getIrDrivers():
            raise RuntimeError("No available IR drivers")
        rgb=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        enc=p.create(dai.node.VideoEncoder).build(
            rgb.requestOutput((1920,1080),type=dai.ImgFrame.Type.NV12,fps=30),
            frameRate=30,profile=dai.VideoEncoderProperties.Profile.MJPEG,quality=80)
        qr=enc.out.createOutputQueue(maxSize=4,blocking=False)
        left=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
        stereo=p.create(dai.node.StereoDepth)
        left.requestFullResolutionOutput(fps=30).link(stereo.left)
        right.requestFullResolutionOutput(fps=30).link(stereo.right)
        stereo.setRectification(True)
        stereo.setLeftRightCheck(True)
        stereo.setExtendedDisparity(False)
        stereo.setSubpixel(subpixel)
        qd=stereo.depth.createOutputQueue(maxSize=4,blocking=False)
        started=False
        try:
            p.start();started=True
            if not dev.setIrLaserDotProjectorIntensity(0.):
                raise RuntimeError("IR dot off preflight FAILED")
            if not dev.setIrFloodLightIntensity(0.):
                raise RuntimeError("IR flood off preflight FAILED")
            warming=time.monotonic()
            while time.monotonic()-warming<13.0:
                r=qr.tryGet();dep=qd.tryGet()
                if r is None and dep is None:
                    time.sleep(.003)
            print("THREE_HEIGHT_WARMUP_DONE",label,flush=True)
            optical_K=None
            for phase,power in phases:
                if not dev.setIrLaserDotProjectorIntensity(power):
                    raise RuntimeError("Could not set IR DOT")
                if not dev.setIrFloodLightIntensity(0.):
                    raise RuntimeError("Could not force IR flood OFF")
                t0=time.monotonic()
                rgb_n=depth_n=0
                missed_seq=0
                last_seq=None
                samples=[]
                timestamps=[]
                next_sample=t0+3.0
                last_temp=0.
                temp_max=None
                while time.monotonic()-t0<16.:
                    r=qr.tryGet()
                    dep=qd.tryGet()
                    if r is not None:
                        rgb_n+=1
                    if dep is not None:
                        depth_n+=1
                        seq=dep.getSequenceNum()
                        if last_seq is not None and seq>last_seq+1:
                            missed_seq+=seq-last_seq-1
                        last_seq=seq
                        now=time.monotonic()
                        if now>=next_sample:
                            frame=dep.getFrame()
                            if frame.dtype!=np.uint16 or frame.shape!=(800,1280):
                                raise RuntimeError("Unexpected depth layout")
                            tr=dep.getTransformation()
                            if not tr.isValid() or list(tr.getSize())!=[1280,800]:
                                raise RuntimeError("Depth output transform not valid")
                            k=np.asarray(tr.getIntrinsicMatrix(),dtype=np.float64)
                            if optical_K is not None and not np.allclose(k,optical_K,atol=.05):
                                raise RuntimeError("Depth K drifted between phases")
                            optical_K=k
                            samples.append(frame.copy())
                            timestamps.append(int(dep.getTimestampDevice().total_seconds()*1e9))
                            next_sample=now+.50
                    if time.monotonic()-last_temp>3.0:
                        last_temp=time.monotonic()
                        temp=float(dev.getChipTemperature().average)
                        temp_max=max(temp_max or temp,temp)
                        if temp>=62.:
                            raise RuntimeError("Temperature abort")
                    if r is None and dep is None:
                        time.sleep(.002)
                if len(samples)<12:
                    raise RuntimeError("Insufficient RAW16 depth frames")
                # lossless non-pickle .npz private. On-demand sequential output.
                private=folder/(phase+"_frames.npz")
                np.savez_compressed(private,
                    depth_mm=np.stack(samples),
                    device_timestamp_ns=np.asarray(timestamps,dtype=np.int64),
                    K=optical_K)
                private.chmod(0o600)
                row={"phase":phase,"dot_pct":power*100,
                     "rgb_fps":round(rgb_n/16.,2),
                     "depth_fps":round(depth_n/16.,2),
                     "depth_sequence_gaps":missed_seq,
                     "frames_saved":len(samples),
                     "temp_max_c":round(temp_max,2),
                     "private_file":private.name}
                report["phases"].append(row)
                print("THREE_HEIGHT_CAPTURE",label,phase,json.dumps({
                   k:v for k,v in row.items() if k!="private_file"}),flush=True)
            report["state"]="CAPTURE_PASS"
        finally:
            try:
                report["ir_off_ack"]={
                    "dot":bool(dev.setIrLaserDotProjectorIntensity(0.)),
                    "flood":bool(dev.setIrFloodLightIntensity(0.)),
                }
            except Exception as exc:
                report["ir_off_error"]=type(exc).__name__
            if started and p.isRunning():
                p.stop();p.wait()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--subpixel",action="store_true")
    args=parser.parse_args()
    label="subpixel_on" if args.subpixel else "subpixel_off"
    OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
    base=url()
    st=health(base)
    if (not st or not st.get("online") or
            st.get("usb")!="UsbSpeed.SUPER" or
            systemctl("is-active",UNIT).stdout.strip()!="active"):
        raise RuntimeError("Production USB owner not healthy; refusing test")
    report={"session":label,"subpixel":args.subpixel,
            "reference_heights_mm":{"beige":34.,"red_cylinder":50.4,"white_red_box":101.},
            "state":"STARTED",
            "baseline":{"rgb_fps":st["rgb_fps"],"depth_fps":st["depth_fps"],
                        "usb":st["usb"],"online":st["online"]},
            "phases":[]}
    stopped=False
    try:
        result=systemctl("stop",UNIT)
        if result.returncode:
            raise RuntimeError("Could not stop production camera service")
        stopped=True
        if systemctl("is-active",UNIT).stdout.strip()=="active":
            raise RuntimeError("Two USB owners would conflict")
        capture(args.subpixel,report)
    except BaseException as exc:
        report["state"]="CAPTURE_FAIL"
        report["error"]=type(exc).__name__+": "+str(exc)[:150]
    finally:
        if stopped:
            sr=systemctl("start",UNIT)
            report["production_start_command_ok"]=sr.returncode==0
            restored=wait_online(base)
            report["production_restored"]=bool(restored)
            if restored:
                report["production_after"]={
                    "online":restored["online"],"usb":restored["usb"],
                    "rgb_fps":restored["rgb_fps"],"depth_fps":restored["depth_fps"],
                    "error":restored["error"]}
        folder=OUT/label
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        summary=folder/"capture_result.json"
        summary.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        summary.chmod(0o600)
        print("THREE_HEIGHT_CAPTURE_RESULT",json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
