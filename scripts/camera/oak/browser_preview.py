#!/usr/bin/env python3
"""DEV: read-only OAK-D Pro AF RGB + stereo browser preview (DepthAI v3).

The process is the sole camera owner. No robot API, neural networks, IR enable,
calibration writes, image recording, or automatic service installation.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = logging.getLogger("oak-preview")
PAGE = Path(__file__).with_suffix(".html")
LOCK = "/tmp/vision-oak-browser-preview.lock"
FRESH_SECONDS = 3.5


class PreviewState:
    def __init__(self):
        self.cv = threading.Condition()
        self.frames = {"rgb": None, "depth": None}
        self.seqs = {"rgb": 0, "depth": 0}
        self.frame_times = {"rgb": 0.0, "depth": 0.0}
        self.fps = {"rgb": 0.0, "depth": 0.0}
        self.usb = "unknown"
        self.device = "OAK-D Pro AF"
        self.depth_valid_pct = None
        self.error = None
        self.running = False

    def start(self, usb: str):
        with self.cv:
            self.running = True
            self.error = None
            self.usb = usb
            self.cv.notify_all()

    def fail(self, error: str):
        with self.cv:
            self.running = False
            self.error = error[:240]
            self.cv.notify_all()

    def stop(self):
        with self.cv:
            self.running = False
            self.cv.notify_all()

    def publish(self, kind: str, jpeg: bytes, *, valid_pct=None):
        if kind not in self.frames:
            raise ValueError("unknown stream")
        if not jpeg:
            raise ValueError("empty image")
        now = time.monotonic()
        with self.cv:
            prev = self.frame_times[kind]
            if prev and now > prev:
                instantaneous = min(100.0, 1.0 / (now - prev))
                self.fps[kind] = (
                    instantaneous if self.fps[kind] == 0 else
                    (self.fps[kind] * 0.8 + instantaneous * 0.2)
                )
            self.frames[kind] = bytes(jpeg)
            self.seqs[kind] += 1
            self.frame_times[kind] = now
            if kind == "depth":
                self.depth_valid_pct = valid_pct
            self.cv.notify_all()

    def next_frame(self, kind: str, after: int, timeout=3.0):
        with self.cv:
            self.cv.wait_for(
                lambda: self.seqs[kind] > after or self.error is not None
                or (not self.running and self.seqs[kind] == 0),
                timeout=timeout,
            )
            if self.seqs[kind] > after:
                return self.seqs[kind], self.frames[kind]
            return None

    def status(self):
        now = time.monotonic()
        with self.cv:
            ages = {
                k: round(now - v, 1) if v else None
                for k, v in self.frame_times.items()
            }
            online = (
                self.running and self.error is None and
                all(v is not None and v < FRESH_SECONDS for v in ages.values())
            )
            return {
                "online": online, "pipeline_running": self.running,
                "device": self.device, "usb": self.usb,
                "rgb_fps": round(self.fps["rgb"], 1),
                "depth_fps": round(self.fps["depth"], 1),
                "depth_valid_pct": (
                    round(self.depth_valid_pct, 1)
                    if self.depth_valid_pct is not None else None
                ),
                "age_seconds": ages, "error": self.error,
                "mode": "DEV / NO ROBOT / NO IR / UNCALIBRATED",
            }


def run_camera(state: PreviewState, stop_event: threading.Event):
    """Only producer; no consumer may open DepthAI directly."""
    try:
        import cv2
        import depthai as dai
        import numpy as np

        with dai.Pipeline() as pipeline:
            device = pipeline.getDefaultDevice()
            rgb_cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            rgb_queue = rgb_cam.requestOutput((640, 360), fps=12).createOutputQueue(
                maxSize=2, blocking=False
            )

            left = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
            right = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)
            stereo = pipeline.create(dai.node.StereoDepth)
            left.requestFullResolutionOutput(fps=12).link(stereo.left)
            right.requestFullResolutionOutput(fps=12).link(stereo.right)
            stereo.setRectification(True)
            stereo.setLeftRightCheck(True)
            stereo.setExtendedDisparity(True)
            depth_queue = stereo.depth.createOutputQueue(maxSize=2, blocking=False)

            pipeline.start()
            state.start(str(device.getUsbSpeed()))
            LOG.info("Camera pipeline active; USB=%s", state.usb)
            try:
                while pipeline.isRunning() and not stop_event.is_set():
                    rgb = rgb_queue.tryGet()
                    depth_msg = depth_queue.tryGet()
                    if rgb is not None:
                        ok, encoded = cv2.imencode(
                            ".jpg", rgb.getCvFrame(), [cv2.IMWRITE_JPEG_QUALITY, 72]
                        )
                        if ok:
                            state.publish("rgb", encoded.tobytes())
                    if depth_msg is not None:
                        raw = depth_msg.getFrame()  # uint16 millimetres, not calibrated to table
                        reduced = cv2.resize(raw, (640, 400), interpolation=cv2.INTER_NEAREST)
                        valid = (reduced >= 200) & (reduced < 5000)
                        scaled = np.clip(
                            (reduced.astype(np.float32) - 200) * (255.0 / 4800),
                            0, 255,
                        ).astype(np.uint8)
                        view = cv2.applyColorMap(255 - scaled, cv2.COLORMAP_TURBO)
                        view[~valid] = (0, 0, 0)
                        ok, encoded = cv2.imencode(
                            ".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 70]
                        )
                        if ok:
                            state.publish(
                                "depth", encoded.tobytes(),
                                valid_pct=float(valid.mean() * 100),
                            )
                    if rgb is None and depth_msg is None:
                        stop_event.wait(0.015)
                if not stop_event.is_set():
                    raise RuntimeError("DepthAI pipeline stopped unexpectedly")
            finally:
                if pipeline.isRunning():
                    pipeline.stop()
                    pipeline.wait()
    except Exception as exc:
        LOG.exception("OAK preview camera unavailable")
        state.fail(f"{type(exc).__name__}: {exc}")
    finally:
        state.stop()


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _headers(self, code: int, content_type: str, size=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        if size is not None:
            self.send_header("Content-Length", str(size))
        self.end_headers()

    def _send(self, code, mime, body):
        self._headers(code, mime, len(body))
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            try:
                self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
            except OSError:
                self._send(500, "text/plain; charset=utf-8", b"Missing HTML file")
        elif path == "/api/status":
            payload = json.dumps(self.server.state.status()).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)
        elif path in ("/stream/rgb.mjpg", "/stream/depth.mjpg"):
            self._stream("rgb" if "rgb" in path else "depth")
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def _stream(self, kind):
        state = self.server.state
        current = state.next_frame(kind, -1, timeout=3.0)
        if current is None:
            self._send(503, "text/plain; charset=utf-8", b"Camera stream unavailable")
            return
        self._headers(200, "multipart/x-mixed-replace; boundary=frame")
        previous = -1
        try:
            while not self.server.stop_event.is_set():
                if current is None:
                    break
                version, jpg = current
                self.wfile.write(
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                    str(len(jpg)).encode("ascii") + b"\r\n\r\n" + jpg + b"\r\n"
                )
                self.wfile.flush()
                previous = version
                current = state.next_frame(kind, previous, timeout=4.0)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1",
                        help="Listen IP; default loopback. Use Tailscale IP for remote clients.")
    parser.add_argument("--port", type=int, default=18092)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")

    # Prevent two instances of this preview from competing for the USB device.
    lock_handle = open(LOCK, "w", encoding="ascii")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("another browser preview instance already owns the lock")
    state = PreviewState()
    stop_event = threading.Event()
    server = ThreadingHTTPServer((args.bind, args.port), PreviewHandler)
    server.daemon_threads = True
    server.state = state
    server.stop_event = stop_event

    def request_stop(_signal, _frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, request_stop)
    worker = threading.Thread(target=run_camera, args=(state, stop_event), daemon=True)
    worker.start()
    LOG.info("Read-only preview at http://%s:%d", args.bind, args.port)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        LOG.info("Stopping preview")
    finally:
        stop_event.set()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
