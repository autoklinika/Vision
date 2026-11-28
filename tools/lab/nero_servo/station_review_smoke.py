"""Bounded review of the real Core/IPC/HTTP build on VENTUNO.

Uses the existing passive observation file, an isolated temporary library
and an ephemeral account. No hardware owner, ROS control publisher, manual
transport or control listener is started. The HTTP server is stopped after
the check. The production library and accounts are never opened.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

from vision_api.identity import IdentityStore, provision_account
from vision_api.station import StationApplication
from vision_station.client import RemoteStationOwner
from vision_station.nero_joint_limits import InstalledJointLimits
from vision_station.nero_manual_review import ManualReviewHost
from vision_station.nero_manual_station import load
from vision_station.server import CoreServer


def snapshot():
    p = Path("/sys/class/net/can0/statistics")
    return {k:int((p/k).read_text()) for k in
            ("rx_packets","rx_dropped","rx_errors","tx_packets","tx_errors")}


def services():
    result={}
    for unit in ("vision-nero-guarded-lab.service","vision-core.service",
                 "vision-webgui.service"):
        result[unit]=subprocess.check_output(
            ["systemctl","--user","show",unit,"-p","MainPID","--value"],
            text=True,timeout=2).strip()
    if any(not v.isdecimal() or int(v)<=0 for v in result.values()):
        raise RuntimeError("expected existing operational services")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("candidate","mesh-root","mesh-source-root","dist","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--observer-directory",type=Path,required=True)
    a=parser.parse_args()
    if not all(x.is_absolute() and x.resolve().is_relative_to("/srv/vision-data")
               for x in (a.candidate,a.mesh_root,a.mesh_source_root,a.dist,a.output)):
        parser.error("station NVMe artifacts required")
    if a.output.exists():parser.error("never overwrite a receipt")
    if a.observer_directory != Path("/run/user")/str(os.getuid())/"vision-fluent2-nero":
        parser.error("existing passive observer only")
    os.umask(0o077)
    candidate=load(a.candidate,mesh_root=a.mesh_root,mesh_source_root=a.mesh_source_root)
    before=snapshot()
    owners=services()
    from waitress import create_server
    with tempfile.TemporaryDirectory(prefix=".nero-review-",dir="/srv/vision-data/staging") as tmp:
        root=Path(tmp)
        password=secrets.token_urlsafe(24)
        accounts=root/"accounts.json"
        provision_account(accounts,"reviewer",password,role="operator")
        host=ManualReviewHost(root/"library",candidate=candidate,
                              nero_directory=a.observer_directory,
                              nero_joint_limits=InstalledJointLimits(
                                  a.candidate/"model.urdf",candidate.manifest["limits"]["firmwareProfile"]))
        core=CoreServer(root/"core.sock",host)
        core_thread=threading.Thread(target=core.serve_forever,kwargs={"poll_interval":.05})
        core_thread.start()
        http=None
        worker=None
        try:
            proxy=RemoteStationOwner(root/"core.sock")
            # Port is private loopback. Reserve the actual socket before
            # creating the application's exact allowed origin.
            import socket
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            origin="http://127.0.0.1:"+str(port)
            app=StationApplication(identity=IdentityStore(accounts),owner=proxy,
                                   dist_root=a.dist,origins=[origin],manual_review_local=True)
            http=create_server(app,sockets=[sock],
                               threads=2,connection_limit=8,channel_timeout=3,
                               expose_tracebacks=False)
            worker=threading.Thread(target=http.run,daemon=True)
            worker.start()
            cookie=None
            def request(path,value=None):
                headers={"Origin":origin,"X-Vision-Client":"webgui"}
                if cookie is not None:headers["Cookie"]=cookie
                body=None
                if value is not None:
                    body=json.dumps(value).encode();headers["Content-Type"]="application/json"
                req=urllib.request.Request(origin+path,data=body,headers=headers)
                try:r=urllib.request.urlopen(req,timeout=3)
                except urllib.error.HTTPError as e:r=e
                with r:
                    return r.status,r.headers,r.read()
            code,_,html=request("/")
            assert code==200 and b"vision-deployment" in html
            import re
            assets=re.findall(rb'(?:src|href)="(/assets/[^"]+)"',html)
            assert assets and all(request(path.decode())[0]==200 for path in assets)
            route="/api/v1/devices/nero/manual"
            assert request(route)[0]==401
            code,headers,body=request("/api/v1/auth/login",{"username":"reviewer","password":password})
            assert code==200 and json.loads(body)["role"]=="operator"
            cookie=headers["Set-Cookie"].split(";",1)[0]
            def get(path):
                code,_,raw=request(path)
                assert code==200,(path,code)
                return json.loads(raw)
            station=get("/api/v1/station")
            assert station["coreConnection"]=="CONNECTED" and station["state"]=="NO_ACTIVE_SESSION"
            report=get("/api/v1/devices/nero")
            manual=get(route)["status"]
            tcp=get("/api/v1/devices/nero/control")
            assert report["observer"]=="ACTIVE" and report["graph"]=="ACTIVE"
            assert report["arm"]["errorCode"]==0 and report["arm"]["controlMode"]==3
            assert report["can"]["up"] and report["can"]["bitrate"]==1000000
            assert manual["reason"]=="REVIEW_ONLY" and manual["state"]=="IDLE"
            assert manual["driveEnabled"]==[False]*7
            assert (manual["linearMax"],manual["angularMax"])==(5,2)
            assert all(manual[k] is False for k in ("pipelineReady","enableAvailable","jogAvailable","holdAvailable"))
            assert tcp["jointCheck"]["state"]=="WITHIN_LIMITS"
            assert all(abs(row["velocityRadS"])<=.001 for row in report["joints"]["rows"])
            assert 0<=time.time()-report["joints"]["stamp"]<=2.5
            # A deliberately valid request sent only to the isolated
            # review HTTP application is denied before it reaches Core.
            intent={"instanceId":station["instanceId"],"operationId":secrets.token_hex(16),
                    "action":"ENABLE","sequence":0,"sentAt":time.time(),
                    "declaration":None,"axis":None,"direction":None}
            assert request(route+"/command",intent)[0]==403
            denied=proxy.nero_manual_command(operator="reviewer",**intent)["result"]
            assert denied["accepted"] is False and denied["reason"]=="NOT_COMMISSIONED"
            result={"status":"STATION_REVIEW_DEPLOYMENT_SMOKE_PASS",
                    "physicalExecutionAllowed":False,"physicalCommissioned":False,
                    "realTelemetry":True,"coreConnected":True,"staticAssets":len(assets),
                    "reviewStatus":manual,"jointCheck":tcp["jointCheck"]["state"],
                    "motionHttpStatus":403,"motionIpcAccepted":False,
                    "liveJointAgeMs":round(1000*(time.time()-report["joints"]["stamp"]),2),
                    "controllerMode":report["arm"]["controlMode"],
                    "reviewUiEphemeral":True}
        finally:
            if http is not None:
                http.task_dispatcher.shutdown()
                http.close()
            if worker is not None:worker.join(3.)
            core.shutdown();core_thread.join(3.);core.server_close()
        assert worker is None or not worker.is_alive(), "review HTTP worker did not exit"
    after=snapshot()
    delta={k:after[k]-before[k] for k in before}
    assert services()==owners and delta["tx_packets"]==delta["tx_errors"]==delta["rx_errors"]==0
    result.update(canCounterDelta=delta,operationalPidsUnchanged=True,
                  candidateManifestSha256=hashlib.sha256((a.candidate/"manifest.json").read_bytes()).hexdigest())
    a.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
