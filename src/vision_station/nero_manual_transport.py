"""Fixed private transport between Core and the sole guarded ROS owner."""
import fcntl
import os
from pathlib import Path
import socket
import socketserver
import threading
import time
from .protocol import checked_path,checked_socket,check_peer,receive,send
from .nero_manual import valid_intent,STATES,ACTIONS

LIMIT=4096
TIMEOUT=.8
STATUS_FIELDS={"state","reason","driveEnabled","pipelineReady","enableAvailable","jogAvailable","holdAvailable","linearMax","angularMax"}

def valid_status(v):
    return (type(v) is dict and set(v)==STATUS_FIELDS and v["state"] in STATES
            and isinstance(v["reason"],str) and 0<len(v["reason"])<=80
            and type(v["driveEnabled"]) is list and len(v["driveEnabled"])==7
            and all(x is None or type(x) is bool for x in v["driveEnabled"])
            and all(type(v[k]) is bool for k in ("pipelineReady","enableAvailable","jogAvailable","holdAvailable"))
            and type(v["linearMax"]) is int and 1<=v["linearMax"]<=100
            and type(v["angularMax"]) is int and 1<=v["angularMax"]<=30)

def valid_result(v,intent):
    return (type(v) is dict and set(v)=={"operationId","action","sequence","accepted","reason","state"}
            and all(v[k]==intent[k] for k in ("operationId","action","sequence"))
            and type(v["accepted"]) is bool and isinstance(v["reason"],str)
            and 0<len(v["reason"])<=80 and v["state"] in STATES)

class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        end=time.monotonic()+TIMEOUT
        try:
            check_peer(self.request)
            r=receive(self.request,limit=LIMIT,deadline=end)
            if type(r) is not dict or set(r)!={"kind","intent"}:return
            if r["kind"]=="status" and r["intent"] is None:v=self.server.engine.report()
            elif r["kind"]=="command" and valid_intent(r["intent"]):v=self.server.engine.command(r["intent"])
            else:return
            send(self.request,v,limit=LIMIT,deadline=end)
        except Exception:return

class ManualOwnerServer(socketserver.UnixStreamServer):
    """One same-UID server and one owner engine, no ROS command service."""
    def __init__(self,path,engine):
        self.path=checked_path(path);self.engine=engine
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

class ManualTransport:
    def __init__(self,path):self.path=checked_path(path)
    def exchange(self,kind,intent):
        checked_socket(self.path)
        deadline=time.monotonic()+TIMEOUT
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            c.settimeout(TIMEOUT);c.connect(str(self.path));check_peer(c)
            send(c,{"kind":kind,"intent":intent},limit=LIMIT,deadline=deadline)
            v=receive(c,limit=LIMIT,deadline=deadline)
        if not (valid_status(v) if kind=="status" else valid_result(v,intent)):raise ValueError("invalid manual response")
        return v
    def status(self):return self.exchange("status",None)
    def command(self,intent):
        if not valid_intent(intent):raise ValueError("invalid manual intent")
        return self.exchange("command",intent)
