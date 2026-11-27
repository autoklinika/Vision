"""One-use, short-lived local console approval, separate from WebGUI/DDS.

This is an operator-presence workflow, not a security boundary against a
privileged or same-UID process. The hardware clear gate remains off by default.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .luxonis import private_directory, read_json, atomic_json
from .nero_clear import valid_id, valid_scope

TTL=60


def local_console():
    """Verify the kernel/logind session of this process, not environment claims."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    try:
        lib=ctypes.CDLL("libsystemd.so.0")
        libc=ctypes.CDLL(None)
        session=ctypes.c_char_p()
        if lib.sd_pid_get_session(os.getpid(),ctypes.byref(session))<0 or not session.value:
            return False
        try:
            session_id=session.value.decode("ascii")
        finally:
            libc.free(session)
        r=subprocess.run(["/usr/bin/loginctl","show-session",session_id,
                          "-p","Active","-p","Remote","-p","Seat","-p","User"],
                         capture_output=True,text=True,timeout=1,check=False)
        fields=dict(line.split("=",1) for line in r.stdout.splitlines() if "=" in line)
        return (r.returncode==0 and fields.get("Active")=="yes"
                and fields.get("Remote")=="no" and fields.get("Seat")=="seat0"
                and fields.get("User")==str(os.getuid()))
    except (OSError,ValueError,UnicodeError,subprocess.SubprocessError):
        return False


class Approval:
    def __init__(self,directory,*,clock=time.time):
        self.directory=private_directory(Path(directory));self.clock=clock

    def grant(self,operation,scope):
        if not valid_id(operation) or not valid_scope(scope):raise ValueError("invalid approval")
        now=self.clock()
        atomic_json(self.directory/(operation+".json"),
                    {"operationId":operation,"scope":scope,"createdAt":now,"expiresAt":now+TTL},1024)

    def consume(self,operation,scope):
        if not valid_id(operation) or not valid_scope(scope):return False
        path=self.directory/(operation+".json")
        # The single guarded owner serializes consumption. Move the grant
        # before inspecting it, so malformed/expired grants cannot replay.
        used=self.directory/(operation+".consumed")
        try:
            os.replace(path,used)
        except OSError:
            return False
        try:
            v=read_json(used,1024);now=self.clock()
            return (type(v) is dict and set(v)=={"operationId","scope","createdAt","expiresAt"}
                    and v["operationId"]==operation and type(v["scope"]) is int and v["scope"]==scope
                    and type(v["createdAt"]) in (int,float) and type(v["expiresAt"]) in (int,float)
                    and v["createdAt"]<=now<v["expiresAt"]<=v["createdAt"]+TTL)
        finally:
            used.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",required=True)
    parser.add_argument("operation")
    parser.add_argument("scope",type=int,choices=(*range(1,8),255))
    a=parser.parse_args()
    if not local_console() or not valid_id(a.operation):
        parser.error("an active local console on seat0 is required")
    label="ALL" if a.scope==255 else f"J{a.scope}"
    if input(f"Confirm NERO clear {label}; type {label}: ").strip()!=label or not local_console():
        parser.error("local confirmation rejected")
    Approval(a.directory).grant(a.operation,a.scope)
    print("One-use approval granted for 60 s. No hardware command was sent.")


if __name__=="__main__":main()
