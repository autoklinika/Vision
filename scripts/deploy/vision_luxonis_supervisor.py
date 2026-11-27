#!/usr/bin/env python3
"""Camera-only lifecycle supervisor. No device SDK or ROS command clients."""
import os
from pathlib import Path
import signal
import subprocess
import time

USB_IDS = {("03e7", "2485"), ("03e7", "f63b"), ("03e7", "f63c")}
STARTUP_GRACE = 60.0
STREAM_TIMEOUT = 30.0
SAMPLE_PERIOD = 10.0
SAMPLE_WINDOW = 3.0
TOPICS = {
    "rgb": "/oak/rgb/image_raw",
    "depth": "/oak/stereo/image_raw",
}
ENCODINGS = {"rgb": {"bgr8": 3, "rgb8": 3}, "depth": {"16UC1": 2, "32FC1": 4}}
CONFIG = "/srv/vision-data/config/luxonis/rgbd.yaml"


def camera_count(root=Path("/sys/bus/usb/devices")):
    """Passive USB enumeration. Return None if an inventory is unreadable."""
    count = 0
    root_seen = False
    try:
        for entry in root.iterdir():
            if ":" in entry.name:
                continue
            root_seen |= entry.name.startswith("usb")
            try:
                pair = tuple((entry / name).read_text(encoding="ascii").strip().lower()
                             for name in ("idVendor", "idProduct"))
            except (OSError, UnicodeError):
                # Non-device entries and re-enumeration races do not count.
                continue
            count += pair in USB_IDS
        return count if root_seen else None
    except OSError:
        return None


def valid_frame(message, stream):
    """Check image layout only; dark/invalid depth pixels are still live frames."""
    try:
        bpp = ENCODINGS[stream][message.encoding]
        w, h, step = message.width, message.height, message.step
        return (0 < w <= 4096 and 0 < h <= 4096 and step >= w * bpp
                and step * h <= 32 * 1024 * 1024 and len(message.data) == step * h
                and message.header.stamp.sec >= 0
                and 0 <= message.header.stamp.nanosec < 10**9)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


class StreamWatch:
    """Independent monotonic deadlines. Samples renew only their own stream."""
    def __init__(self, started):
        self.started = started
        self.last = dict.fromkeys(TOPICS, None)
        self.source_stamps = dict.fromkeys(TOPICS, -1)

    def seen(self, stream, now, source_stamp):
        if source_stamp > self.source_stamps[stream]:
            self.source_stamps[stream] = source_stamp
            self.last[stream] = now

    def expired(self, now):
        if now - self.started < STARTUP_GRACE:
            return False
        return any(last is None or now - last > STREAM_TIMEOUT
                   for last in self.last.values())


def terminate(child):
    if child is None or child.poll() is not None:
        return
    for sig, timeout in ((signal.SIGINT, 12), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        try:
            child.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass


def sample(node, executor, child, stopped, watch):
    """Short-lived best-effort subscribers; no image storage/processing."""
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image
    result = {}
    subs = {}
    gids = {}
    def publisher(topic):
        rows = node.get_publishers_info_by_topic(topic)
        if len(rows) != 1:
            return None
        row = rows[0]
        if row.node_namespace.rstrip("/") + "/" + row.node_name != "/oak":
            return None
        if row.topic_type != "sensor_msgs/msg/Image":
            return None
        return tuple(row.endpoint_gid)
    def callback(stream):
        def receive(msg):
            if stream not in result and valid_frame(msg, stream):
                stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
                if stamp > watch.source_stamps[stream]:
                    result[stream] = (time.monotonic(), stamp)
        return receive
    try:
        for key, topic in TOPICS.items():
            gid = publisher(topic)
            if gid is not None:
                gids[key] = gid
                subs[key] = node.create_subscription(Image, topic, callback(key),
                                                    qos_profile_sensor_data)
        deadline = time.monotonic() + SAMPLE_WINDOW
        while (subs and time.monotonic() < deadline and not stopped()
               and child.poll() is None):
            executor.spin_once(timeout_sec=0.1)
            for key in tuple(subs):
                if key in result:
                    node.destroy_subscription(subs.pop(key))
        # Do not accept a sample from a replaced or ambiguous publisher.
        return {key: stamp for key, stamp in result.items()
                if publisher(TOPICS[key]) == gids[key]}
    finally:
        for sub in subs.values():
            node.destroy_subscription(sub)


def main():
    if os.environ.get("ROS_DOMAIN_ID") != "186" or os.environ.get("ROS_LOCALHOST_ONLY") != "1":
        print("Refusing non-isolated ROS environment", flush=True)
        return 1
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions

    stopping = False
    def stop(_sig, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    child = node = executor = None
    initialized = False
    try:
        # Wait for the one expected USB device without opening it. This also
        # handles boot with no camera and reconnection after a driver failure.
        announced = False
        while not stopping and camera_count() != 1:
            if not announced:
                print("Waiting for exactly one recognized OAK USB device", flush=True)
                announced = True
            time.sleep(1)
        if stopping:
            return 0
        rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        initialized = True
        node = rclpy.create_node("vision_luxonis_watchdog", enable_rosout=False,
                                 start_parameter_services=False, use_global_arguments=False)
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        # Discover any existing /oak before opening the physical camera.
        deadline = time.monotonic() + 2.0
        while not stopping and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.1)
        if stopping:
            return 0
        if any(ns.rstrip("/") + "/" + name in ("/oak", "/oak800")
               for name, ns in node.get_node_names_and_namespaces()):
            print("Existing camera node detected; refusing a second owner", flush=True)
            return 1
        if camera_count() != 1:
            return 1
        child = subprocess.Popen([
            "ros2", "launch", "depthai_ros_driver_v3", "rgbd_pcl.launch.py",
            "name:=oak", "params_file:=" + CONFIG, "use_rviz:=False",
            "parent_frame:=oak_parent_frame",
        ], start_new_session=True)
        watch = StreamWatch(time.monotonic())
        next_sample = watch.started
        announced = False
        while not stopping:
            if child.poll() is not None:
                print("Camera launcher exited; requesting service recovery", flush=True)
                return 1
            now = time.monotonic()
            if now >= next_sample:
                for key, (received, stamp) in sample(node, executor, child, lambda: stopping, watch).items():
                    watch.seen(key, received, stamp)
                next_sample = now + SAMPLE_PERIOD
                if all(v is not None for v in watch.last.values()) and not announced:
                    print("RGB and depth streams observed", flush=True)
                    announced = True
            if watch.expired(time.monotonic()):
                print("Camera stream timeout; requesting service recovery", flush=True)
                return 1
            time.sleep(0.2)
        return 0
    finally:
        terminate(child)
        if executor is not None:
            executor.remove_node(node)
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if initialized:
            rclpy.try_shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
