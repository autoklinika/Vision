#!/usr/bin/env python3
"""Controlled IR dot/flood + stereo + optional on-camera YOLOv6 Nano benchmark.

Modes tested in one USB3 session. No robot commands, saved images, flash, EEPROM changes.
Attempts to reset emitters to OFF in finally; if USB disconnects this call cannot reach device. Device reboots to default IR OFF.
"""
import argparse
import json
import statistics
import time
import depthai as dai
import numpy as np

ap=argparse.ArgumentParser()
ap.add_argument("--ai",action="store_true")
ap.add_argument("--off-only",action="store_true",help="Only passive stereo baseline, never turn on IR")
ap.add_argument("--enable-ir",action="store_true",help="Explicit opt-in to IR emitter testing after power review")
ap.add_argument("--duration",type=float,default=7.0)
ap.add_argument("--warmup",type=float,default=1.5)
args=ap.parse_args()

PHASES=[("off_initial",0.0,0.0),
        ("dot_15pct",0.15,0.0),
        ("dot_30pct",0.30,0.0),
        ("flood_20pct",0.0,0.20),
        ("combined_20pct",0.20,0.20),
        ("off_final",0.0,0.0)]
if args.off_only or not args.enable_ir:
    PHASES=[PHASES[0]]
if args.ai and args.enable_ir:
    raise SystemExit("SAFETY_GATE: IR+AI test suspended until external camera power is verified")

with dai.Pipeline() as pipeline:
    device=pipeline.getDefaultDevice()
    print("USB",str(device.getUsbSpeed()),"MODEL",device.getPlatformAsString(),flush=True)
    drivers=device.getIrDrivers()
    print("IR_DRIVERS",repr(drivers),flush=True)
    if not drivers:
        print("IR_DRIVER_NOT_FOUND: will only run baseline",flush=True)
        PHASES=[PHASES[0]]
    left=pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    right=pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
    stereo=pipeline.create(dai.node.StereoDepth)
    left.requestFullResolutionOutput().link(stereo.left)
    right.requestFullResolutionOutput().link(stereo.right)
    stereo.setRectification(True)
    stereo.setLeftRightCheck(True)
    stereo.setExtendedDisparity(True)
    depth_q=stereo.depth.createOutputQueue(maxSize=8,blocking=False)
    nnq=None
    if args.ai:
        desc=dai.NNModelDescription()
        desc.model="yolov6-nano"
        desc.platform="RVC2"
        cam=pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        net=pipeline.create(dai.node.DetectionNetwork).build(cam,desc)
        nnq=net.out.createOutputQueue(maxSize=8,blocking=False)
    result=[]
    try:
        pipeline.start()
        assert device.setIrLaserDotProjectorIntensity(0.0)
        assert device.setIrFloodLightIntensity(0.0)
        for label,dot,flood in PHASES:
            # Reset previous phase, then apply new emitter intensity.
            ok_dot=bool(device.setIrLaserDotProjectorIntensity(dot))
            ok_flood=bool(device.setIrFloodLightIntensity(flood))
            if not (ok_dot and ok_flood):
                print("EMITTER_SET_FAILED",label,ok_dot,ok_flood,flush=True)
                raise RuntimeError("IR emitter control returned false")
            settle=time.monotonic()+args.warmup
            while time.monotonic()<settle:
                depth_q.tryGet()
                if nnq: nnq.tryGet()
                time.sleep(0.03)
            t0=time.monotonic()
            depth_frames=0
            nn_frames=0
            det_count=0
            valid_full=[]
            valid_center=[]
            depth_median=[]
            temps=[]
            while time.monotonic()-t0<args.duration:
                df=depth_q.tryGet()
                nf=nnq.tryGet() if nnq else None
                if df is not None:
                    depth_frames+=1
                    if depth_frames%3==1:
                        depth=df.getFrame()
                        good=(depth>0)&(depth<5000)
                        h,w=depth.shape
                        roi=depth[h//4:3*h//4,w//4:3*w//4]
                        valid_roi=(roi>0)&(roi<5000)
                        valid_full.append(float(good.mean()))
                        valid_center.append(float(valid_roi.mean()))
                        if valid_roi.any():
                            depth_median.append(float(np.median(roi[valid_roi])))
                if nf is not None:
                    nn_frames+=1
                    det_count+=len(nf.detections)
                if (depth_frames+nn_frames)%150==1:
                    pass
                if not df and not nf:
                    time.sleep(0.002)
            elapsed=time.monotonic()-t0
            try:
                temp=device.getChipTemperature()
                temp_avg=round(float(temp.average),1)
            except Exception:
                temp_avg=None
            row={
                "phase":label,"dot":dot,"flood":flood,"ir_control_ack":ok_dot and ok_flood,
                "stereo_frames":depth_frames,"stereo_fps":round(depth_frames/elapsed,2),
                "nn_frames":nn_frames if args.ai else None,
                "nn_fps":round(nn_frames/elapsed,2) if args.ai else None,
                "detections_sum":det_count if args.ai else None,
                "full_valid_pct":round(100*statistics.mean(valid_full),2) if valid_full else None,
                "center_valid_pct":round(100*statistics.mean(valid_center),2) if valid_center else None,
                "center_median_mm":round(statistics.median(depth_median)) if depth_median else None,
                "chip_temp_C":temp_avg,"duration_seconds":round(elapsed,2)
            }
            result.append(row)
            print("PHASE_RESULT",json.dumps(row,ensure_ascii=False),flush=True)
        print("BENCHMARK_COMPLETE",json.dumps({"ai":args.ai,"usb_speed":str(device.getUsbSpeed()),"ir_drivers":drivers,"results":result},ensure_ascii=False),flush=True)
    finally:
        print("EMITTER_SHUTDOWN",flush=True)
        try:
            print("DOT_OFF",bool(device.setIrLaserDotProjectorIntensity(0.0)),
                  "FLOOD_OFF",bool(device.setIrFloodLightIntensity(0.0)),flush=True)
        except Exception as ex:
            print("EMITTER_SHUTDOWN_ERROR",repr(ex),flush=True)
        if pipeline.isRunning():
            pipeline.stop()
            pipeline.wait()
