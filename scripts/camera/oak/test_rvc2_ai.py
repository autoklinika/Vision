#!/usr/bin/env python3
"""Verify on-device NN using Luxonis RVC2 YOLOv6-nano. NO robot actions; does not store images."""
import collections
import json
import time
import depthai as dai

print("DepthAI", dai.__version__, flush=True)
desc = dai.NNModelDescription()
desc.model = "yolov6-nano"
desc.platform = "RVC2"
with dai.Pipeline() as pipeline:
    device = pipeline.getDefaultDevice()
    print("Device platform", device.getPlatformAsString(), flush=True)
    print("USB speed", device.getUsbSpeed(), flush=True)
    camera = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    detection = pipeline.create(dai.node.DetectionNetwork).build(camera, desc)
    labels = detection.getClasses() or []
    print("Network built", len(labels), "labels", flush=True)
    output = detection.out.createOutputQueue()
    print("Starting on-camera neural inference", flush=True)
    pipeline.start()
    print("PIPELINE_RUNNING",pipeline.isRunning(), flush=True)
    end = time.monotonic()+20.0
    t0 = time.monotonic()
    cnt=0
    total_dets=0
    confs=[]
    classes=collections.Counter()
    first=0
    while time.monotonic() < end:
        packet = output.get()
        if packet is None:
            continue
        cnt += 1
        if first==0: first=time.monotonic()
        dets = packet.detections
        total_dets += len(dets)
        for dt in dets:
            label=labels[dt.label] if dt.label<len(labels) else str(dt.label)
            classes[label]+=1
            confs.append(float(dt.confidence))
        if cnt in (1,10,30,60,120,180):
            print("NN_RESULT",cnt,"detections",len(dets),flush=True)
    elapsed=time.monotonic()-t0
    result={"result":"AI_ON_RVC2_PASS" if cnt>=10 else "AI_FRAMES_TOO_FEW",
            "model":"yolov6-nano","platform":"RVC2","model_execution":"OAK NeuralNetwork + on-device DetectionParser",
            "output_packets":cnt,"test_wall_seconds":round(elapsed,2),
            "effective_nn_fps":round(cnt/elapsed,2) if elapsed>0 else 0,
            "total_detections_over_frames":total_dets,
            "detection_classes_by_frame":dict(classes.most_common(10)),
            "highest_confidence":round(max(confs),3) if confs else None,
            "no_images_saved":True,"robot_control":False}
    print("NN_TEST_RESULT",json.dumps(result,ensure_ascii=False),flush=True)
    pipeline.stop()
    pipeline.wait()
