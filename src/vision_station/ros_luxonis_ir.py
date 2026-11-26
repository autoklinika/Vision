"""One narrowly scoped runtime IR operation on the standalone camera.

Initial IR permission and zero boot intensities are set in the installed
camera YAML. This adapter changes exactly one runtime intensity, not the
pipeline, calibration, initial parameters or any robot service.
"""
import argparse
import json
import os
import subprocess
import time

from .luxonis_ir import GATE, KEYS, ON, valid_level
from .ros_luxonis import endpoint


def owner_active():
    try:
        r=subprocess.run(["systemctl","--user","show","vision-luxonis.service",
                         "-p","ActiveState","--value"],capture_output=True,text=True,
                        timeout=.6,check=False)
        return r.returncode==0 and r.stdout.strip()=="active"
    except (OSError,subprocess.SubprocessError):
        return False


def change(node, executor, channel, enabled, *, deadline, owner_check=owner_active):
    """Return actual driver parameter readback, not independent optical proof."""
    from rcl_interfaces.srv import GetParameters, SetParametersAtomically
    from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType

    def call(client, request):
        remaining=deadline-time.monotonic()
        if remaining<=0 or not client.wait_for_service(timeout_sec=min(.7,remaining)):
            raise TimeoutError()
        future=client.call_async(request)
        executor.spin_until_future_complete(future,timeout_sec=max(0,deadline-time.monotonic()))
        if not future.done() or future.result() is None:
            raise TimeoutError()
        return future.result()

    def binding():
        names=[ns.rstrip("/")+"/"+name for name,ns in node.get_node_names_and_namespaces()]
        if not owner_check() or names.count("/oak")!=1 or "/oak800" in names:
            return None
        result=tuple(endpoint(node,t,"/oak") for t in ("/oak/rgb/image_raw","/oak/stereo/image_raw"))
        return result if all(v[0]=="AVAILABLE" for v in result) else None

    # Give local DDS discovery a short bounded window before admitting writes.
    pinned=None
    while time.monotonic()<deadline-2:
        executor.spin_once(timeout_sec=.1)
        pinned=binding()
        if pinned is not None:
            break
    if pinned is None:
        return None
    get=node.create_client(GetParameters,"/oak/get_parameters")
    setter=node.create_client(SetParametersAtomically,"/oak/set_parameters_atomically")

    def read():
        req=GetParameters.Request(); req.names=[GATE,*KEYS.values()]
        values=call(get,req).values
        if (len(values)!=3 or values[0].type!=ParameterType.PARAMETER_BOOL or not values[0].bool_value
                or any(v.type!=ParameterType.PARAMETER_DOUBLE or not valid_level(v.double_value)
                       for v in values[1:])):
            return None
        return dict(zip(KEYS,(v.double_value for v in values[1:])))

    before=read()
    if before is None or binding()!=pinned:
        return None
    target=ON if enabled else 0.0
    if abs(before[channel]-target)>=1e-6:
        req=SetParametersAtomically.Request()
        req.parameters=[Parameter(name=KEYS[channel],
                    value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE,double_value=target))]
        reply=call(setter,req)
        if not reply.result.successful:
            return None
    after=read()
    if after is None or binding()!=pinned or abs(after[channel]-target)>=1e-6:
        raise RuntimeError("IR readback unconfirmed")
    other="flood" if channel=="dot" else "dot"
    if abs(after[other]-before[other])>=1e-6:
        raise RuntimeError("Concurrent IR change")
    return {**after,"capturedAt":time.time()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("channel",choices=tuple(KEYS))
    p.add_argument("mode",choices=("on","off"))
    a=p.parse_args()
    if os.environ.get("ROS_DOMAIN_ID")!="186" or os.environ.get("ROS_LOCALHOST_ONLY")!="1":
        return 2
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    node=None; executor=None
    try:
        node=rclpy.create_node("vision_manual_luxonis_ir",enable_rosout=False,
                               start_parameter_services=False,use_global_arguments=False)
        executor=SingleThreadedExecutor()
        executor.add_node(node)
        result=change(node,executor,a.channel,a.mode=="on",deadline=time.monotonic()+5.5)
        if result is None:
            return 2
        print(json.dumps(result,separators=(",",":")),flush=True)
        return 0
    except Exception:
        return 1
    finally:
        if executor is not None:
            executor.remove_node(node);executor.shutdown()
        if node is not None:node.destroy_node()
        rclpy.try_shutdown()


if __name__=="__main__":
    raise SystemExit(main())
