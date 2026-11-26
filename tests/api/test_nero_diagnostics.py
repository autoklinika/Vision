"""NERO diagnostics: synthetic feedback only; no hardware commands."""
import copy
from pathlib import Path
import tempfile
import threading
import time
import unittest

from test_nero import observation
import test_station as fixtures
from vision_station.nero import FLAGS, NeroMonitor
from vision_station.nero_diagnostics import (ARM, DRIVE, SCOPES, decode, projection,
    validate_report, describe, DRIVE_FAULT_MASK)
from vision_station.nero_history import FaultHistory, validate_history
from vision_station.luxonis import atomic_json
from vision_station.nero import MAX_BYTES
from vision_station.host import CoreHost
from vision_station.server import CoreServer
from vision_station.client import RemoteStationOwner
from vision_api.identity import provision_account

INSTANCE = "a"*32

def report(now=100., *, arm=6, mask=0, drives=(0,)*7):
    v=observation(now)
    v.update(schema="vision.api.nero.v1",source="STATION",instanceId=INSTANCE,
             model="AgileX NERO",hardwareConnection="USB_CAN_DETECTED",observer="ACTIVE")
    v["arm"].update(armStatus=arm,errorCode=mask,
        angleLimit=[bool(mask & (1<<(i+8))) for i in range(7)],
        communicationFault=[bool(mask & (1<<i)) for i in range(7)])
    for m,raw in zip(v["motors"]["rows"],drives):
        m.update(rawStatus=raw,enabled=bool(raw&64),faults={k:bool(raw&b) for k,b in zip(FLAGS,DRIVE)})
    return v

class DecoderTests(unittest.TestCase):
    def test_catalog_all_values_and_bits(self):
        for code in range(256):
            e, coverage=decode(report(arm=code))
            self.assertEqual(len(e),1)
            self.assertEqual(e[0]["severity"],ARM.get(code,("","UNKNOWN"))[1])
            self.assertEqual(len(coverage),len(SCOPES))
        for raw in range(256):
            e,_=decode(report(arm=0,drives=(raw,)*7))
            rows=[x for x in e if x["family"]=="DRIVE_STATUS"]
            self.assertEqual(len(rows),7*(raw & DRIVE_FAULT_MASK).bit_count())
        for bit in range(16):
            e,_=decode(report(mask=1<<bit))
            self.assertEqual(len(e),2)
            self.assertEqual(e[1]["hex"],f"0x{1<<bit:04X}")
            source="ARM" if bit in (7,15) else f"J{bit%8+1}"
            self.assertEqual(e[1]["source"],source)
    def test_partial_and_inconsistent(self):
        v=report(mask=1,drives=(4,0,0,0,0,0,0))
        v["arm"]["communicationFault"][0]=False
        v["motors"]["rows"][0]["faults"]["driver_overcurrent"]=False
        e,c=decode(v)
        self.assertEqual(len(e),1)
        self.assertNotIn(("J1","ARM_MASK"),c)
        self.assertNotIn(("J1","DRIVE_STATUS"),c)
        self.assertIn(("J2","DRIVE_STATUS"),c)
        p=projection(v,history_available=True)
        self.assertTrue(validate_report(p))
        p["current"][0]["description"]="invented"
        self.assertFalse(validate_report(p))
    def test_missing_is_unknown_not_normal(self):
        v=report()
        v["arm"]=None;v["motors"]=None
        p=projection(v,history_available=True)
        self.assertEqual(p["coverage"],[])
        self.assertEqual(p["current"],[])
        self.assertTrue(validate_report(p))

class HistoryTests(unittest.TestCase):
    def test_persistence_recurrence_gap_filters(self):
        with tempfile.TemporaryDirectory() as d:
            h=FaultHistory(d)
            v=report(drives=(4,0,0,0,0,0,0))
            h.observe(v);h.observe(v)
            page=h.page(INSTANCE,"J1","ACTIVE")
            self.assertTrue(validate_history(page))
            self.assertEqual(len(page["events"]),1)
            first=page["events"][0]["id"]
            gap=report(101.)
            gap["motors"]=None
            h.observe(gap)
            self.assertEqual(len(h.page(INSTANCE,"J1","ACTIVE")["events"]),1)
            h.close();h=FaultHistory(d)
            h.observe(report(102.))
            self.assertEqual(h.page(INSTANCE,"J1","RESOLVED")["events"][0]["id"],first)
            h.observe(report(103.,drives=(4,0,0,0,0,0,0)))
            self.assertNotEqual(h.page(INSTANCE,"J1","ACTIVE")["events"][0]["id"],first)
            self.assertTrue(validate_history(h.page(INSTANCE)))
            h.close()
    def test_last_seen_and_pagination(self):
        with tempfile.TemporaryDirectory() as d:
            h=FaultHistory(d)
            for i in range(55):
                h.observe(report(100+2*i,arm=0,drives=(4,0,0,0,0,0,0)))
                h.observe(report(101+2*i,arm=0))
            p=h.page(INSTANCE,"J1","RESOLVED")
            self.assertEqual(len(p["events"]),50)
            self.assertTrue(validate_history(p))
            n=h.page(INSTANCE,"J1","RESOLVED",p["nextBefore"])
            self.assertEqual(len(n["events"]),5)
            self.assertTrue(validate_history(n))
            h.close()
    def test_unsafe_storage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"diagnostics.sqlite3").symlink_to(root/"elsewhere")
            with self.assertRaises(OSError): FaultHistory(root)

class BoundaryTests(unittest.TestCase):
    def test_history_without_browser_and_http(self):
        web=fixtures.StationTests();web.setUp();self.addCleanup(web.doCleanups)
        root=web.root/"nero";root.mkdir(mode=0o700)
        history=web.root/"nero-history";history.mkdir(mode=0o700)
        v=observation(time.time());atomic_json(root/"observation.json",v,MAX_BYTES)
        host=CoreHost(web.root/"nero-library",diagnostics=lambda:(),nero_directory=root,nero_history_directory=history)
        socket=web.root/"nero-ipc/core.sock";server=CoreServer(socket,host)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01});thread.start()
        self.addCleanup(lambda:(server.shutdown(),thread.join(3),server.server_close()))
        # No HTTP request has triggered observation.
        deadline=time.monotonic()+2
        while not host._nero_history.history.page(INSTANCE)["events"] and time.monotonic()<deadline:
            time.sleep(.03)
        self.assertEqual(len(host._nero_history.history.page(INSTANCE)["events"]),1)
        web.app.owner=RemoteStationOwner(socket)
        p="/api/v1/devices/nero"
        self.assertEqual(web.request(p+"/diagnostics")["status"],401)
        _,cookie=web.login()
        d=web.request(p+"/diagnostics",cookie=cookie)
        self.assertEqual(d["status"],200);self.assertTrue(validate_report(d["json"]))
        h=web.request(p+"/history?source=ARM&status=ACTIVE&before=0",cookie=cookie)
        self.assertEqual(h["status"],200);self.assertTrue(validate_history(h["json"]))
        self.assertEqual(len(h["json"]["events"]),1)
        self.assertEqual(web.request(p+"/history?source=bad&status=ACTIVE&before=0",cookie=cookie)["status"],400)
        self.assertEqual(web.request(p+"/clear",cookie=cookie,method="POST",value={})["status"],403)
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui"}
        intent={"instanceId":d["json"]["instanceId"],"operationId":"c"*32,"scope":1}
        self.assertEqual(web.request(p+"/clear",cookie=cookie,method="POST",value=intent,headers=headers)["status"],403)
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        _,operator=web.login()
        self.assertEqual(web.request(p+"/clear",cookie=operator,method="POST",value={**intent,"scope":0},headers=headers)["status"],400)
        rejected=web.request(p+"/clear",cookie=operator,method="POST",value=intent,headers=headers)
        self.assertEqual(rejected["status"],200)
        self.assertEqual(rejected["json"]["operation"]["reason"],"NOT_COMMISSIONED")
        self.assertEqual(web.request(p+"/clear",cookie=operator,method="POST",value=intent,headers=headers)["json"],rejected["json"])
        a=web.request(p+"/clear-history?source=J1&before=0",cookie=operator)
        self.assertEqual(a["status"],200)
        self.assertEqual(len(a["json"]["events"]),1)
