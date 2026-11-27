"""Read-only guarded NERO ROS 2 telemetry, fixed local domain 181.

Only existing feedback subscribers and fixed GetParameters; no CAN socket,
command publisher, SetParameters, enable/disable, trajectory or action client.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from .luxonis import atomic_json, private_directory
from .nero import (DOMAIN,NODE,MAX_BYTES,SOURCES,PARAMS,empty,fresh,parse_arm,
                   parse_joints,parse_motors,parse_can,valid_observation)


def sample_can():
    try:
        r=subprocess.run(["/usr/sbin/ip","-details","-statistics","-json","link","show","dev","can0"],
                         timeout=.4,capture_output=True,text=True,check=False)
        if r.returncode or len(r.stdout)>16384:return None
        return parse_can(json.loads(r.stdout),time.time())
    except (OSError,ValueError,subprocess.SubprocessError):
        return None


class Observer:
    def __init__(self,node,*,source=NODE,domain=DOMAIN,can=sample_can):
        from sensor_msgs.msg import JointState
        from diagnostic_msgs.msg import DiagnosticArray
        self.node,self.source,self.domain,self.can=node,source,domain,can
        self.specs={
            "joints":(JointState,"/nero_guarded/feedback/joint_states","sensor_msgs/msg/JointState",parse_joints),
            "arm":(DiagnosticArray,"/nero_guarded/feedback/arm_status","diagnostic_msgs/msg/DiagnosticArray",parse_arm),
            "motors":(DiagnosticArray,"/nero_guarded/feedback/motor_status","diagnostic_msgs/msg/DiagnosticArray",parse_motors),
        }
        self.subs={};self.gids={};self.evidence=dict.fromkeys(SOURCES)
        self.client=self.pending=None
        self.next_params=0.;self.pending_until=0.
        self.can_report=None;self.next_can=0.
        self.graph="UNKNOWN"

    def endpoint(self,topic,kind):
        rows=self.node.get_publishers_info_by_topic(topic)
        if len(rows)!=1:return None
        r=rows[0]
        if r.node_namespace.rstrip("/")+"/"+r.node_name!=self.source or r.topic_type!=kind:return None
        return tuple(r.endpoint_gid),r.qos_profile.reliability

    def reset(self):
        for sub in self.subs.values():self.node.destroy_subscription(sub)
        self.subs.clear();self.gids.clear();self.evidence=dict.fromkeys(SOURCES)
        if self.pending is not None:self.pending.cancel()
        if self.client is not None:self.node.destroy_client(self.client)
        self.client=self.pending=None;self.next_params=0.

    def step(self):
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from rcl_interfaces.srv import GetParameters
        from rcl_interfaces.msg import ParameterType
        names=[ns.rstrip("/")+"/"+n for n,ns in self.node.get_node_names_and_namespaces()]
        count=names.count(self.source)
        graph="ACTIVE" if count==1 else "NO_NODE" if count==0 else "AMBIGUOUS"
        endpoints={k:self.endpoint(topic,typ) for k,(_,topic,typ,_) in self.specs.items()} if graph=="ACTIVE" else {}
        if graph=="ACTIVE" and any(len(self.node.get_publishers_info_by_topic(topic))>1 for _,topic,_,_ in self.specs.values()):
            graph="AMBIGUOUS"
        if graph!=self.graph:
            self.reset();self.graph=graph
        if graph=="ACTIVE":
            changed=False
            for key,(kind,topic,typ,parse) in self.specs.items():
                ep=endpoints.get(key)
                if self.gids.get(key)!=ep:
                    changed=True
                    old=self.subs.pop(key,None)
                    if old is not None:self.node.destroy_subscription(old)
                    self.gids[key]=ep;self.evidence[key]=None
                if ep is not None and key not in self.subs:
                    def bind(k,expected,t,ty,parse):
                        def receive(msg,info):
                            gid=info.get("publisher_gid")
                            if gid is not None and tuple(gid)!=expected[0]:return
                            if self.endpoint(t,ty)!=expected:return
                            self.evidence[k]=parse(msg,time.time())
                        return receive
                    qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE if ep[1]==ReliabilityPolicy.RELIABLE else ReliabilityPolicy.BEST_EFFORT)
                    self.subs[key]=self.node.create_subscription(kind,topic,bind(key,ep,topic,typ,parse),qos)
            if changed:
                if self.pending is not None:self.pending.cancel()
                if self.client is not None:self.node.destroy_client(self.client)
                self.pending=self.client=None;self.evidence["parameters"]=None;self.next_params=0.
            if self.client is None:self.client=self.node.create_client(GetParameters,self.source+"/get_parameters")
            mono=time.monotonic()
            if self.pending is not None:
                if self.pending.done():
                    try:
                        v=self.pending.result().values
                        data={k:x.bool_value for k,x in zip(PARAMS,v) if x.type==ParameterType.PARAMETER_BOOL} if len(v)==len(PARAMS) else {}
                        self.evidence["parameters"]={"stamp":time.time(),"values":data} if data else None
                    except Exception:self.evidence["parameters"]=None
                    self.pending=None
                elif mono>=self.pending_until:
                    self.pending.cancel();self.pending=None;self.evidence["parameters"]=None
            if self.pending is None and mono>=self.next_params:
                self.next_params=mono+1.5
                if self.client.service_is_ready():
                    req=GetParameters.Request();req.names=list(PARAMS)
                    self.pending=self.client.call_async(req);self.pending_until=mono+.8
        if time.monotonic()>=self.next_can:
            self.can_report=self.can()
            self.next_can=time.monotonic()+1.
        now=time.time()
        v=empty(now);v["graph"]=graph
        if graph=="ACTIVE":
            v["node"]={"domain":DOMAIN,"name":NODE}
            for k in SOURCES:
                packet=self.evidence[k]
                if packet is not None and fresh(packet["stamp"],now):v[k]=packet
        if self.can_report is not None and fresh(self.can_report["stamp"],now):v["can"]=self.can_report
        return v


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",required=True,type=Path);a=p.parse_args()
    if os.environ.get("ROS_DOMAIN_ID")!="181" or os.environ.get("ROS_LOCALHOST_ONLY")!="1":p.error("fixed local domain required")
    os.umask(0o077);root=private_directory(a.directory)
    target=root/"observation.json";target.unlink(missing_ok=True)
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    node=None;observer=None;stopped=False
    def stop(_sig,_frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    try:
        node=rclpy.create_node("vision_nero_observer",enable_rosout=False,start_parameter_services=False,use_global_arguments=False)
        observer=Observer(node)
        next_write=0.
        while not stopped and rclpy.ok():
            rclpy.spin_once(node,timeout_sec=.04)
            if time.monotonic()>=next_write:
                v=observer.step()
                atomic_json(target,v if valid_observation(v) else empty(time.time()),MAX_BYTES)
                next_write=time.monotonic()+.4
    finally:
        if observer is not None:observer.reset()
        if node is not None:node.destroy_node()
        rclpy.try_shutdown();target.unlink(missing_ok=True)


if __name__=="__main__":
    main()
