"""Passive ROS 2 Luxonis observer. Fixed local domains, read-only GetParameters.

No driver startup, no camera access, no set-parameter or action clients.
Only preview JPEGs in a private volatile cache, only on active viewer interest.
This is diagnostic display, not trusted Runtime measurement evidence.
"""
import argparse
import base64
import os
from pathlib import Path
import signal
import time

from .luxonis import (BINDINGS, STREAMS, PARAMETERS, PROFILE_IDS, MAX_JPEG, MAX_SNAPSHOT,
                      FRAME_AGE, SETTINGS_AGE, atomic_json, empty_observation, fresh,
                      lease_active, private_directory, valid_setting, valid_observation)
from .readiness import header_stamp
from vision_runtime.ros2_messages import image_layout

DEPTH_LIMIT_MM=2000


def preview_image(message, stream, now):
    """Respect ROS stride/endian/metric encoding; reduce only for display."""
    import cv2
    import numpy as np
    stamp=header_stamp(message)
    if not fresh(stamp,now,FRAME_AGE):
        return None
    try:
        depth=stream=="depth"
        image_layout(message,depth=depth)
        w,h=message.width,message.height
        if w>4096 or h>4096 or message.step*h>32*1024*1024:
            return None
        raw=bytes(message.data)
        ratio=min(1,640/w,480/h)
        size=(max(1,int(w*ratio)),max(1,int(h*ratio)))
        if depth:
            dtype=np.dtype((">" if message.is_bigendian else "<")+("u2" if message.encoding=="16UC1" else "f4"))
            data=np.ndarray((h,w),dtype=dtype,buffer=raw,strides=(message.step,dtype.itemsize))
            # Sample native pixels before conversion; OpenCV must not read
            # big-endian data as native numbers. Invalid depth stays black.
            ys=np.minimum((np.arange(size[1])*h/size[1]).astype(int),h-1)
            xs=np.minimum((np.arange(size[0])*w/size[0]).astype(int),w-1)
            metric=data[np.ix_(ys,xs)].astype(np.float32)
            if message.encoding=="32FC1":metric*=1000
            valid=np.isfinite(metric)&(metric>0)
            normalized=np.zeros(metric.shape,np.uint8)
            normalized[valid]=np.clip(metric[valid]/DEPTH_LIMIT_MM*255,0,255).astype(np.uint8)
            pixels=cv2.applyColorMap(normalized,cv2.COLORMAP_TURBO)
            pixels[~valid]=0
        else:
            data=np.ndarray((h,w,3),dtype=np.uint8,buffer=raw,strides=(message.step,3,1))
            pixels=cv2.resize(data,size,interpolation=cv2.INTER_AREA)
            if message.encoding=="rgb8":pixels=cv2.cvtColor(pixels,cv2.COLOR_RGB2BGR)
        for _ in range(3):
            for quality in (75,55,35):
                ok,encoded=cv2.imencode(".jpg",pixels,[cv2.IMWRITE_JPEG_QUALITY,quality])
                if ok and len(encoded)<=MAX_JPEG:
                    return {"stamp":stamp,"sourceWidth":w,"sourceHeight":h,"encoding":message.encoding,
                            "width":pixels.shape[1],"height":pixels.shape[0],
                            "jpeg":base64.b64encode(encoded.tobytes()).decode("ascii")}
            pixels=cv2.resize(pixels,(max(1,pixels.shape[1]//2),max(1,pixels.shape[0]//2)),interpolation=cv2.INTER_AREA)
    except (AttributeError,ValueError,TypeError,OverflowError,cv2.error):
        pass
    return None


def configured_profile(path, node):
    """Read the selected installed diagnostic YAML; expose allowlisted scalars."""
    import yaml
    if path is None:
        return None
    try:
        p=Path(path)
        if not p.is_file() or p.stat().st_size>16384:return None
        with p.open("rb") as stream:
            raw=stream.read(16385)
        if len(raw)>16384:return None
        value=yaml.safe_load(raw)
        params=value[node]["ros__parameters"]
        result={}
        for key in PARAMETERS:
            group,param=key.split(".",1)
            v=params.get(key,params.get(group,{}).get(param))
            if valid_setting(key,v):result[key]=v
        return result
    except (OSError,ValueError,TypeError,AttributeError,KeyError,yaml.YAMLError):
        return None


def parameter_values(response,names=PARAMETERS):
    if len(response.values)!=len(names):
        return {}
    result={}
    for key,v in zip(names,response.values):
        fields={1:"bool_value",2:"integer_value",3:"double_value",4:"string_value"}
        if v.type in fields:
            value=getattr(v,fields[v.type])
            if valid_setting(key,value):result[key]=value
    return result


def endpoint(node,topic,expected):
    endpoints=node.get_publishers_info_by_topic(topic)
    if not endpoints:
        return "UNAVAILABLE",None
    if len(endpoints)!=1:
        return "AMBIGUOUS",None
    item=endpoints[0]
    name=item.node_namespace.rstrip("/")+"/"+item.node_name
    if name!=expected or item.topic_type!="sensor_msgs/msg/Image":
        return "AMBIGUOUS",None
    return "AVAILABLE",tuple(item.endpoint_gid)


class Observer:
    """One local node/executor per allowed domain; no cross-domain data mixing."""
    def __init__(self, directory, profiles, domains=None):
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.signals import SignalHandlerOptions
        self.directory=directory
        self.profiles=profiles
        self.domains={}
        for domain in (sorted({d for d,_ in BINDINGS}) if domains is None else domains):
            context=Context()
            rclpy.init(args=[],context=context,domain_id=domain,signal_handler_options=SignalHandlerOptions.NO)
            node=rclpy.create_node("vision_luxonis_observer",context=context,enable_rosout=False,
                                  start_parameter_services=False,use_global_arguments=False)
            executor=SingleThreadedExecutor(context=context)
            executor.add_node(node)
            self.domains[domain]=(context,node,executor)
        self.selected=None
        self.client=None
        self.list_client=None
        self.pending=None
        self.pending_names=()
        self.pending_kind=None
        self.settings={}
        self.settings_at=None
        self.next_params=0.
        self.subs={}
        self.endpoints={}
        self.frames=dict.fromkeys(STREAMS)
        self.next_sample=dict.fromkeys(STREAMS,0.)

    def reset(self):
        if self.selected is not None:
            node=self.domains[self.selected[0]][1]
            for sub in self.subs.values():node.destroy_subscription(sub)
            if self.pending is not None:self.pending.cancel()
            if self.client is not None:node.destroy_client(self.client)
            if self.list_client is not None:node.destroy_client(self.list_client)
        self.subs={};self.endpoints={};self.client=None;self.list_client=None;self.pending=None;self.pending_kind=None;self.pending_names=()
        self.settings={};self.settings_at=None;self.next_params=0.
        self.frames=dict.fromkeys(STREAMS);self.next_sample=dict.fromkeys(STREAMS,0.)
        self.selected=None

    def close(self):
        self.reset()
        for context,node,executor in self.domains.values():
            executor.remove_node(node)
            executor.shutdown()
            node.destroy_node()
            context.try_shutdown()

    def step(self, bindings=BINDINGS):
        from rcl_interfaces.srv import GetParameters,ListParameters
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import Image
        for _context,_node,executor in self.domains.values():
            executor.spin_once(timeout_sec=0.02)
        now=time.time()
        active=[]
        for domain,name in bindings:
            if domain not in self.domains:continue
            node=self.domains[domain][1]
            found=sum(ns.rstrip("/")+"/"+n==name for n,ns in node.get_node_names_and_namespaces())
            active.extend([(domain,name)]*found)
        selected=active[0] if len(active)==1 else None
        if selected!=self.selected:
            self.reset()
            self.selected=selected
        result=empty_observation(now,self.profiles)
        result["graph"]="ACTIVE" if selected else "AMBIGUOUS" if active else "NO_NODE"
        if selected is None:
            result["endpoints"]=dict.fromkeys(STREAMS,"AMBIGUOUS" if active else "UNAVAILABLE")
            return result
        domain,name=selected
        node=self.domains[domain][1]
        result["node"]={"domain":domain,"name":name}
        if self.client is None:
            self.client=node.create_client(GetParameters,name+"/get_parameters")
            self.list_client=node.create_client(ListParameters,name+"/list_parameters")
        if self.pending is not None and self.pending.done():
            pending=self.pending
            self.pending=None
            try:
                if self.pending_kind=="list":
                    names=pending.result().result.names
                    # Never return the full list or read arbitrary parameters.
                    self.pending_names=tuple(key for key in PARAMETERS if key in names) if len(names)<=4096 else ()
                    if self.pending_names and self.client.service_is_ready():
                        req=GetParameters.Request();req.names=list(self.pending_names)
                        self.pending=self.client.call_async(req);self.pending_kind="get"
                    else:
                        self.settings={};self.settings_at=None
                elif self.pending_kind=="get":
                    self.settings=parameter_values(pending.result(),self.pending_names)
                    self.settings_at=now if self.settings else None
            except Exception:
                self.settings={};self.settings_at=None;self.pending=None
        if self.pending is not None and now>=self.next_params:
            self.pending.cancel();self.pending=None
            self.settings={};self.settings_at=None
        if self.pending is None and now>=self.next_params:
            self.next_params=now+5
            if self.list_client.service_is_ready() and self.client.service_is_ready():
                req=ListParameters.Request()
                req.prefixes=["driver","pipeline_gen","rgb","left","right","stereo"]
                req.depth=1
                self.pending=self.list_client.call_async(req);self.pending_kind="list"
            else:
                self.settings={};self.settings_at=None
        if fresh(self.settings_at,now,SETTINGS_AGE):
            result["settings"]=self.settings;result["settingsAt"]=self.settings_at
        interested=lease_active(self.directory,now)
        topics={"rgb":name+"/rgb/image_raw","depth":name+"/stereo/image_raw"}
        for key,topic in topics.items():
            state,gid=endpoint(node,topic,name)
            result["endpoints"][key]=state
            # Drop cached frame immediately on changed endpoint or expired lease.
            if self.endpoints.get(key)!=gid or not interested or state!="AVAILABLE":
                sub=self.subs.pop(key,None)
                if sub is not None:node.destroy_subscription(sub)
                self.frames[key]=None
                self.next_sample[key]=0.
            self.endpoints[key]=gid
            if interested and gid is not None and key not in self.subs and time.monotonic()>=self.next_sample[key]:
                def bind(stream,expected_gid,expected_topic,expected_node):
                    def receive(message,info):
                        # Read one actual source frame per bounded sample,
                        # rejecting wrong endpoints and stale header stamps.
                        # The installed Jazzy rclpy MessageInfo omits publisher_gid.
                        # Re-check the exact unique graph endpoint in that case;
                        # this is diagnostic provenance, not DDS authentication.
                        received_gid=info.get("publisher_gid")
                        if received_gid is not None and tuple(received_gid)!=expected_gid:
                            return
                        if endpoint(node,expected_topic,expected_node)!=("AVAILABLE",expected_gid):
                            return
                        if self.frames[stream] is not None and self.frames[stream]["stamp"]>= (header_stamp(message) or 0):
                            return
                        if lease_active(self.directory,time.time()):
                            self.frames[stream]=preview_image(message,stream,time.time())
                            self.next_sample[stream]=time.monotonic()+0.7
                    return receive
                self.subs[key]=node.create_subscription(Image,topic,bind(key,gid,topic,name),
                    QoSProfile(depth=1,reliability=ReliabilityPolicy.BEST_EFFORT))
            # Release the image subscriber after a sample so we do not sustain
            # an unnecessary extra full-rate RGB-D consumer.
            if key in self.subs and self.next_sample[key]>time.monotonic():
                node.destroy_subscription(self.subs.pop(key))
            frame=self.frames[key]
            if interested and state=="AVAILABLE" and frame and fresh(frame["stamp"],now,FRAME_AGE):
                result["frames"][key]=frame
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",required=True,type=Path)
    parser.add_argument("--rgbd-config",type=Path)
    parser.add_argument("--stereo-config",type=Path)
    args=parser.parse_args()
    if os.environ.get("ROS_LOCALHOST_ONLY")!="1":
        parser.error("local ROS discovery required")
    root=private_directory(args.directory)
    os.umask(0o077)
    (root/"viewer.json").unlink(missing_ok=True)
    (root/"observation.json").unlink(missing_ok=True)
    profiles={}
    for key,path,node in zip(PROFILE_IDS,(args.rgbd_config,args.stereo_config),("/oak","/oak800")):
        value=configured_profile(path,node)
        if value is not None:profiles[key]=value
    import cv2
    cv2.setNumThreads(1)
    observer=Observer(root,profiles)
    stopped=False
    def stop(_sig,_frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        next_write=0.
        # Discover local nodes before reporting absence.
        until=time.monotonic()+2
        while not stopped and time.monotonic()<until:
            for _,_,executor in observer.domains.values():executor.spin_once(timeout_sec=.1)
        while not stopped:
            value=observer.step()
            if time.monotonic()>=next_write:
                if valid_observation(value):
                    atomic_json(root/"observation.json",value,MAX_SNAPSHOT)
                else:
                    atomic_json(root/"observation.json",empty_observation(time.time(),profiles),MAX_SNAPSHOT)
                next_write=time.monotonic()+0.25
            time.sleep(.06)
    finally:
        observer.close()
        for name in ("viewer.json","observation.json"):(root/name).unlink(missing_ok=True)


if __name__=="__main__":
    main()
