"""Standalone connection path: fixture SDK only, never real CAN."""
import threading
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from vision_station.nero_can_connection import CanConnectionOwner,CanConnectionServer,CanConnectionTransport
from vision_station.nero_manual import Feedback
from vision_station.host import CoreHost
from vision_station.server import CoreServer
from vision_station.client import RemoteStationOwner
from vision_api.station import StationApplication
from vision_api.identity import provision_account
import test_station

class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.mode=3;self.drive=0;self.speed=0.;self.age=.001;self.calls=[];self.transition=True
        def disable(**kwargs):
            self.calls.append(kwargs)
            if self.transition:self.mode=1
        self.node=NS(agx_arm=NS(disable=disable),vision_arbiter=NS(mode=NS(value="LOCKED")),
                     fast_mode=False,auto_enable=False,control_enabled=False,enable_flag=False,
                     get_parameter=lambda k:NS(value=False),can_port="can0",physical_hold_enabled=True)
        self.owner=CanConnectionOwner(self.node,threading.RLock())
        self.patch=patch("vision_station.nero_can_connection.sdk_feedback",side_effect=self.feedback)
        self.patch.start();self.addCleanup(self.patch.stop)
    def feedback(self,*a,**kw):
        t=time.time()-self.age
        return Feedback((0.,)*7,(self.speed,)*7,t,t,6,0,self.mode,(self.drive,)*7,(t,)*7,(t,)*7)
    def intent(self,op="b"*32):return {"instanceId":"a"*32,"operationId":op,"sentAt":time.time()}
    def test_explicit_and_no_motion_runtime(self):
        self.assertEqual(self.owner.report(),{"mode":3,"available":True})
        self.assertEqual(self.calls,[])
        req=self.intent();self.assertEqual(self.owner.command(req)["reason"],"CAN_CONNECTED")
        self.assertEqual(self.calls,[{"timeout":0.}])
        self.assertEqual(self.owner.report(),{"mode":1,"available":False})
        self.assertEqual(self.owner.command(req)["reason"],"REPLAY")
        self.assertEqual(self.owner.command(self.intent("c"*32))["reason"],"ALREADY_CAN")
        self.assertEqual(len(self.calls),1)
    def test_stale_moving_fault_and_enabled_rejected(self):
        for d,s,a in ((64,0.,.001),(1,0.,.001),(0,.1,.001),(0,0.,.3)):
            with self.subTest(d=d,s=s,a=a):
                self.drive,self.speed,self.age=d,s,a
                self.assertFalse(self.owner.report()["available"])
                self.assertEqual(self.owner.command(self.intent())["reason"],"INTERLOCK")
        self.assertEqual(self.calls,[])
    def test_timeout_and_no_retry(self):
        self.transition=False
        req=self.intent()
        self.assertEqual(self.owner.command(req)["reason"],"CAN_CONNECT_UNVERIFIED")
        self.assertEqual(self.owner.command(req)["reason"],"REPLAY")
        self.assertEqual(len(self.calls),1)
    def test_hold_latched(self):
        self.node.vision_arbiter.mode.value="STOP_LATCHED"
        self.assertFalse(self.owner.report()["available"])
        self.assertEqual(self.owner.command(self.intent())["reason"],"INTERLOCK")
        self.assertEqual(self.calls,[])
    def test_private_socket_core_and_authenticated_http(self):
        web=test_station.StationTests();web.setUp();self.addCleanup(web.doCleanups)
        private=web.root/"can-owner";private.mkdir(mode=0o700)
        server=CanConnectionServer(private/"can.sock",self.owner);self.addCleanup(server.close)
        idle={"coreConnection":"CONNECTED","state":"NO_ACTIVE_SESSION"}
        host=CoreHost(web.root/"can-library",diagnostics=lambda:(),
                      nero_can_transport=CanConnectionTransport(private/"can.sock"),
                      nero_can_interlock=lambda:idle)
        core=CoreServer(web.root/"ipc/core.sock",host)
        thread=threading.Thread(target=core.serve_forever,kwargs={"poll_interval":.01});thread.start()
        self.addCleanup(lambda:(core.shutdown(),thread.join(3),core.server_close()))
        proxy=RemoteStationOwner(web.root/"ipc/core.sock")
        provision_account(web.accounts,"operator",web.password,replace=True,role="operator")
        web.app=StationApplication(identity=web.identity,owner=proxy,dist_root=web.dist,
                                   origins=["http://127.0.0.1:18490"],nero_can_enabled=True)
        _,cookie=web.login()
        headers={"HTTP_ORIGIN":"http://127.0.0.1:18490","HTTP_X_VISION_CLIENT":"webgui","REMOTE_ADDR":"127.0.0.1"}
        route="/api/v1/devices/nero/can-connection"
        req={**self.intent(),"instanceId":proxy.station_report()["instanceId"]}
        self.assertEqual(web.request(route)["status"],401)
        self.assertEqual(web.request(route,method="POST",value=req,headers=headers)["status"],401)
        self.assertTrue(web.request(route,cookie=cookie,headers=headers)["json"]["status"]["available"])
        self.assertIsNone(proxy.nero_manual_report()["status"])
        self.assertEqual(web.request(route,method="POST",cookie=cookie,value=req,headers={**headers,"HTTP_ORIGIN":"https://other.invalid"})["status"],403)
        idle["state"]="SESSION_ACTIVE"
        self.assertFalse(web.request(route,cookie=cookie,headers=headers)["json"]["status"]["available"])
        self.assertFalse(web.request(route,method="POST",cookie=cookie,value=req,headers=headers)["json"]["result"]["accepted"])
        self.assertEqual(self.calls,[])
        idle["state"]="NO_ACTIVE_SESSION"
        req["sentAt"]=time.time()
        self.assertTrue(web.request(route,method="POST",cookie=cookie,value=req,headers=headers)["json"]["result"]["accepted"])
        self.assertEqual(self.calls,[{"timeout":0.}])
        self.assertFalse(web.request(route,cookie=cookie,headers=headers)["json"]["status"]["available"])

if __name__=="__main__":unittest.main()
