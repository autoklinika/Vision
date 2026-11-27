"""One fixed, typed local ROS 2 clear request; never opens CAN."""
import argparse
import json
import os
import time

from .nero_clear import SERVICE, valid_id, valid_scope, validate_result, result
from .nero import NODE
from .ros_nero_guarded_diagnostics import from_message

SERVICE_TYPE="vision_nero_diagnostics_interfaces/srv/ClearJointErrors"


def binding(node):
    names=node.get_node_names_and_namespaces()
    if sum(ns.rstrip("/")+"/"+name==NODE for name,ns in names)!=1:
        return False
    providers=[]
    try:
        for name,ns in names:
            for service,types in node.get_service_names_and_types_by_node(name,ns):
                if service==SERVICE:providers.append((ns.rstrip("/")+"/"+name,tuple(types)))
    except Exception:
        return False
    return providers==[(NODE,(SERVICE_TYPE,))]


def call(node,executor,operation,scope,not_after,deadline):
    from vision_nero_diagnostics_interfaces.srv import ClearJointErrors
    while time.monotonic()<deadline-4:
        executor.spin_once(timeout_sec=.1)
        if binding(node):break
    else:return result(operation,scope,"REJECTED","TRANSPORT_UNAVAILABLE")
    client=node.create_client(ClearJointErrors,SERVICE)
    if not client.wait_for_service(timeout_sec=.5) or not binding(node) or time.time()>=not_after:
        return result(operation,scope,"REJECTED","TRANSPORT_UNAVAILABLE")
    req=ClearJointErrors.Request(operation_id=operation,scope=scope,not_after=not_after)
    future=client.call_async(req)
    try:
        executor.spin_until_future_complete(future,timeout_sec=max(0,deadline-time.monotonic()))
        reply=future.result() if future.done() else None
        if reply is None or not binding(node):
            return result(operation,scope,"UNVERIFIED","SOURCE_CHANGED",invoked=None)
        v={"operationId":reply.operation_id,"scope":reply.scope,"result":reply.result,
           "reason":reply.reason,"commandInvoked":reply.command_invoked,"axisResults":list(reply.axis_results),
           "sentAfter":reply.sent_after or None,"before":from_message(reply.before),"after":from_message(reply.after)}
        if not validate_result(v) or v["operationId"]!=operation or v["scope"]!=scope:
            return result(operation,scope,"UNVERIFIED","TRANSPORT_UNAVAILABLE",invoked=None)
        return v
    except Exception:
        return result(operation,scope,"UNVERIFIED","TRANSPORT_UNAVAILABLE",invoked=None)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation");p.add_argument("scope",type=int);p.add_argument("not_after",type=float)
    a=p.parse_args()
    if (os.environ.get("ROS_DOMAIN_ID")!="181" or os.environ.get("ROS_LOCALHOST_ONLY")!="1"
            or not valid_id(a.operation) or not valid_scope(a.scope)):
        return 2
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    node=rclpy.create_node("vision_nero_clear_client",enable_rosout=False,start_parameter_services=False,use_global_arguments=False)
    executor=SingleThreadedExecutor();executor.add_node(node)
    try:
        v=call(node,executor,a.operation,a.scope,a.not_after,time.monotonic()+6)
        print(json.dumps(v,allow_nan=False,separators=(",",":")),flush=True)
        return 0
    finally:
        executor.shutdown();node.destroy_node();rclpy.try_shutdown()


if __name__=="__main__":raise SystemExit(main())
