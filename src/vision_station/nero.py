"""Bounded read-only NERO projection; no ROS/CAN clients on the Core path."""
import json
import math
from pathlib import Path
import re
import time

from .hardware_presence import usb_hardware_connections
from .luxonis import private_directory, read_json
from .readiness import JOINTS, header_stamp, level, values

SCHEMA = "vision.api.nero.v1"
OBS_SCHEMA = "vision.nero-observation.v1"
DOMAIN = 181
NODE = "/nero_guarded/agx_arm_ctrl_single_node"
MAX_BYTES = 16384
AGE = 2.5
SNAPSHOT_AGE = 3.0
SOURCES = ("joints", "arm", "motors", "parameters")
ARM_CODES = ("controlMode", "armStatus", "modeFeedback", "teachStatus", "motionStatus", "trajectoryNumber", "errorCode")
ARM_FIELDS = ("ctrl_mode", "arm_status", "mode_feedback", "teach_status", "motion_status", "trajectory_num", "err_status")
FLAGS = ("undervoltage", "motor_overtemp", "driver_overcurrent", "driver_overtemp", "collision_tripped", "driver_error", "stall_tripped")
PARAMS = ("control_enabled", "auto_enable", "physical_hold_enabled")
MOTOR_NUM = {"voltageV":"bus_voltage_v", "driverTempC":"driver_temp_deg", "motorTempC":"motor_temp_deg", "currentA":"bus_current"}
MOTOR_FIELDS = {"joint", "level", "enabled", "faults", "rawStatus", *MOTOR_NUM}
CAN_STATES = ("ERROR-ACTIVE","ERROR-WARNING","ERROR-PASSIVE","BUS-OFF","STOPPED","SLEEPING","UNKNOWN")


def number(v, low=-1e6, high=1e6):
    return type(v) in (int,float) and math.isfinite(v) and low<=v<=high


def integer(v, high=2**53-1):
    return type(v) is int and 0<=v<=high


def fresh(stamp, now, age=AGE):
    return number(stamp,0,253402300800) and 0<stamp<=now and now-stamp<=age


def as_int(v, high=65535):
    if not isinstance(v,str) or re.fullmatch(r"[0-9]{1,10}",v) is None:
        return None
    result=int(v)
    return result if result<=high else None


def as_number(v):
    try:
        if not isinstance(v,str) or len(v)>40:
            return None
        result=float(v)
        return result if number(result) else None
    except (ValueError,OverflowError):
        return None


def as_bool(v):
    return {"true":True,"false":False}.get(v) if isinstance(v,str) else None


def flags(v):
    try:
        if not isinstance(v,str) or len(v)>128:return None
        x=json.loads(v)
        return x if type(x) is list and len(x)==7 and all(type(y) is bool for y in x) else None
    except (ValueError,TypeError,RecursionError):
        return None


def parse_joints(msg,now):
    try:
        stamp=header_stamp(msg)
        names=list(msg.name)
        if not fresh(stamp,now) or len(names)!=7 or set(names)!=set(JOINTS):
            return None
        positions=list(msg.position); velocities=list(msg.velocity); efforts=list(msg.effort)
        if len(positions)!=7 or not all(number(x,-100,100) for x in positions):
            return None
        if len(velocities) not in (0,7) or len(efforts) not in (0,7):
            return None
        rows=[]
        for name in JOINTS:
            i=names.index(name)
            rows.append({"joint":name,"positionRad":positions[i],
                         "velocityRadS":velocities[i] if velocities and number(velocities[i]) else None,
                         "torqueNm":efforts[i] if efforts and number(efforts[i]) else None})
        return {"stamp":stamp,"rows":rows}
    except (TypeError,AttributeError,ValueError,OverflowError):
        return None


def parse_arm(msg,now):
    try:
        stamp=header_stamp(msg)
        if not fresh(stamp,now) or len(msg.status)!=1:
            return None
        s=msg.status[0];lvl=level(s)
        if s.name!="arm" or s.hardware_id!="can0:arm" or lvl not in (0,1,2):
            return None
        v=values(s)
        codes={key:as_int(v.get(raw),65535 if key in ("errorCode","trajectoryNumber") else 255)
               for key,raw in zip(ARM_CODES,ARM_FIELDS)}
        angle=flags(v.get("joint_angle_limit"));comm=flags(v.get("communication_status_joint"))
        if any(x is None for x in codes.values()) or angle is None or comm is None:
            return None
        return {"stamp":stamp,"level":lvl,**codes,"angleLimit":angle,"communicationFault":comm}
    except (TypeError,AttributeError,ValueError,KeyError):
        return None


def parse_motors(msg,now):
    try:
        stamp=header_stamp(msg)
        if not fresh(stamp,now) or len(msg.status)!=7 or {s.name for s in msg.status}!=set(JOINTS):
            return None
        rows=[]
        by_name={s.name:s for s in msg.status}
        for i,name in enumerate(JOINTS,1):
            s=by_name[name];lvl=level(s)
            if s.hardware_id!=f"can0:{i}" or lvl is None:
                return None
            row={"joint":name,"level":lvl,"enabled":None,"faults":None,"rawStatus":None,**dict.fromkeys(MOTOR_NUM)}
            if lvl!=3:
                v=values(s)
                enabled=as_bool(v.get("enabled"))
                fs={k:as_bool(v.get(k)) for k in FLAGS}
                nums={k:as_number(v.get(raw)) for k,raw in MOTOR_NUM.items()}
                status=as_int(v.get("status_raw"),255)
                if enabled is None or any(x is None for x in fs.values()) or status is None:
                    row["level"]=3
                else:
                    row.update(enabled=enabled,faults=fs,rawStatus=status,**nums)
            rows.append(row)
        return {"stamp":stamp,"rows":rows}
    except (TypeError,AttributeError,ValueError,KeyError):
        return None


def valid_packet(kind,v,now):
    if v is None:
        return True
    try:
        if type(v) is not dict or not fresh(v["stamp"],now):
            return False
        if kind in ("joints","motors"):
            if set(v)!={"stamp","rows"} or type(v["rows"]) is not list or len(v["rows"])!=7:
                return False
            for i,r in enumerate(v["rows"]):
                if type(r) is not dict or r.get("joint")!=JOINTS[i]:
                    return False
                if kind=="joints":
                    if (set(r)!={"joint","positionRad","velocityRadS","torqueNm"}
                            or not number(r["positionRad"],-100,100)
                            or any(r[k] is not None and not number(r[k]) for k in ("velocityRadS","torqueNm"))):
                        return False
                else:
                    if set(r)!=MOTOR_FIELDS or not integer(r["level"],3):
                        return False
                    if r["level"]==3:
                        if any(r[k] is not None for k in MOTOR_FIELDS-{"joint","level"}):
                            return False
                    elif (type(r["enabled"]) is not bool or not integer(r["rawStatus"],255)
                          or type(r["faults"]) is not dict or set(r["faults"])!=set(FLAGS)
                          or any(type(x) is not bool for x in r["faults"].values())
                          or any(r[k] is not None and not number(r[k]) for k in MOTOR_NUM)):
                        return False
            return True
        if kind=="arm":
            return (set(v)=={"stamp","level",*ARM_CODES,"angleLimit","communicationFault"}
                    and integer(v["level"],2)
                    and all(integer(v[k],65535 if k in ("errorCode","trajectoryNumber") else 255) for k in ARM_CODES)
                    and all(type(v[k]) is list and len(v[k])==7 and all(type(x) is bool for x in v[k])
                            for k in ("angleLimit","communicationFault")))
        if kind=="parameters":
            return set(v)=={"stamp","values"} and type(v["values"]) is dict and set(v["values"])<=set(PARAMS) and all(type(x) is bool for x in v["values"].values())
        return False
    except (KeyError,ValueError,TypeError,OverflowError):
        return False


def parse_can(data,now):
    """Project a single fixed interface from ip -details -statistics -json."""
    try:
        if type(data) is not list or len(data)!=1:
            return None
        row=data[0]
        if row["ifname"]!="can0" or row["linkinfo"]["info_kind"]!="can":
            return None
        info=row["linkinfo"]["info_data"];stats=row.get("stats64") or row.get("stats")
        fields={"stamp":now,"interface":"can0","up":"UP" in row["flags"],
                "state":info.get("state","UNKNOWN"),"bitrate":info.get("bittiming",{}).get("bitrate"),
                "rxErrors":stats["rx"]["errors"],"txErrors":stats["tx"]["errors"],
                "rxDropped":stats["rx"]["dropped"],"txDropped":stats["tx"]["dropped"],
                "rxPackets":stats["rx"]["packets"],"txPackets":stats["tx"]["packets"]}
        return fields if valid_can(fields,now) else None
    except (KeyError,TypeError,AttributeError,ValueError):
        return None


def valid_can(v,now):
    if v is None:return True
    try:
        keys={"stamp","interface","up","state","bitrate","rxErrors","txErrors","rxDropped","txDropped","rxPackets","txPackets"}
        return (type(v) is dict and set(v)==keys and fresh(v["stamp"],now)
                and v["interface"]=="can0" and type(v["up"]) is bool and v["state"] in CAN_STATES
                and (v["bitrate"] is None or integer(v["bitrate"],10000000))
                and all(integer(v[k]) for k in keys-{"stamp","interface","up","state","bitrate"}))
    except (KeyError,TypeError,ValueError):
        return False


def empty(now):
    return {"schema":OBS_SCHEMA,"capturedAt":now,"graph":"UNKNOWN","node":None,
            **dict.fromkeys(SOURCES),"can":None}


def valid_observation(v):
    try:
        if type(v) is not dict or set(v)!=set(empty(1)) or v["schema"]!=OBS_SCHEMA:
            return False
        now=v["capturedAt"]
        if not fresh(now,now) or v["graph"] not in ("UNKNOWN","NO_NODE","AMBIGUOUS","ACTIVE"):
            return False
        if v["graph"]=="ACTIVE":
            if v["node"]!={"domain":DOMAIN,"name":NODE}:return False
        elif v["node"] is not None or any(v[k] is not None for k in SOURCES):
            return False
        return all(valid_packet(k,v[k],now) for k in SOURCES) and valid_can(v["can"],now)
    except (KeyError,TypeError,ValueError,OverflowError):
        return False


class NeroMonitor:
    def __init__(self,directory=None,*,clock=time.time,usb=usb_hardware_connections):
        self.directory=Path(directory) if directory is not None else None
        self.clock,self.usb=clock,usb

    def report(self,instance):
        hardware="UNKNOWN";observer="UNAVAILABLE";now=self.clock();v=empty(now)
        if self.directory is not None:
            try:
                root=private_directory(self.directory)
                hardware=self.usb().get("nero","UNKNOWN")
                if hardware not in ("USB_CAN_DETECTED","USB_CAN_NOT_DETECTED","UNKNOWN"):hardware="UNKNOWN"
                candidate=read_json(root/"observation.json",MAX_BYTES)
                now=self.clock()
                if valid_observation(candidate) and fresh(candidate["capturedAt"],now,SNAPSHOT_AGE):
                    v=dict(candidate);observer="ACTIVE"
                    for k in (*SOURCES,"can"):
                        if v[k] is not None and not fresh(v[k]["stamp"],now):
                            v[k]=None
            except (OSError,ValueError,TypeError):
                pass
        return {**v,"schema":SCHEMA,"source":"STATION","instanceId":instance,"capturedAt":now,
                "model":"AgileX NERO","hardwareConnection":hardware,"observer":observer}


def validate_nero_report(v):
    try:
        if (type(v) is not dict or set(v)!=set(empty(1))|{"source","instanceId","model","hardwareConnection","observer"}
                or v["schema"]!=SCHEMA or v["source"]!="STATION" or v["model"]!="AgileX NERO"
                or not isinstance(v["instanceId"],str) or re.fullmatch(r"[0-9a-f]{32}",v["instanceId"]) is None
                or v["hardwareConnection"] not in ("USB_CAN_DETECTED","USB_CAN_NOT_DETECTED","UNKNOWN")
                or v["observer"] not in ("ACTIVE","UNAVAILABLE")):
            return False
        obs={k:v[k] for k in empty(1)};obs["schema"]=OBS_SCHEMA
        return valid_observation(obs) and (v["observer"]=="ACTIVE" or
            (v["graph"]=="UNKNOWN" and v["can"] is None))
    except (KeyError,TypeError,ValueError):
        return False
