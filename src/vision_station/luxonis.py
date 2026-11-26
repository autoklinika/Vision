"""Read-only Luxonis device presentation. Core owns the protected projection.

No ROS imports, hardware opens, parameter writes or driver control on the
request path. Only a bounded, private, fresh observer snapshot is consumed.
The preview cache is ephemeral RAM, never an inspection archive.
"""
import base64
import binascii
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from .hardware_presence import usb_hardware_connections

SCHEMA = "vision.api.luxonis.v1"
OBS_SCHEMA = "vision.luxonis-observation.v1"
MAX_JPEG = 40 * 1024
MAX_REPORT = 128 * 1024
MAX_SNAPSHOT = MAX_REPORT
FRAME_AGE = 2.5
SNAPSHOT_AGE = 4.0
SETTINGS_AGE = 8.0
LEASE_AGE = 4.0
BINDINGS = ((181, "/oak"), (181, "/oak800"), (186, "/oak"))
PROFILE_IDS = ("rgbd_lab", "stereo800_lab")
STREAMS = ("rgb", "depth")
ENCODINGS = {"rgb": ("bgr8", "rgb8"), "depth": ("16UC1", "32FC1")}
GRAPH_STATES = ("UNKNOWN", "NO_NODE", "ACTIVE", "AMBIGUOUS")
ENDPOINT_STATES = ("UNKNOWN", "AVAILABLE", "UNAVAILABLE", "AMBIGUOUS")
# Explicit installed DepthAI ROS v3 allowlist: no serials, paths, IDs,
# addresses, arbitrary parameter queries or settings mutation.
BOOL_KEYS = frozenset({
    "driver.i_enable_ir", "pipeline_gen.i_enable_rgbd",
    "rgb.i_publish_topic", "rgb.r_set_man_focus", "rgb.r_set_man_exposure",
    "stereo.i_publish_topic", "stereo.i_aligned", "stereo.i_subpixel",
    "stereo.i_lr_check", "stereo.i_extended_disp",
})
NUMBER_KEYS = frozenset({
    "rgb.i_width", "rgb.i_height", "rgb.i_fps", "rgb.r_focus",
    "rgb.r_exposure", "rgb.r_iso", "stereo.i_width", "stereo.i_height",
    "stereo.i_fps", "left.i_width", "left.i_height", "left.i_fps",
    "right.i_width", "right.i_height", "right.i_fps",
    "driver.r_laser_dot_intensity", "driver.r_floodlight_intensity",
})
ENUM_KEYS = frozenset({
    "pipeline_gen.i_pipeline_type", "driver.i_pipeline_auto_calibration_mode",
    "stereo.i_depth_preset", "rgb.i_resolution", "left.i_resolution",
    "right.i_resolution",
})
PARAMETERS = tuple(sorted(BOOL_KEYS | NUMBER_KEYS | ENUM_KEYS))
_SAFE_ENUM = re.compile(r"[A-Za-z0-9_-]{1,48}", re.ASCII)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def fresh(stamp, now, age):
    return number(stamp) and 0 < stamp <= now and now - stamp <= age


def valid_setting(key, value):
    if key in BOOL_KEYS:
        return type(value) is bool
    if key in NUMBER_KEYS:
        return number(value) and 0 <= value <= 10**8
    return key in ENUM_KEYS and isinstance(value, str) and _SAFE_ENUM.fullmatch(value) is not None


def valid_settings(value):
    return type(value) is dict and all(valid_setting(k,v) for k,v in value.items())


def valid_profiles(value):
    return (type(value) is dict and set(value) <= set(PROFILE_IDS)
            and all(valid_settings(v) for v in value.values()))


def valid_node(value):
    return (type(value) is dict and set(value) == {"domain", "name"}
            and type(value["domain"]) is int and isinstance(value["name"],str)
            and (value["domain"], value["name"]) in BINDINGS)


def valid_endpoints(value):
    return (type(value) is dict and set(value) == set(STREAMS)
            and all(v in ENDPOINT_STATES for v in value.values()))


def valid_frame(value, stream):
    if value is None:
        return True
    if (type(value) is not dict or set(value) != {"stamp","sourceWidth","sourceHeight",
            "encoding","width","height","jpeg"}
            or not number(value["stamp"]) or value["stamp"] <= 0
            or value["encoding"] not in ENCODINGS[stream]
            or any(type(value[k]) is not int for k in ("sourceWidth","sourceHeight","width","height"))
            or not 1<=value["width"]<=min(640,value["sourceWidth"])
            or not 1<=value["height"]<=min(480,value["sourceHeight"])
            or not 1<=value["sourceWidth"]<=4096 or not 1<=value["sourceHeight"]<=4096):
        return False
    encoded=value["jpeg"]
    if not isinstance(encoded,str) or not 1<=len(encoded)<=4*((MAX_JPEG+2)//3):
        return False
    try:
        data=base64.b64decode(encoded,validate=True)
        return (4<=len(data)<=MAX_JPEG and data.startswith(b"\xff\xd8")
                and data.endswith(b"\xff\xd9")
                and base64.b64encode(data).decode("ascii")==encoded)
    except (ValueError,binascii.Error):
        return False


def valid_observation(value):
    try:
        if (type(value) is not dict or set(value)!={"schema","capturedAt","graph","node",
                "endpoints","settings","settingsAt","profiles","frames"}
                or value["schema"]!=OBS_SCHEMA or not number(value["capturedAt"])
                or not 0<value["capturedAt"]<253402300800 or value["graph"] not in GRAPH_STATES
                or not valid_endpoints(value["endpoints"]) or not valid_settings(value["settings"])
                or not valid_profiles(value["profiles"]) or type(value["frames"]) is not dict
                or set(value["frames"])!=set(STREAMS)):
            return False
        if value["graph"]=="ACTIVE":
            if not valid_node(value["node"]):
                return False
        elif (value["node"] is not None or value["settings"] or value["settingsAt"] is not None
              or any(v is not None for v in value["frames"].values())):
            return False
        if value["graph"]!="ACTIVE":
            expected={"UNKNOWN":"UNKNOWN","NO_NODE":"UNAVAILABLE","AMBIGUOUS":"AMBIGUOUS"}[value["graph"]]
            if any(v!=expected for v in value["endpoints"].values()):
                return False
        if value["settingsAt"] is None:
            if value["settings"]:
                return False
        elif not fresh(value["settingsAt"],value["capturedAt"],SETTINGS_AGE):
            return False
        for key,frame in value["frames"].items():
            if not valid_frame(frame,key):
                return False
            if frame is not None and (value["endpoints"][key]!="AVAILABLE"
                    or not fresh(frame["stamp"],value["capturedAt"],FRAME_AGE)):
                return False
        return True
    except (TypeError,ValueError,KeyError,OverflowError):
        return False


def private_directory(path):
    path=Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError("private monitor directory required")
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError("private monitor directory required")
    return path


def read_json(path, limit):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,"rb") as stream:
            info=os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1
                    or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>limit):
                return None
            raw=stream.read(limit+1)
        if len(raw)>limit:
            return None
        def unique(pairs):
            value={}
            for key,item in pairs:
                if key in value:raise ValueError("duplicate snapshot field")
                value[key]=item
            return value
        return json.loads(raw,object_pairs_hook=unique)
    except (OSError,ValueError,TypeError,RecursionError):
        return None


def atomic_json(path, value, limit):
    raw=json.dumps(value,ensure_ascii=True,allow_nan=False,separators=(",",":")).encode("ascii")
    if len(raw)>limit:
        raise ValueError("monitor snapshot exceeds bound")
    fd,name=tempfile.mkstemp(prefix=".luxonis-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def lease_active(directory, now):
    value=read_json(Path(directory)/"viewer.json",256)
    return type(value) is dict and set(value)=={"requestedAt"} and fresh(value["requestedAt"],now,LEASE_AGE)


def empty_observation(now, profiles=None):
    return {"schema":OBS_SCHEMA,"capturedAt":now,"graph":"UNKNOWN","node":None,
            "endpoints":dict.fromkeys(STREAMS,"UNKNOWN"),"settings":{},"settingsAt":None,
            "profiles":profiles or {},"frames":dict.fromkeys(STREAMS)}


class LuxonisMonitor:
    def __init__(self, directory=None, *, clock=time.time, usb=usb_hardware_connections):
        self.directory=Path(directory) if directory is not None else None
        self.clock,self.usb=clock,usb

    def report(self,instance, *, preview=False, idle=True):
        now=self.clock()
        observation=empty_observation(now)
        hardware="UNKNOWN"
        observer="UNAVAILABLE"
        if self.directory is not None:
            try:
                directory=private_directory(self.directory)
                hardware=self.usb().get("luxonis","UNKNOWN")
                if hardware not in ("USB_DETECTED","USB_NOT_DETECTED","UNKNOWN"):
                    hardware="UNKNOWN"
                if preview and idle:
                    # This only renews a short-lived local viewer interest;
                    # it cannot start a driver, open USB or command hardware.
                    atomic_json(directory/"viewer.json",{"requestedAt":now},256)
                value=read_json(directory/"observation.json",MAX_SNAPSHOT)
                if valid_observation(value) and fresh(value["capturedAt"],now,SNAPSHOT_AGE):
                    observation=value
                    observer="ACTIVE"
            except (OSError,ValueError,TypeError):
                pass
        frames=dict.fromkeys(STREAMS)
        if preview and idle and observer=="ACTIVE" and observation["graph"]=="ACTIVE":
            for key,frame in observation["frames"].items():
                if frame is not None and fresh(frame["stamp"],now,FRAME_AGE):
                    frames[key]=frame
        settings_at=observation["settingsAt"]
        settings=observation["settings"] if fresh(settings_at,now,SETTINGS_AGE) else {}
        return {"schema":SCHEMA,"source":"STATION","instanceId":instance,"capturedAt":now,
                "model":"OAK-D Pro AF","hardwareConnection":hardware,"observer":observer,
                "graph":observation["graph"],"node":observation["node"],"endpoints":observation["endpoints"],
                "settings":settings,"settingsAt":settings_at if settings else None,
                "profiles":observation["profiles"],"frames":frames,
                "previewAllowed":idle}


def validate_luxonis_report(value):
    try:
        if (type(value) is not dict or set(value)!={"schema","source","instanceId","capturedAt","model",
                "hardwareConnection","observer","graph","node","endpoints","settings","settingsAt",
                "profiles","frames","previewAllowed"} or value["schema"]!=SCHEMA
                or value["source"]!="STATION" or value["model"]!="OAK-D Pro AF"
                or not isinstance(value["instanceId"],str) or re.fullmatch(r"[0-9a-f]{32}",value["instanceId"]) is None
                or value["hardwareConnection"] not in ("USB_DETECTED","USB_NOT_DETECTED","UNKNOWN")
                or value["observer"] not in ("ACTIVE","UNAVAILABLE")
                or type(value["previewAllowed"]) is not bool):
            return False
        observation={k:value[k] for k in ("capturedAt","graph","node","endpoints","settings","settingsAt","profiles","frames")}
        observation["schema"]=OBS_SCHEMA
        if not valid_observation(observation):
            return False
        if value["observer"]=="UNAVAILABLE" and (value["graph"]!="UNKNOWN" or value["profiles"]):
            return False
        return value["previewAllowed"] or all(f is None for f in value["frames"].values())
    except (TypeError,ValueError,KeyError):
        return False
