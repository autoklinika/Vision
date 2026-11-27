"""Bounded maintenance-only query using the original guarded ROS owner.

Run ONLY after the normal guarded unit has stopped and its CAN receiver
has closed, with all drives verified disabled and station idle. The caller
must restore the original unit afterward. No physical motion or enable
operation is added. This does not change the controller's configuration.
"""
import argparse
import json
import math
import os
import re
from pathlib import Path
import time

from vision_station.nero_firmware_limits import query_limits
from vision_station.nero_joint_limits import InstalledJointLimits
from vision_station.ros_nero_manual import sdk_feedback
from vision_station.ros_nero import sample_can
from vision_station.luxonis import atomic_json,private_directory

UNIT="vision-nero-guarded-lab.service"

def receivers():
    # Check kernel registration lists, including global CAN receivers.
    normal=errors=0
    paths=list(Path("/proc/net/can").glob("rcvlist_*"))
    if len(paths)<6:raise RuntimeError("CAN receiver inventory unavailable")
    for path in paths:
        for line in path.read_text().splitlines():
            f=line.split()
            if len(f)>=6 and f[0] in ("can0","any") and re.fullmatch(r"[0-9a-fA-F]{3,8}",f[1]):
                if path.name=="rcvlist_err":errors+=1
                else:normal+=1
    return normal,errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",required=True,type=Path)
    parser.add_argument("--model-urdf",required=True,type=Path)
    args=parser.parse_args()
    if (os.environ.get("ROS_DOMAIN_ID")!="181" or os.environ.get("ROS_LOCALHOST_ONLY")!="1"
            or not args.directory.is_absolute() or not args.directory.is_relative_to("/srv/vision-data")
            or receivers()!=(0,0)):
        parser.error("exclusive local maintenance owner required")
    # Reuse exactly the installed guarded driver class, not an additional
    # raw socket or a parallel owner. Startup is still passive.
    import rclpy
    from agx_arm_ctrl.vision_nero_guarded_node import VisionNeroGuardedNode
    os.umask(0o077)
    directory=private_directory(args.directory)
    target=directory/"controller-limits.json"
    if target.exists():raise RuntimeError("result already exists")
    reference=InstalledJointLimits(args.model_urdf,"v121")()
    rclpy.init(args=["--ros-args","-p","arm_type:=nero","-p","effector_type:=none",
                     "-p","physical_hold_enabled:=true","-p","auto_enable:=false",
                     "-p","control_enabled:=false","-r","__ns:=/nero_guarded"])
    node=None
    initial=None
    try:
        probe=rclpy.create_node("vision_nero_query_preflight",use_global_arguments=False)
        try:
            end=time.monotonic()+1.5
            while time.monotonic()<end:
                rclpy.spin_once(probe,timeout_sec=.1)
                if any(name=="agx_arm_ctrl_single_node" for name,_ in probe.get_node_names_and_namespaces()):
                    raise RuntimeError("existing ROS arm owner detected")
        finally:probe.destroy_node()
        if receivers()!=(0,0):raise RuntimeError("another CAN receiver appeared")
        before=sample_can()
        if not before or before["state"]!="ERROR-ACTIVE" or not before["up"] or before["bitrate"]!=1_000_000:
            raise RuntimeError("CAN not healthy")
        node=VisionNeroGuardedNode()
        def check():
            nonlocal initial
            if (not rclpy.ok() or node.auto_enable or node.control_enabled
                    or node.vision_arbiter.motion_allowed() or node.vision_arbiter.mode.value!="LOCKED"
                    or receivers()!=(1,1)):
                raise RuntimeError("exclusive guarded interlock lost")
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                f=sdk_feedback(node)
                if f is not None:
                    if not f.clean(time.time()) or f.arm_status not in (0,6) or any(f.drives()) or max(abs(v) for v in f.velocity)>.01:
                        raise RuntimeError("arm is not stationary with disabled drives")
                    if initial is None:initial=tuple(f.q)
                    elif max(abs(x-y) for x,y in zip(f.q,initial))>.003:
                        raise RuntimeError("actual position changed during query")
                    return f
                rclpy.spin_once(node,timeout_sec=.03)
            raise RuntimeError("fresh feedback unavailable")
        first=check()
        started=time.time()
        print("DISABLED_DRIVES_CONFIRMED",first.arm_status,first.drives(),flush=True)
        rows=query_limits(node.agx_arm,check)
        last=check()
        after=sample_can()
        if not after or after["state"]!="ERROR-ACTIVE" or not after["up"]:
            raise RuntimeError("CAN state changed")
        if any(after[k]!=before[k] for k in ("rxErrors","txErrors","rxDropped","txDropped")):
            raise RuntimeError("CAN counters indicate errors")
        data={"schema":"vision.nero.firmware-limit-observation.v1","startedAt":started,
              "capturedAt":time.time(),"source":reference.source(),
              "controllerRows":rows,"sdkRad":[list(r) for r in reference.sdk],
              "modelRad":[list(r) for r in reference.model],
              "beforePositionRad":list(initial),"afterPositionRad":list(last.q),
              "beforeDriveEnabled":list(first.drives()),"afterDriveEnabled":list(last.drives()),
              "txBefore":before["txPackets"],"txAfter":after["txPackets"]}
        atomic_json(target,data,16384)
        print("READ_ONLY_LIMIT_OBSERVATION",json.dumps(data),flush=True)
        return 0 if all(r["angleRad"] is not None for r in rows) else 2
    finally:
        # Stop publisher thread before disconnecting the original SDK owner.
        rclpy.try_shutdown()
        if node is not None:
            node.publisher_thread.join(timeout=2)
            node.destroy_node()


if __name__=="__main__":raise SystemExit(main())
