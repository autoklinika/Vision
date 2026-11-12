#!/usr/bin/env python3
"""Vision OAK-D Pro AF camera service: single-owner RGB MJPEG + 16-bit depth.

Runs on Ventuno Q / DepthAI 3.12.0. No on-camera NN, IR, robot, or disk recording.
"""
from __future__ import annotations

import argparse
from collections import deque
import fcntl
import json
import logging
import os
import resource
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from camera_sync import (FramePacket, RgbdSynchronizer, bundle_metadata,
                         encode_replay_npz, read_optics_readonly)

LOG = logging.getLogger("vision.camera")
PAGE = Path(__file__).with_name("camera_service_prod.html")
LOCK_PATH = "/tmp/vision-oak-browser-preview.lock"
FRESH_SECONDS = 5.0
PROFILES = {
    "balanced": {"rgb_size": (1920, 1080), "rgb_fps": 30, "depth_fps": 30,
                 "preview_fps": 12, "extended": False},
    "detail": {"rgb_size": (3840, 2160), "rgb_fps": 20, "depth_fps": 20,
               "preview_fps": 10, "extended": False},
    "near": {"rgb_size": (1920, 1080), "rgb_fps": 15, "depth_fps": 15,
             "preview_fps": 10, "extended": True},
}


class State:
    def __init__(self, profile: str):
        self.cv = threading.Condition()
        self.profile = profile
        self.config = PROFILES[profile]
        self.frames = {"rgb": None, "depth": None}
        self.seqs = {"rgb": 0, "depth": 0}
        self.times = {"rgb": 0.0, "depth": 0.0}
        self.received = {"rgb": 0, "depth": 0}
        self.fps = {"rgb": 0.0, "depth": 0.0}
        self.frame_ticks = {"rgb": deque(maxlen=140), "depth": deque(maxlen=140)}
        self.depth = None
        self.depth_time = 0.0
        self.depth_shape = None
        self.valid_pct = None
        self.center_mm = None
        self.usb = "not started"
        self.chip_C = None
        self.running = False
        self.error = None
        self.started = time.monotonic()
        self.sync = RgbdSynchronizer()
        self.calibration = {"state": "UNAVAILABLE", "depth_projection_status": "UNAVAILABLE"}
        self.client_semaphore = threading.BoundedSemaphore(10)

    def start(self, usb: str):
        with self.cv:
            self.sync.reset()
            self.usb = usb
            self.running = True
            self.error = None
            self.cv.notify_all()

    def fail(self, why: str):
        with self.cv:
            self.error = why[:240]
            self.running = False
            self.cv.notify_all()

    def stop(self):
        with self.cv:
            self.running = False
            self.cv.notify_all()

    def _tick(self, kind: str, now: float):
        stamps = self.frame_ticks[kind]
        stamps.append(now)
        while len(stamps) > 2 and stamps[0] < now - 4.0:
            stamps.popleft()
        if len(stamps) > 1 and stamps[-1] > stamps[0]:
            self.fps[kind] = (len(stamps) - 1) / (stamps[-1] - stamps[0])

    def publish(self, kind: str, jpeg: bytes):
        if kind not in self.frames or not jpeg:
            raise ValueError("invalid frame")
        now = time.monotonic()
        with self.cv:
            self.frames[kind] = bytes(jpeg)
            self.seqs[kind] += 1
            self.times[kind] = now
            if kind == "rgb":
                self._tick("rgb", now)
            self.cv.notify_all()

    def publish_depth(self, depth):
        now = time.monotonic()
        with self.cv:
            self.depth = depth
            self.depth_shape = tuple(depth.shape)
            self.depth_time = now
            self.received["depth"] += 1
            self._tick("depth", now)
            self.cv.notify_all()

    def next_frame(self, kind: str, after: int, timeout: float = 4.0):
        with self.cv:
            self.cv.wait_for(
                lambda: self.seqs[kind] > after or self.error is not None
                or not self.running,
                timeout=timeout,
            )
            if self.running and self.error is None and self.seqs[kind] > after:
                return self.seqs[kind], self.frames[kind]
            return None

    def snapshot(self, kind: str):
        with self.cv:
            return self.frames[kind]

    def raw_depth(self):
        with self.cv:
            return self.depth.copy() if self.depth is not None else None

    def ingest_packet(self, kind, payload, sequence, device_timestamp_ns,
                      width, height, host_received_ns=None):
        host_received_ns = (time.monotonic_ns() if host_received_ns is None
                            else host_received_ns)
        with self.cv:
            if not self.running or self.error is not None:
                return None
            packet = FramePacket(kind, int(sequence), int(device_timestamp_ns),
                                 host_received_ns, width, height, payload)
            return self.sync.ingest(packet, now_ns=time.monotonic_ns())

    def frame_bundle(self):
        with self.cv:
            if not self.running or self.error is not None:
                return None
            now_ns = time.monotonic_ns()
            pair = self.sync.current(now_ns)
            if pair is None:
                return None
            quality = {
                "validity": "IMAGE_PAIR_ONLY",
                "spatial_accuracy": "UNVERIFIED",
                "depth_valid_fraction_preview_estimate": (
                    self.valid_pct / 100.0 if self.valid_pct is not None else None),
                "sync_diagnostics_at_read": self.sync.diagnostics(now_ns),
            }
            return pair, bundle_metadata(pair, self.calibration, quality, now_ns)

    def status(self):
        now = time.monotonic()
        with self.cv:
            ages = {
                "rgb": round(now-self.times["rgb"], 2) if self.times["rgb"] else None,
                "depth": round(now-self.depth_time, 2) if self.depth_time else None,
                "depth_preview": round(now-self.times["depth"], 2)
                    if self.times["depth"] else None,
            }
            online = self.running and self.error is None and all(
                x is not None and x < FRESH_SECONDS for x in ages.values()
            )
            return {
                "online": bool(online), "pipeline_running": self.running,
                "profile": self.profile, "model": "OAK-D Pro AF",
                "rgb_resolution": self.config["rgb_size"],
                "depth_resolution": self.depth_shape,
                "rgb_fps": round(self.fps["rgb"], 1),
                "depth_fps": round(self.fps["depth"], 1),
                "depth_valid_pct": self.valid_pct,
                "center_depth_mm": self.center_mm,
                "usb": self.usb, "chip_temp_C": self.chip_C,
                "age_seconds": ages, "error": self.error,
                "uptime_seconds": round(now-self.started),
                "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),
                "mode": "PROD / NO AI / NO IR / NO ROBOT / NOT TABLE-CALIBRATED",
                "raw_depth_unit": "millimetres", "depth_alignment": "rectified-left",
                "rgbd_sync": self.sync.diagnostics(),
                "calibration_read_only_state": self.calibration.get("state"),
                "calibration_revision": self.calibration.get("revision"),
            }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if not self.path.startswith("/stream/"):
            LOG.debug("HTTP %s: %s", self.client_address[0], fmt % args)

    def _send_headers(self, code, mime, length=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def send(self, code, mime, data: bytes):
        self._send_headers(code, mime, len(data))
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        state = self.server.state
        if path == "/":
            try:
                self.send(200, "text/html; charset=utf-8", PAGE.read_bytes())
            except OSError:
                self.send(500, "text/plain", b"UI not installed")
        elif path == "/api/status":
            payload=json.dumps(state.status()).encode("utf-8")
            self.send(200,"application/json; charset=utf-8",payload)
        elif path == "/api/frame-bundle/latest":
            bundle = state.frame_bundle()
            if bundle is None:
                self.send(503, "application/json", b'{"sync_state":"NOT_READY"}')
            else:
                self.send(200, "application/json; charset=utf-8",
                          json.dumps(bundle[1]).encode("utf-8"))
        elif path == "/snapshot/frame-bundle.npz":
            if not state.client_semaphore.acquire(blocking=False):
                self.send(429, "text/plain", b"Too many clients")
                return
            try:
                bundle = state.frame_bundle()
                if bundle is None:
                    self.send(503, "text/plain", b"No synchronized RGB-D bundle")
                else:
                    data = encode_replay_npz(*bundle)
                    self.send(200, "application/octet-stream", data)
            finally:
                state.client_semaphore.release()
        elif path == "/healthz":
            s=state.status()
            self.send(200 if s["online"] else 503,"text/plain",
                      b"OK" if s["online"] else b"NOT_READY")
        elif path in ("/stream/rgb.mjpg", "/stream/depth.mjpg"):
            self.stream("rgb" if "rgb" in path else "depth")
        elif path == "/snapshot/rgb.jpg":
            frame=state.snapshot("rgb")
            self.send(200,"image/jpeg",frame) if frame else self.send(503,"text/plain",b"No RGB frame")
        elif path == "/snapshot/depth-mm.png":
            raw=state.raw_depth()
            if raw is None:
                self.send(503,"text/plain",b"No depth")
                return
            import cv2
            ok,data=cv2.imencode(".png",raw)
            if not ok:
                self.send(500,"text/plain",b"Depth encoding failed")
            else:
                self.send(200,"image/png",data.tobytes())
        else:
            self.send(404,"text/plain",b"Not found")

    def stream(self, kind):
        state=self.server.state
        if not state.client_semaphore.acquire(blocking=False):
            self.send(429,"text/plain",b"Too many viewers")
            return
        try:
            item=state.next_frame(kind,0,timeout=8.0)
            if item is None:
                self.send(503,"text/plain",b"Camera not ready")
                return
            self.connection.settimeout(5.0)
            self._send_headers(200,"multipart/x-mixed-replace; boundary=frame")
            while not self.server.stop_event.is_set() and item is not None:
                seq,jpg=item
                self.wfile.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                    str(len(jpg)).encode("ascii")+b"\r\n\r\n"+jpg+b"\r\n"
                )
                self.wfile.flush()
                item=state.next_frame(kind,seq,timeout=4.0)
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            pass
        finally:
            state.client_semaphore.release()


def render_depth_previews(state: State, stop: threading.Event):
    """Render at a bounded rate off the acquisition thread. Never blocks USB queues."""
    import cv2
    import numpy as np
    last_seen = 0.0
    interval = 1.0 / state.config["preview_fps"]
    while not stop.is_set():
        with state.cv:
            state.cv.wait_for(
                lambda: state.depth_time > last_seen or stop.is_set(), timeout=1.0
            )
            if stop.is_set():
                break
            if state.depth_time <= last_seen or state.depth is None:
                continue
            last_seen = state.depth_time
            raw = state.depth
        t0 = time.monotonic()
        reduced = cv2.resize(raw, (640, 400), interpolation=cv2.INTER_NEAREST)
        good = (reduced > 0) & (reduced < 5000)
        clipped = np.clip((reduced.astype(np.float32) - 200) * (255. / 4800.),
                          0, 255).astype(np.uint8)
        colored = cv2.applyColorMap(255 - clipped, cv2.COLORMAP_TURBO)
        colored[~good] = 0
        ok, jpeg = cv2.imencode(".jpg", colored, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if not ok:
            LOG.error("Depth preview JPEG encoder failed")
            stop.set()
            break
        state.publish("depth", jpeg.tobytes())
        roi = reduced[100:300, 160:480]
        valid_roi = roi[(roi > 0) & (roi < 5000)]
        with state.cv:
            state.valid_pct = round(float(good.mean() * 100), 1)
            state.center_mm = int(np.median(valid_roi)) if valid_roi.size else None
        stop.wait(max(0., interval - (time.monotonic() - t0)))


def run_camera(state: State, stop: threading.Event):
    import cv2
    import depthai as dai
    import numpy as np
    cfg=state.config
    with dai.Pipeline() as p:
        device=p.getDefaultDevice()
        color=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
        video=color.requestOutput(cfg["rgb_size"],type=dai.ImgFrame.Type.NV12,
                                  fps=cfg["rgb_fps"])
        encoder=p.create(dai.node.VideoEncoder).build(
            video,frameRate=cfg["rgb_fps"],
            profile=dai.VideoEncoderProperties.Profile.MJPEG,quality=80
        )
        qr=encoder.out.createOutputQueue(maxSize=4,blocking=False)
        left=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right=p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
        stereo=p.create(dai.node.StereoDepth)
        left.requestFullResolutionOutput(fps=cfg["depth_fps"]).link(stereo.left)
        right.requestFullResolutionOutput(fps=cfg["depth_fps"]).link(stereo.right)
        stereo.setRectification(True)
        stereo.setLeftRightCheck(True)
        stereo.setExtendedDisparity(cfg["extended"])
        qd=stereo.depth.createOutputQueue(maxSize=4,blocking=False)

        p.start()
        state.start(str(device.getUsbSpeed()))
        if state.usb != "UsbSpeed.SUPER":
            raise RuntimeError("USB3 required in production; negotiated " + state.usb)
        state.calibration = read_optics_readonly(device, dai, cfg["rgb_size"])
        LOG.info("CAMERA_STARTED profile=%s USB=%s calibration=%s",
                 state.profile, state.usb, state.calibration.get("state"))
        renderer_stop = threading.Event()
        renderer = threading.Thread(
            target=render_depth_previews, args=(state, renderer_stop), daemon=True
        )
        renderer.start()
        launched = time.monotonic()
        last_rgb = last_depth = launched
        next_chip = 0.0
        try:
            while not stop.is_set() and p.isRunning():
                now=time.monotonic()
                rgb=qr.tryGet()
                pkt=qd.tryGet()
                if rgb is not None:
                    data=bytes(rgb.getData())
                    if data[:2]!=bytes.fromhex("ffd8") or data[-2:]!=bytes.fromhex("ffd9"):
                        raise RuntimeError("Invalid hardware JPEG packet")
                    state.publish("rgb",data)
                    state.ingest_packet("rgb", data, rgb.getSequenceNum(),
                        int(rgb.getTimestampDevice().total_seconds() * 1e9),
                        cfg["rgb_size"][0], cfg["rgb_size"][1])
                    last_rgb=time.monotonic()
                    state.received["rgb"]+=1
                if pkt is not None:
                    raw = pkt.getFrame().copy()
                    state.publish_depth(raw)
                    state.ingest_packet("depth", raw, pkt.getSequenceNum(),
                        int(pkt.getTimestampDevice().total_seconds() * 1e9),
                        raw.shape[1], raw.shape[0])
                    last_depth = time.monotonic()
                if now>=next_chip:
                    try:
                        state.chip_C=round(float(device.getChipTemperature().average),1)
                    except Exception:
                        LOG.warning("Chip temperature read unavailable",exc_info=True)
                    next_chip=now+10
                if now-last_rgb>8 or now-last_depth>8:
                    raise RuntimeError("Camera frames stale >8s")
                with state.cv:
                    preview_ts=state.times["depth"]
                if now-(preview_ts or launched)>8:
                    raise RuntimeError("Depth preview stopped >8s")
                if not renderer.is_alive():
                    raise RuntimeError("Depth preview worker exited")
                if rgb is None and pkt is None:
                    stop.wait(.004)
            if not stop.is_set():
                raise RuntimeError("DepthAI pipeline stopped unexpectedly")
        finally:
            renderer_stop.set()
            with state.cv:
                state.cv.notify_all()
            renderer.join(timeout=3)
            if p.isRunning():
                p.stop()
                p.wait()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bind",default="127.0.0.1")
    ap.add_argument("--port",type=int,default=18092)
    ap.add_argument("--profile",choices=PROFILES,default="balanced")
    args=ap.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    if not 1<=args.port<=65535:
        ap.error("port out of range")
    lock=open(LOCK_PATH,"w")
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error("Another Vision OAK camera owner is running")
    state=State(args.profile)
    stop=threading.Event()
    server=ThreadingHTTPServer((args.bind,args.port),Handler)
    server.daemon_threads=True
    server.state=state
    server.stop_event=stop
    def sigterm(_sig,_frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,sigterm)
    thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.25},daemon=True)
    thread.start()
    LOG.info("HTTP_START http://%s:%d profile=%s",args.bind,args.port,args.profile)
    exit_code=0
    try:
        run_camera(state,stop)
    except KeyboardInterrupt:
        LOG.info("Operator requested stop")
    except Exception as e:
        state.fail(f"{type(e).__name__}: {e}")
        LOG.exception("CAMERA_FATAL; process exits for systemd recovery")
        exit_code=1
    finally:
        stop.set()
        state.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    return exit_code


if __name__=="__main__":
    sys.exit(main())
