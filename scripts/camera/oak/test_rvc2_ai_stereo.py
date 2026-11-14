#!/usr/bin/env python3
"""20-second concurrent on-device object detection + stereo depth smoke test."""
import json
import time
import numpy as np
import depthai as dai
desc=dai.NNModelDescription()
desc.model="yolov6-nano"
desc.platform="RVC2"
with dai.Pipeline() as p:
    dev=p.getDefaultDevice()
    print("DEVICE",dev.getPlatformAsString(),"USB",dev.getUsbSpeed(),flush=True)
    cam=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    nn=p.create(dai.node.DetectionNetwork).build(cam,desc)
    qnn=nn.out.createOutputQueue()
    left=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    right=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
    stereo=p.create(dai.node.StereoDepth)
    left.requestFullResolutionOutput().link(stereo.left)
    right.requestFullResolutionOutput().link(stereo.right)
    stereo.setRectification(True)
    stereo.setLeftRightCheck(True)
    stereo.setExtendedDisparity(True)
    qdepth=stereo.depth.createOutputQueue()
    print("Starting combined NN + StereoDepth pipeline",flush=True)
    p.start()
    t0=time.monotonic()
    packets=0
    ratios=[]
    detections=0
    while time.monotonic()-t0<15:
        pkt=qnn.get()
        frame=qdepth.get().getFrame()
        packets+=1
        detections+=len(pkt.detections)
        if packets%10 == 0:
            valid=(frame>0)&(frame<5000)
            ratios.append(float(valid.mean()))
        if packets in (1,20,100):
            print("PAIRED_FRAMES",packets,flush=True)
    dt=time.monotonic()-t0
    print("NN_STEREO_RESULT",json.dumps({
        "result":"PASS" if packets>=20 else "INSUFFICIENT_FRAMES",
        "paired_packets":packets,
        "seconds":round(dt,2),
        "paired_fps":round(packets/dt,2),
        "depth_resolution":list(frame.shape),
        "depth_valid_fraction_mean_sampled":round(float(np.mean(ratios)),3) if ratios else None,
        "detected_objects_summed_over_frames":detections,
        "camera_model":"OAK-D-PRO-AF",
        "on_camera_ai":True,
        "robot_moves":False,
        "images_saved":False},ensure_ascii=False),flush=True)
    p.stop()
    p.wait()
