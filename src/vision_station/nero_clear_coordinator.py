"""Core-side admission and fixed ROS service transport."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .nero_clear import (CLEARABLE_ARM_STATES, result, valid_id, valid_scope, validate_result)
from .nero_diagnostics import decode, SCOPES
from .luxonis import private_directory

SCHEMA="vision.api.nero-clear.v1"


def valid_intent(v):
    return (type(v) is dict and set(v)=={"instanceId","operationId","scope"}
            and valid_id(v["instanceId"]) and valid_id(v["operationId"]) and valid_scope(v["scope"]))


def valid_actor(v):
    return isinstance(v,str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}",v) is not None


def validate_envelope(v):
    try:
        return (type(v) is dict and set(v)=={"schema","source","instanceId","operation"}
                and v["schema"]==SCHEMA and v["source"]=="STATION" and valid_id(v["instanceId"])
                and validate_result(v["operation"]))
    except (KeyError,TypeError,ValueError):
        return False


def eligible(report):
    _,coverage=decode(report)
    if set(coverage)!=set(SCOPES):return False
    arm=report["arm"];motors=report["motors"];params=report["parameters"];can=report["can"]
    return (arm["armStatus"] in CLEARABLE_ARM_STATES
            and all(m["enabled"] is False for m in motors["rows"])
            and params is not None and params["values"].get("control_enabled") is False
            and params["values"].get("auto_enable") is False
            and can is not None and can["up"] is True and can["state"]=="ERROR-ACTIVE"
            and report["hardwareConnection"]=="USB_CAN_DETECTED")


class RosClearTransport:
    """Explicit private NVMe overlay, fixed endpoint, no arbitrary ROS commands."""
    def __init__(self,overlay,ros_directory,*,run=subprocess.run):
        root=Path(overlay)
        if not root.is_absolute() or not root.is_relative_to("/srv/vision-data") or any(p.is_symlink() for p in (root,*root.parents)):
            raise ValueError("explicit NVMe overlay required")
        self.setup=root/"setup.bash"
        if not self.setup.is_file() or self.setup.is_symlink():
            raise ValueError("missing generated interface overlay")
        self.ros_directory=private_directory(Path(ros_directory))
        self.run=run

    def change(self,operation,scope):
        if not valid_id(operation) or not valid_scope(scope):raise ValueError("invalid clear")
        started=time.time()
        env=dict(os.environ,ROS_DOMAIN_ID="181",ROS_LOCALHOST_ONLY="1",
                 ROS_HOME=str(self.ros_directory),ROS_LOG_DIR=str(self.ros_directory/"log"),
                 PYTHONDONTWRITEBYTECODE="1",TMPDIR="/srv/vision-data/tmp")
        def unknown():return result(operation,scope,"UNVERIFIED","TRANSPORT_UNAVAILABLE",invoked=None)
        try:
            proc=self.run(["/bin/bash","-c",
                'set -e; source /opt/ros/jazzy/setup.bash; source "$1"; shift; exec /usr/bin/python3 -B -m vision_station.ros_nero_clear "$@"',
                "vision-nero-clear",str(self.setup),operation,str(scope),str(started+8)],
                env=env,capture_output=True,text=True,timeout=9,check=False)
            if proc.returncode or len(proc.stdout)>8192:return unknown()
            v=json.loads(proc.stdout)
            if not validate_result(v) or v["operationId"]!=operation or v["scope"]!=scope:return unknown()
            if v["sentAfter"] is not None and not started<=v["sentAfter"]<=time.time():return unknown()
            for name in ("before","after"):
                e=v[name]
                if e is not None and max(e["armStamp"],*e["driveStamps"])>time.time():return unknown()
            return v
        except (OSError,ValueError,TypeError,subprocess.SubprocessError):
            return unknown()


def envelope(instance,operation):
    return {"schema":SCHEMA,"source":"STATION","instanceId":instance,"operation":operation}
