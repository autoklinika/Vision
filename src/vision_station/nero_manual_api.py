"""Strict station envelopes for the local maintenance command channel."""
from .nero_clear import valid_id
from .nero_manual import STATES,ACTIONS
from .nero_manual_transport import valid_status

STATUS_SCHEMA="vision.api.nero-manual.v1"
COMMAND_SCHEMA="vision.api.nero-manual-command.v1"

def locked(instance):
    return {"schema":STATUS_SCHEMA,"source":"STATION","instanceId":instance,"status":None}

def status(instance,value):
    if not valid_status(value):raise ValueError("invalid manual status")
    return {"schema":STATUS_SCHEMA,"source":"STATION","instanceId":instance,"status":value}

def outcome(intent,accepted,reason,state):
    return {"operationId":intent["operationId"],"action":intent["action"],"sequence":intent["sequence"],
            "accepted":accepted,"reason":reason,"state":state}

def envelope(instance,result):
    return {"schema":COMMAND_SCHEMA,"source":"STATION","instanceId":instance,"result":result}

def validate_status(v):
    try:
        return (type(v) is dict and set(v)=={"schema","source","instanceId","status"}
                and v["schema"]==STATUS_SCHEMA and v["source"]=="STATION" and valid_id(v["instanceId"])
                and (v["status"] is None or valid_status(v["status"])))
    except (KeyError,TypeError,ValueError):return False

def validate_command(v):
    try:
        if (type(v) is not dict or set(v)!={"schema","source","instanceId","result"}
                or v["schema"]!=COMMAND_SCHEMA or v["source"]!="STATION" or not valid_id(v["instanceId"])):return False
        r=v["result"]
        return (type(r) is dict and set(r)=={"operationId","action","sequence","accepted","reason","state"}
                and valid_id(r["operationId"]) and r["action"] in ACTIONS and type(r["sequence"]) is int
                and 0<=r["sequence"]<=2**31-1 and type(r["accepted"]) is bool
                and isinstance(r["reason"],str) and 0<len(r["reason"])<=80
                and r["state"] in (*STATES,"LOCKED") and (not r["accepted"] or r["state"]!="LOCKED"))
    except (KeyError,TypeError,ValueError):return False
