"""One standalone CAN ownership request, no motion/Servo runtime.

The private owner socket is served inside the existing guarded ROS node.
The only native transmit path here is the vendor disable() call, once per
fresh explicit request while all seven drives are disabled and stationary.
"""
import fcntl
import os
import socket
import socketserver
import threading
import time
from .protocol import checked_path, checked_socket, check_peer, receive, send
from .nero_clear import valid_id
from .nero_clear_coordinator import valid_actor
from .ros_nero_manual import sdk_feedback

SCHEMA="vision.api.nero-can-connection.v1"
RESULT_SCHEMA="vision.api.nero-can-connection-result.v1"
LIMIT=2048
TIMEOUT=.9
REASONS=("CAN_CONNECTED","ALREADY_CAN","INTERLOCK","STALE","REPLAY","CAN_CONNECT_UNVERIFIED","NOT_COMMISSIONED","BUSY")

def valid_intent(v):
    return (type(v) is dict and set(v)=={"instanceId","operationId","sentAt"}
            and valid_id(v["instanceId"]) and valid_id(v["operationId"])
            and type(v["sentAt"]) in (int,float) and 0<v["sentAt"]<253402300800)

def valid_owner_status(v):
    return (type(v) is dict and set(v)=={"mode","available"} and
            (v["mode"] is None or type(v["mode"]) is int and v["mode"] in (0,1,3))
            and type(v["available"]) is bool and (not v["available"] or v["mode"] in (0,3)))

def valid_status(v):
    return (type(v) is dict and set(v)=={"schema","source","instanceId","status"}
            and v["schema"]==SCHEMA and v["source"]=="STATION" and valid_id(v["instanceId"])
            and valid_owner_status(v["status"]))

def valid_owner_result(v):
    return (type(v) is dict and set(v)=={"operationId","accepted","reason"}
            and valid_id(v["operationId"]) and type(v["accepted"]) is bool
            and v["reason"] in REASONS and v["accepted"]==(v["reason"] in ("CAN_CONNECTED","ALREADY_CAN")))

def valid_result(v):
    return (type(v) is dict and set(v)=={"schema","source","instanceId","result"}
            and v["schema"]==RESULT_SCHEMA and v["source"]=="STATION"
            and valid_id(v["instanceId"]) and valid_owner_result(v["result"]))

def result(op,reason):
    return {"operationId":op,"accepted":reason in ("CAN_CONNECTED","ALREADY_CAN"),"reason":reason}

def status(instance,value):
    return {"schema":SCHEMA,"source":"STATION","instanceId":instance,"status":value}

def envelope(instance,value):
    return {"schema":RESULT_SCHEMA,"source":"STATION","instanceId":instance,"result":value}

class CanConnectionOwner:
    """Shares the same TX lock as HOLD and the sole SDK instance."""
    def __init__(self,node,lock):
        self.node,self.lock=node,lock
        self.used=set()

    def feedback(self):
        o=self.node
        try:
            if not (o.vision_arbiter.mode.value=="LOCKED" and not o.fast_mode
                    and not o.auto_enable and not o.control_enabled and not o.enable_flag
                    and not o.get_parameter("auto_enable").value
                    and not o.get_parameter("control_enabled").value
                    and o.can_port=="can0" and o.physical_hold_enabled):
                return None
            f=sdk_feedback(o,require_can=False)
            if (f is None or not f.valid(time.time(),require_can=False) or f.arm_mask
                    or f.arm_status not in (0,6) or any(f.drive_status)
                    or any(abs(v)>.001 for v in f.velocity)):
                return None
            return f
        except Exception:return None

    def report(self):
        with self.lock:
            f=self.feedback()
            return {"mode":f.control_mode if f else None,
                    "available":f is not None and f.control_mode in (0,3)}

    def command(self,v):
        if not valid_intent(v):raise ValueError("invalid CAN connection intent")
        op=v["operationId"]
        with self.lock:
            if not 0<=time.time()-v["sentAt"]<=1.5:return result(op,"STALE")
            if op in self.used or len(self.used)>=10000:return result(op,"REPLAY")
            before=self.feedback()
            if before is None:return result(op,"INTERLOCK")
            if before.control_mode==1:return result(op,"ALREADY_CAN")
            if before.control_mode not in (0,3):return result(op,"INTERLOCK")
            self.used.add(op)
            sent=time.time()
            try:
                self.node.agx_arm.disable(timeout=0.)
                deadline=time.monotonic()+.30
                while time.monotonic()<deadline:
                    f=self.feedback()
                    if (f is not None and f.control_mode==1 and f.stamp_min()>sent
                            and max(abs(a-b) for a,b in zip(f.q,before.q))<=.001):
                        return result(op,"CAN_CONNECTED")
                    time.sleep(.01)
            except Exception:pass
            return result(op,"CAN_CONNECT_UNVERIFIED")

class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        end=time.monotonic()+TIMEOUT
        try:
            check_peer(self.request)
            v=receive(self.request,limit=LIMIT,deadline=end)
            if type(v) is not dict or set(v)!={"kind","intent"}:return
            if v["kind"]=="status" and v["intent"] is None:r=self.server.owner.report()
            elif v["kind"]=="connect" and valid_intent(v["intent"]):r=self.server.owner.command(v["intent"])
            else:return
            send(self.request,r,limit=LIMIT,deadline=end)
        except Exception:return

class CanConnectionServer(socketserver.UnixStreamServer):
    def __init__(self,path,owner):
        self.path=checked_path(path,create_parent=True);self.owner=owner
        self.lock_fd=os.open(str(self.path)+".lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(self.lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if self.path.exists():checked_socket(self.path);self.path.unlink()
            super().__init__(str(self.path),_Handler,bind_and_activate=False)
            self.server_bind();os.chmod(self.path,0o600);checked_socket(self.path);self.server_activate()
        except BaseException:
            if hasattr(self,"socket"):super().server_close()
            os.close(self.lock_fd);raise
        self.thread=threading.Thread(target=self.serve_forever,kwargs={"poll_interval":.05},daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown();self.thread.join(timeout=2);super().server_close()
        self.path.unlink(missing_ok=True);os.close(self.lock_fd)

class CanConnectionTransport:
    def __init__(self,path):self.path=checked_path(path)
    def exchange(self,kind,intent):
        checked_socket(self.path)
        deadline=time.monotonic()+TIMEOUT
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            c.settimeout(TIMEOUT);c.connect(str(self.path));check_peer(c)
            send(c,{"kind":kind,"intent":intent},limit=LIMIT,deadline=deadline)
            r=receive(c,limit=LIMIT,deadline=deadline)
        if kind=="status":
            if not valid_owner_status(r):raise ValueError("invalid CAN status")
        elif not valid_owner_result(r) or r["operationId"]!=intent["operationId"]:
            raise ValueError("invalid CAN response")
        return r
    def status(self):return self.exchange("status",None)
    def connect(self,intent):
        if not valid_intent(intent):raise ValueError("invalid CAN request")
        return self.exchange("connect",intent)
