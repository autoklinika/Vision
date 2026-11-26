"""Synthetic read-only feedback and authenticated Core/HTTP boundary."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace as NS
import unittest

from vision_station.nero import (JOINTS,FLAGS,PARAMS,MAX_BYTES,NODE,DOMAIN,empty,
    parse_joints,parse_arm,parse_motors,parse_can,valid_observation,validate_nero_report,NeroMonitor)
from vision_station.luxonis import atomic_json
from vision_station.host import CoreHost
from vision_station.server import CoreServer,dispatch
from vision_station.client import RemoteStationOwner
from vision_station.protocol import PROTOCOL
from vision_api.identity import provision_account
import test_station as fixtures

NOW=100.


def header(t=NOW-.1):
    return NS(stamp=NS(sec=int(t),nanosec=int((t-int(t))*1e9)))


def diagnostic(name,hardware,v,lvl=0):
    return NS(name=name,hardware_id=hardware,level=bytes([lvl]),
              values=[NS(key=k,value=x) for k,x in v.items()])


def messages(now=NOW):
    h=header(now-.1)
    joint=NS(header=h,name=list(reversed(JOINTS)),position=[i/10 for i in range(7)],
             velocity=[.1]*7,effort=[.2]*7)
    arm=NS(header=h,status=[diagnostic("arm","can0:arm",{
        "ctrl_mode":"1","arm_status":"6","mode_feedback":"1","teach_status":"0",
        "motion_status":"0","trajectory_num":"0","err_status":"0",
        "joint_angle_limit":json.dumps([False]*7),"communication_status_joint":json.dumps([False]*7)},2)])
    motors=NS(header=h,status=[diagnostic(n,f"can0:{i}",{
        "enabled":"false",**dict.fromkeys(FLAGS,"false"),"status_raw":"0",
        "bus_voltage_v":"24.1","driver_temp_deg":"31","motor_temp_deg":"25","bus_current":"0.1"})
        for i,n in enumerate(JOINTS,1)])
    return joint,arm,motors


def can(now=NOW):
    return parse_can([{"ifname":"can0","flags":["UP"],"linkinfo":{"info_kind":"can","info_data":{
        "state":"ERROR-ACTIVE","bittiming":{"bitrate":1000000}}},
        "stats64":{"rx":{"packets":100,"errors":0,"dropped":0},"tx":{"packets":1,"errors":0,"dropped":0}}}],now-.1)


def observation(now=NOW):
    j,a,m=messages(now)
    data=empty(now)
    data.update(graph="ACTIVE",node={"domain":DOMAIN,"name":NODE},
                joints=parse_joints(j,now),arm=parse_arm(a,now),motors=parse_motors(m,now),
                parameters={"stamp":now-.1,"values":dict.fromkeys(PARAMS,False)},can=can(now))
    assert valid_observation(data)
    return data


class NeroTests(unittest.TestCase):
    def test_mapping_and_partial_feedback(self):
        j,a,m=messages()
        parsed=parse_joints(j,NOW)
        self.assertEqual(parsed["rows"][0]["positionRad"],.6)
        self.assertEqual(parsed["rows"][0]["torqueNm"],.2)
        self.assertEqual(parse_arm(a,NOW)["armStatus"],6)
        self.assertFalse(parse_motors(m,NOW)["rows"][0]["enabled"])
        m.status[2].level=b"\x03"
        r=parse_motors(m,NOW)["rows"][2]
        self.assertEqual(r["level"],3)
        self.assertIsNone(r["enabled"]);self.assertIsNone(r["voltageV"])
        self.assertEqual(parse_motors(m,NOW)["rows"][3]["voltageV"],24.1)
        m.status[1].hardware_id="other"
        self.assertIsNone(parse_motors(m,NOW))
        j.position[0]=float("nan")
        self.assertIsNone(parse_joints(j,NOW))
        self.assertIsNone(parse_arm(a,NOW+4))

    def test_strict_schema_and_separate_freshness(self):
        data=observation()
        bad=copy.deepcopy(data);bad["joints"]["rows"][0]["positionRad"]=True
        self.assertFalse(valid_observation(bad))
        bad=copy.deepcopy(data);bad["motors"]["rows"][0]["enabled"]="false"
        self.assertFalse(valid_observation(bad))
        bad=copy.deepcopy(data);bad["node"]["domain"]=185
        self.assertFalse(valid_observation(bad))
        bad=copy.deepcopy(data);bad["graph"]="AMBIGUOUS"
        self.assertFalse(valid_observation(bad))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=[NOW]
            mon=NeroMonitor(root,clock=lambda:now[0],usb=lambda:{"nero":"USB_CAN_DETECTED"})
            data["joints"]["stamp"]=NOW-2.4
            atomic_json(root/"observation.json",data,MAX_BYTES)
            now[0]+=.2
            r=mon.report("a"*32)
            self.assertTrue(validate_nero_report(r));self.assertIsNone(r["joints"])
            self.assertIsNotNone(r["arm"])
            now[0]+=4
            r=mon.report("a"*32)
            self.assertTrue(validate_nero_report(r));self.assertEqual(r["observer"],"UNAVAILABLE")
            self.assertIsNone(r["motors"])
            now[0]=NOW
            (root/"observation.json").chmod(0o644)
            self.assertEqual(mon.report("a"*32)["observer"],"UNAVAILABLE")

    def test_authenticated_http_ipc_and_no_commands(self):
        web=fixtures.StationTests();web.setUp();self.addCleanup(web.doCleanups)
        root=web.root/"nero";root.mkdir(mode=0o700)
        host=CoreHost(web.root/"nero-library",diagnostics=lambda:(),nero_directory=root)
        host._nero.usb=lambda:{"nero":"USB_CAN_DETECTED"}
        atomic_json(root/"observation.json",observation(time.time()),MAX_BYTES)
        socket=web.root/"nero-ipc/core.sock";server=CoreServer(socket,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01});thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        web.app.owner=RemoteStationOwner(socket)
        path="/api/v1/devices/nero"
        self.assertEqual(web.request(path)["status"],401)
        _,reader=web.login()
        r=web.request(path,cookie=reader)
        self.assertEqual(r["status"],200);self.assertEqual(r["json"]["graph"],"ACTIVE")
        self.assertEqual(len(r["json"]["joints"]["rows"]),7)
        self.assertEqual(r["headers"]["Cache-Control"],"no-store")
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,operator=web.login()
        self.assertEqual(web.request(path,cookie=operator,method="POST",value={"enabled":True})["status"],405)
        self.assertEqual(web.request(path+"?topic=other",cookie=operator)["status"],404)
        for op,query in (("nero",{"enabled":True}),("nero_enable",{}),("nero_move",{})):
            with self.assertRaises(ValueError):
                dispatch(host,{"schema":PROTOCOL,"operation":op,"query":query})
