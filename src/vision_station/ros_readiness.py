"""Optional ROS 2 Jazzy read-only diagnostics process (system Python).

It never publishes application topics, creates command clients, opens USB/CAN
devices, invokes planning, changes parameters or launches a hardware driver.
Only explicitly named local-domain publishers are sampled. Graph identity is
diagnostic provenance, NOT authenticated Runtime evidence.
"""
import argparse
import math
import os
from pathlib import Path
import signal
import struct
import time

from .readiness import (arm, fresh, header_stamp, joints, motors, nero_observation,
                        planning_observation, rgbd_observation, write_snapshot)
from vision_runtime.ros2_messages import image_layout


def image_stamp(message, now, *, depth=False):
    try:
        stamp = header_stamp(message)
        if not fresh(stamp,now):
            return None
        image_layout(message,depth=depth)
        if depth:
            # Sample a bounded grid of actual pixels, not row padding. Do not
            # retain payloads or hash/save images for a liveness observation.
            size = 2 if message.encoding == "16UC1" else 4
            fmt = (">" if message.is_bigendian else "<") + ("H" if size == 2 else "f")
            usable = False
            for y in range(0,message.height,max(1,message.height//16)):
                for x in range(0,message.width,max(1,message.width//16)):
                    value, = struct.unpack_from(fmt,message.data,y*message.step+x*size)
                    if math.isfinite(value) and value > 0:
                        usable = True
                        break
                if usable:
                    break
            if not usable:
                return None
        return stamp
    except (ValueError,TypeError,AttributeError,struct.error):
        return None


def unique_publisher(node, topic, expected):
    """Pin graph endpoint and reject duplicates; no claim of DDS authentication."""
    endpoints = node.get_publishers_info_by_topic(topic)
    if len(endpoints) != 1:
        return None
    endpoint = endpoints[0]
    name = (endpoint.node_namespace.rstrip("/") + "/" + endpoint.node_name)
    if name != expected:
        return None
    return tuple(endpoint.endpoint_gid)


def sample(node, *, duration=1.5):
    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray
    from moveit_msgs.msg import PlanningScene
    from sensor_msgs.msg import Image, JointState
    from rclpy.qos import QoSProfile,ReliabilityPolicy
    from rclpy.time import Time
    from tf2_ros import Buffer, TransformListener

    qos = QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT)
    sources = {}
    subscriptions = {}
    evidence = {}
    guard = "/nero_guarded/agx_arm_ctrl_single_node"
    specs = {
        "joints": (JointState,"/nero_guarded/feedback/joint_states",guard,joints),
        "arm": (DiagnosticArray,"/nero_guarded/feedback/arm_status",guard,arm),
        "motors": (DiagnosticArray,"/nero_guarded/feedback/motor_status",guard,motors),
        "scene": (PlanningScene,"/monitored_planning_scene","/move_group",
                  lambda msg,now:joints(msg.robot_state.joint_state,now)),
    }
    for camera in ("oak","oak800"):
        specs[camera+"_rgb"] = (Image,f"/{camera}/rgb/image_raw","/"+camera,image_stamp)
        specs[camera+"_depth"] = (Image,f"/{camera}/stereo/image_raw","/"+camera,
                                 lambda msg,now:image_stamp(msg,now,depth=True))
    buffer = listener = None
    try:
        # Graph discovery persists on this node across cycles; subscribe to
        # explicit live endpoints only, not arbitrary devices or fake drivers.
        for key,(kind,topic,publisher,parse) in specs.items():
            endpoint = unique_publisher(node,topic,publisher)
            if endpoint is None:
                continue
            sources[key] = endpoint
            # A ROS callback must have exactly one argument (the closure below
            # avoids rclpy interpreting default arguments as MessageInfo).
            def bind(key,parse):
                def receive(message):
                    evidence[key] = parse(message,time.time())
                return receive
            subscriptions[key] = node.create_subscription(kind,topic,bind(key,parse),qos)
        if "scene" in sources:
            buffer = Buffer()
            listener = TransformListener(buffer,node,spin_thread=False)
        deadline = time.monotonic()+duration
        while rclpy.ok() and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=0.05)
            # Only one image per stream in a sample window. No continuous
            # additional full-rate camera client.
            for key in tuple(subscriptions):
                if key.endswith(("_rgb","_depth")) and key in evidence:
                    node.destroy_subscription(subscriptions.pop(key))
        now = time.time()
        for key,endpoint in sources.items():
            _,topic,publisher,_ = specs[key]
            if unique_publisher(node,topic,publisher) != endpoint:
                evidence.pop(key,None)
        tf_stamp = None
        if buffer is not None and evidence.get("scene") is not None:
            try:
                # Explicit existing model frames; no scene/world calibration
                # assertion. A missing or stale transform stays unknown.
                names = node.get_node_names_and_namespaces()
                if ("vision_nero_robot_state_publisher","/") in names:
                    transform = buffer.lookup_transform("base_link","link7",Time())
                    t,q = transform.transform.translation,transform.transform.rotation
                    numbers = (t.x,t.y,t.z,q.x,q.y,q.z,q.w)
                    if all(math.isfinite(v) for v in numbers) and abs(math.hypot(*numbers[3:])-1)<1e-3:
                        tf_stamp = header_stamp(transform)
            except Exception:
                pass
        return {
            "nero":nero_observation(evidence.get("joints"),evidence.get("arm"),evidence.get("motors"),now),
            "oak":rgbd_observation(evidence.get("oak_rgb"),evidence.get("oak_depth"),now),
            "oak800":rgbd_observation(evidence.get("oak800_rgb"),evidence.get("oak800_depth"),now),
            "moveit":planning_observation(evidence.get("joints"),evidence.get("scene"),tf_stamp,now),
        }
    finally:
        if listener is not None:
            listener.unregister()
        for subscription in subscriptions.values():
            node.destroy_subscription(subscription)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,required=True)
    parser.add_argument("--once",action="store_true")
    args = parser.parse_args()
    if (os.environ.get("ROS_DOMAIN_ID") != "181" or os.environ.get("ROS_LOCALHOST_ONLY") != "1"):
        parser.error("explicit local ROS domain 181 is required")
    import rclpy
    os.umask(0o077)
    args.report.unlink(missing_ok=True)
    rclpy.init()
    node = None
    stopped = False
    def stop(_signal,_frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        node = rclpy.create_node("vision_device_readiness",enable_rosout=False,start_parameter_services=False)
        # Give the local graph time to discover publishers without a ROS daemon.
        deadline = time.monotonic()+2.0
        while not stopped and rclpy.ok() and time.monotonic()<deadline:
            rclpy.spin_once(node,timeout_sec=0.1)
        while not stopped and rclpy.ok():
            observations = sample(node)
            write_snapshot(args.report,observations,time.time())
            if args.once:
                break
            deadline = time.monotonic()+0.75
            while not stopped and rclpy.ok() and time.monotonic()<deadline:
                rclpy.spin_once(node,timeout_sec=0.1)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
        if not args.once:
            args.report.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
